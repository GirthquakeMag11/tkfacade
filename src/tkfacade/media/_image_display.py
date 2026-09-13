"""Image playback: a still or an animation on the timed-media contract.

:class:`ImageDisplay` is the second implementation of
:class:`AbstractMediaDisplay`, beside :class:`~tkfacade.media.VideoDisplay`, so
one piece of code can drive either. Frames are decoded through
:class:`~tkfacade.media.ImageWrapper` and advanced by a Tk timer; there is no
audio, and the members that describe some are inert.
"""

import tkinter as tk
from contextlib import suppress
from typing import Self, Unpack

from .._params import ImageOptions
from .._subscription import Subscription
from ..observable import ObservableBool, ObservableFloat, ObservableInt
from ..widget import BaseWidget, Surface
from ._abstract import AbstractMediaDisplay, MediaVariables
from ._image import ImageInput, ImageWrapper, PhotoImage


class ImageDisplay(Surface, AbstractMediaDisplay):
    """An :class:`AbstractMediaDisplay` showing a still image or an animation.

    Every frame is decoded up front and held for the display's lifetime,
    and the timeline is the frames' own delays laid end to end. A still
    image and a display with no image are both safe to drive — they have
    no timeline, so every transport method is a no-op on them and
    :attr:`paused` stays True.

    An image has no audio, so :attr:`volume` and :attr:`muted` are inert:
    they keep what they are given and report it back, which is what lets
    controls written against the contract bind to this display as they do
    to a video.

    Styling exception, per the classic-widget ruling (2026-08-27):
    the surface and view label are classic, so a
    :class:`~tkfacade.Look` is held without acting here — filed for
    the future classic-widget study.
    """

    __slots__ = (
        "_auto_size_limit",
        "_default_delay",
        "_delays",
        "_display_watches",
        "_elapsed",
        "_ended",
        "_frames",
        "_index",
        "_job",
        "_obstructed_pause",
        "_paused_by_policy",
        "_paused_by_user",
        "_pending_seek",
        "_source",
        "_variables",
        "_view",
        "_wrapper",
    )

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        source: ImageInput | None = None,
        /,
        **options: Unpack[ImageOptions],
    ) -> None:
        """Build the surface and decode ``source`` into it, left paused.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the
                display is created inside.
            source (ImageInput | None): The image to show, anything
                :class:`~tkfacade.media.ImageWrapper` accepts. Defaults to
                None, leaving the display empty.
            **options (Unpack[ImageOptions]): The display's settings,
                each documented as the property of the same name where
                one exists. ``auto_size`` sizes the display to the image
                rather than to ``width`` x ``height``, never exceeding
                ``auto_size_limit`` (default: the screen); ``background``
                is the colour shown around the image; ``default_delay``
                is how long a frame declaring no duration of its own is
                held, in milliseconds, defaulting to 100; ``loop``
                defaults to True, an animation's own convention; and
                ``obstructed_pause``
                decides whether a suppressed surface also stops
                animating, defaulting to False. The surface is unmapped
                either way.
        """
        auto_size = options.get("auto_size", False)
        background = options.get("background", "black")
        height = options.get("height", 540)
        volume = options.get("volume", 100.0)
        width = options.get("width", 960)
        self._auto_size_limit: tuple[int, int] | None = options.get("auto_size_limit")
        self._default_delay: int = options.get("default_delay", 100)
        self._delays: list[int] = []
        self._elapsed: int = 0
        self._ended: bool = False
        self._frames: list[PhotoImage] = []
        self._index: int = 0
        self._job: str | None = None
        self._obstructed_pause: bool = options.get("obstructed_pause", False)
        self._paused_by_policy: bool = False
        self._paused_by_user: bool = True
        self._pending_seek: float | None = None
        self._source: ImageInput | None = source
        self._wrapper: ImageWrapper | None = None
        super().__init__(parent, background=background, height=height, width=width)
        self._view: tk.Label = tk.Label(
            self._surface, background=background, borderwidth=0, highlightthickness=0
        )
        self._route_events(self._view)
        self._view.place(relx=0.5, rely=0.5, anchor="center")
        self._variables: MediaVariables = MediaVariables(
            auto_size=ObservableBool(auto_size),
            duration=ObservableFloat(0.0),
            loop=ObservableBool(options.get("loop", True)),
            media_height=ObservableInt(0),
            media_width=ObservableInt(0),
            muted=ObservableBool(False),
            obstructed=self._obstructed,
            paused=ObservableBool(True),
            position=ObservableFloat(0.0),
            volume=ObservableFloat(max(0.0, min(100.0, volume))),
        )
        self._display_watches: tuple[Subscription, ...] = (
            self._variables.auto_size.watch(self._on_auto_size),
            self._variables.volume.watch(self._on_volume),
        )
        if source is not None:
            self._load(source)

    # -------
    # Surface
    # -------

    def _surface_restore(self) -> None:
        """Remap the surface, lifting any pause the obstruction policy imposed."""
        super()._surface_restore()
        self._release_policy_pause()

    def _surface_blank(self) -> None:
        """Unmap the surface, stopping the timer with it when the policy says to."""
        super()._surface_blank()
        if self._obstructed_pause:
            self._pause_for_policy()

    def _surface_teardown(self) -> None:
        """Cancel the pending tick and drop the frames before Tk frees the widget.

        A tick outliving the display would fire on a destroyed widget
        and, until it did, hold every decoded frame alive through its
        own closure.
        """
        super()._surface_teardown()
        for watch in self._display_watches:
            watch.cancel()
        self._cancel_tick()
        self._frames.clear()
        self._delays.clear()

    # ------
    # Frames
    # ------

    def _load(self, source: ImageInput, /) -> None:
        """Decode ``source`` into the frame list and show its first frame.

        Leaves the timer alone: what a load means for playback is the
        caller's, and every caller here settles it straight after.
        """
        self._wrapper = ImageWrapper(source)
        self._frames.clear()
        self._delays.clear()
        for animframe in self._wrapper.iter_frames(self._default_delay, master=self._tk):
            self._frames.append(animframe.frame)
            self._delays.append(animframe.delay)
        if not self._frames:
            self._frames.append(self._wrapper.photo_for(self._tk))
            self._delays.append(self._default_delay)
        self._elapsed = 0
        self._index = 0
        self._ended = False
        total = sum(self._delays) / 1000 if len(self._frames) > 1 else 0.0
        self._variables.duration.value = total
        self._variables.media_width.value = self._wrapper.width
        self._variables.media_height.value = self._wrapper.height
        self._show_frame()
        self._publish_position()
        if self.auto_size:
            self._resize_to_media()
        pending, self._pending_seek = self._pending_seek, None
        if pending is not None:
            self.seek(pending)

    def _unload(self) -> None:
        """Drop the frames and zero every readout, keeping :attr:`source`."""
        self._wrapper = None
        self._frames.clear()
        self._delays.clear()
        self._elapsed = 0
        self._index = 0
        self._ended = False
        self._variables.duration.value = 0.0
        self._variables.media_width.value = 0
        self._variables.media_height.value = 0
        self._show_frame()
        self._publish_position()

    def _ensure_loaded(self) -> None:
        """Reload what :meth:`stop` unloaded, or rewind an animation that ran out.

        Starting playback is the door out of both states: :meth:`stop`
        leaves :attr:`source` naming an unloaded image, and an
        animation that reached its end with :attr:`loop` off sits on its
        last frame, where advancing cannot move. A no-op otherwise.
        """
        if self._wrapper is None:
            if self._source is not None:
                self._load(self._source)
        elif self._ended:
            self.seek(0.0)

    def _show_frame(self) -> None:
        """Put the frame at the current index on the view; clear it when empty."""
        self._view.configure(image=self._frames[self._index] if self._frames else "")

    def _frame_start(self, index: int, /) -> int:
        """Milliseconds from the start of the animation to the frame at ``index``."""
        return sum(self._delays[:index])

    def _frame_at(self, elapsed: int, /) -> int:
        """Index of the frame holding ``elapsed``; the last one past the end."""
        remaining = elapsed
        for index, delay in enumerate(self._delays):
            if remaining < delay:
                return index
            remaining -= delay
        return max(0, len(self._delays) - 1)

    # --------
    # The tick
    # --------

    def _schedule_tick(self) -> None:
        """Arm the timer for what is left of the frame on screen.

        The remainder, not the whole delay: a :meth:`seek` lands part
        way into a frame, and re-arming for its full length there would
        hold that frame longer than the animation says to.
        """
        self._cancel_tick()
        if len(self._frames) < 2:
            return
        left = self._frame_start(self._index) + self._delays[self._index] - self._elapsed
        self._job = self._tk.after(max(1, left), self._tick)

    def _cancel_tick(self) -> None:
        """Cancel the pending tick, if there is one."""
        if self._job is not None:
            with suppress(tk.TclError):
                self._tk.after_cancel(self._job)
            self._job = None

    def _tick(self) -> None:
        """Advance one frame and re-arm, unless the animation just ran out."""
        self._job = None
        self._advance()
        if not self.paused:
            self._schedule_tick()

    def _advance(self) -> None:
        """Show the next frame, wrapping when looping and pausing when not.

        The position lands exactly on the new frame's start, so it never
        drifts from the frame on screen however far into a frame a seek
        left it.
        """
        following = self._index + 1
        if following >= len(self._frames):
            if not self.loop:
                self._ended = True
                self._variables.paused.value = True
                return
            following = 0
        self._index = following
        self._elapsed = self._frame_start(following)
        self._show_frame()
        self._publish_position()

    def _publish_position(self) -> None:
        """Mirror the elapsed position into its variable, unless something holds it."""
        if not self.position_locked:
            self._variables.position.value = self._elapsed / 1000

    # ------
    # Paused
    # ------

    def _set_paused(self, value: bool, /) -> None:
        """Record a deliberate pause decision and act on it."""
        self._paused_by_user = value
        if value:
            self._cancel_tick()
            self._variables.paused.value = True
        else:
            self._ensure_loaded()
            self._start_playback()
        self._reassert_policy()

    def _start_playback(self) -> None:
        """Run the timer, unless there is nothing to animate.

        A still image and an empty display never play, and the refusal
        settles the state rather than abandoning it: the pause mirror
        is written True and any tick a previous animation armed is
        cancelled, so a still swapped into a running animation stops
        it honestly instead of leaving :attr:`paused` False with a
        stray timer set to fire against the new one.
        """
        if len(self._frames) < 2:
            self._cancel_tick()
            self._variables.paused.value = True
            return
        self._ended = False
        self._variables.paused.value = False
        self._schedule_tick()

    def _pause_for_policy(self) -> None:
        """Stop the timer because the surface is hidden, remembering it was us."""
        self._paused_by_policy = True
        self._cancel_tick()
        self._variables.paused.value = True

    def _release_policy_pause(self) -> None:
        """Undo a pause the policy imposed, unless the caller holds one too."""
        if not self._paused_by_policy:
            return
        self._paused_by_policy = False
        if self._paused_by_user or self._ended:
            return
        self._start_playback()

    def _reassert_policy(self) -> None:
        """Re-apply the obstruction pause after anything that may have lifted it."""
        if self._obstructed_pause and self.obstructed:
            self._pause_for_policy()

    # -----------------
    # Traced variables
    # -----------------

    def _on_auto_size(self, value: bool, /) -> None:
        """Re-fit to the image when :attr:`~MediaVariables.auto_size` turns on.

        Turning it *off* does nothing, which is what leaves the display
        at its reached size rather than snapping back.
        """
        if value:
            self._resize_to_media()

    def _on_volume(self, value: float, /) -> None:
        """Clamp :attr:`~MediaVariables.volume` on write.

        Clamps in place, since a widget bound to the observable — or a
        caller writing it directly — can put anything there, and the
        level a display reports should stay inside its range whether or
        not anything listens to it.
        """
        clamped = max(0.0, min(100.0, value))
        if clamped != value:
            self._variables.volume.value = clamped  # settles once more, then agrees

    # -----
    # State
    # -----

    @property
    def variables(self) -> MediaVariables:
        """The live Tk variables tracking playback; see :class:`MediaVariables`."""
        return self._variables

    @property
    def source(self) -> ImageInput | None:
        """The image last given to the constructor or :meth:`play`, or None.

        Kept through a :meth:`stop`, which unloads the frames but leaves
        this naming what to load again.
        """
        return self._source

    @property
    def wrapper(self) -> ImageWrapper | None:
        """The wrapper the frames were decoded from, or None when empty.

        The image pipeline's own currency rather than a reach below
        the facade: it is what the transformations in :mod:`tkfacade.media`
        take and answer, so transforming a display's image is
        ``display.play(rotate(display.wrapper, 90))``.
        """
        return self._wrapper

    @property
    def index(self) -> int:
        """Index of the frame on screen; 0 when there is no image."""
        return self._index

    @property
    def default_delay(self) -> int:
        """Milliseconds a frame declaring no duration of its own is held for.

        Defaults to 100. Fixed at construction: the delays are read off
        the frames as they decode, so a new value would mean decoding
        again.
        """
        return self._default_delay

    @property
    def loop(self) -> bool:
        """Whether the animation restarts when it reaches its last frame.

        With :attr:`loop` off it stops on that frame and :attr:`paused`
        reads True, and starting playback again starts it over.
        """
        return self._variables.loop.value

    @loop.setter
    def loop(self, value: bool) -> None:
        self._variables.loop.value = value

    @property
    def muted(self) -> bool:
        """Whether audio is silenced; inert, an image having none.

        Kept and reported so that controls written against
        :class:`AbstractMediaDisplay` bind here as they do to a video,
        and nothing else follows from it.
        """
        return self._variables.muted.value

    @muted.setter
    def muted(self, value: bool) -> None:
        self._variables.muted.value = value

    @property
    def media_width(self) -> int:
        """The image's own width in pixels; 0 when there is no image."""
        return self._variables.media_width.value

    @property
    def media_height(self) -> int:
        """The image's own height in pixels; 0 when there is no image."""
        return self._variables.media_height.value

    @property
    def auto_size(self) -> bool:
        """Whether the display asks for the size of the image it holds."""
        return self._variables.auto_size.value

    @auto_size.setter
    def auto_size(self, value: bool) -> None:
        self._variables.auto_size.value = value

    @property
    def auto_size_limit(self) -> tuple[int, int] | None:
        """The largest size auto-sizing may ask for, or None for the screen."""
        return self._auto_size_limit

    @auto_size_limit.setter
    def auto_size_limit(self, value: tuple[int, int] | None) -> None:
        self._auto_size_limit = value
        if self.auto_size:
            self._resize_to_media()

    @property
    def obstructed_pause(self) -> bool:
        """Whether the animation stops while the surface is suppressed."""
        return self._obstructed_pause

    @obstructed_pause.setter
    def obstructed_pause(self, policy: bool) -> None:
        self._obstructed_pause = policy
        if not self.obstructed:
            return
        if policy:
            self._pause_for_policy()
        else:
            self._release_policy_pause()

    @property
    def position(self) -> float:
        """Playback position in seconds; setting it seeks."""
        return self._variables.position.value

    @position.setter
    def position(self, seconds: float) -> None:
        self.seek(seconds)

    @property
    def duration(self) -> float:
        """The animation's length in seconds, its frames' delays added up."""
        return self._variables.duration.value

    @property
    def paused(self) -> bool:
        """Whether the animation is stopped, however it came to be.

        Always True on a still image and on a display with no image,
        neither of which ever animates.
        """
        return self._variables.paused.value

    @paused.setter
    def paused(self, value: bool) -> None:
        self._set_paused(value)

    @property
    def volume(self) -> float:
        """Volume from 0.0 to 100.0; inert, an image having no audio.

        Assignments outside the range clamp, and the level is kept and
        reported for controls to bind to; see :attr:`muted`.
        """
        return self._variables.volume.value

    @volume.setter
    def volume(self, value: float) -> None:
        self._variables.volume.value = max(0.0, min(100.0, value))

    # --------
    # Playback
    # --------

    def play(self, source: ImageInput | None = None, /) -> Self:
        """Show ``source``, or resume the current image when given none.

        Decoding happens here, so the frames and :attr:`duration` are
        ready by the time this returns. Resuming an image :meth:`stop`
        unloaded decodes it again, and an animation that ran to its end
        with :attr:`loop` off starts over — so :meth:`play` is
        the way out of both. A still image and an empty display are
        left paused, having nothing to animate.

        Args:
            source (ImageInput | None): The image to show, anything
                :class:`~tkfacade.media.ImageWrapper` accepts. Defaults to
                None, meaning keep the current one.

        Returns:
            ``self``, for chaining.
        """
        self._paused_by_user = False
        if source is not None:
            self._source = source
            self._pending_seek = None
            self._load(source)
        else:
            self._ensure_loaded()
        self._start_playback()
        self._reassert_policy()
        return self

    def pause(self) -> Self:
        """Stop the animation on the frame it is showing.

        Returns:
            ``self``, for chaining.
        """
        self._set_paused(True)
        return self

    def resume(self) -> Self:
        """Start the animation again from where it stopped.

        Returns:
            ``self``, for chaining.
        """
        self._set_paused(False)
        return self

    def toggle_pause(self) -> Self:
        """Stop the animation if it is running, start it if it is not.

        Returns:
            ``self``, for chaining.
        """
        self._set_paused(not self.paused)
        return self

    def stop(self) -> Self:
        """Stop the animation and drop the frames, discarding a held seek.

        :attr:`duration` and :attr:`position` read 0 at once and the
        view clears, while :attr:`source` keeps naming the image, so
        starting playback again decodes it from the start. A
        :meth:`seek` issued straight after this is held and applied to
        that reload.

        Returns:
            ``self``, for chaining.
        """
        self._pending_seek = None
        self._paused_by_user = True
        self._cancel_tick()
        self._variables.paused.value = True
        self._unload()
        return self

    def seek(self, seconds: float, /) -> Self:
        """Move to an absolute position, showing the frame it falls in.

        The position is recorded exactly as asked for; only the frame
        quantizes, since an animation holds each frame for its own delay.
        Playback carries on from there.

        With no timeline to move in — a still image, an empty display,
        or one :meth:`stop` unloaded — the request is held, and the
        reload starting playback performs applies it, so ``stop()``
        then ``seek(saved)`` comes back where it left off. :meth:`play`
        with a new image and :meth:`stop` each discard a request still
        waiting.

        Args:
            seconds (float): Target position from the start of the
                animation. Clamped to zero, and to :attr:`duration`
                once there is one.

        Returns:
            ``self``, for chaining.
        """
        target = max(0.0, seconds)
        duration = self.duration
        if duration <= 0.0:  # 0.0 is "no timeline", never a real length
            self._pending_seek = target
            return self
        self._elapsed = round(min(target, duration) * 1000)
        self._index = self._frame_at(self._elapsed)
        self._ended = False
        self._show_frame()
        self._publish_position()
        if not self.paused:
            self._schedule_tick()
        return self

    def skip(self, delta: float, /) -> Self:
        """Move ``delta`` seconds from the current position.

        Delegates to :meth:`seek`, so it clamps and shows the frame it
        lands in. Repeated skips accumulate exactly: each records its
        target as the position the next reads, and while a request is
        held for an image that has not loaded, the held target is that
        recording.

        Args:
            delta (float): Seconds to move; negative goes backwards.

        Returns:
            ``self``, for chaining.
        """
        pending = self._pending_seek
        base = pending if pending is not None else self.position
        return self.seek(base + delta)
