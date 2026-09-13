"""Video playback: mpv behind the timed-media contract, controls elsewhere.

:class:`VideoDisplay` is mpv behind :class:`AbstractMediaDisplay`'s
contract, driven entirely from code; a video with controls is
:class:`~tkfacade.media.MediaPlayer`, which holds one of these beside an
image display and a bar.

Tk widgets cannot be drawn over a video: the OS composites mpv's output
above anything Tk paints in the same place, whatever Tk's stacking
order says. The display is a surface and unmaps itself whenever
Tk reports something in front, so a covered video disappears rather
than hiding the widget over it.

Requires libmpv, which the bundled mpv binding loads when the first
display is constructed — importing this module, or tkfacade, costs
nothing. Windows (HWND) and Linux/X11 (Window ID) only: macOS needs an
``NSView`` pointer Tk does not expose.
"""

import time
import tkinter as tk
from collections import deque
from collections.abc import Callable
from contextlib import suppress
from typing import TYPE_CHECKING, Any, Final, Self, Unpack

from .._params import VideoOptions
from .._subscription import Subscription
from .._types import MediaSource
from ..observable import ObservableBool, ObservableFloat, ObservableInt
from ..widget import BaseWidget, Surface
from ._abstract import AbstractMediaDisplay, MediaVariables

if TYPE_CHECKING:
    from ._mpv import MPV

_PUMP_INTERVAL: Final[int] = 50
"""Milliseconds between drains of the queue mpv's threads report through."""

_SEEK_SETTLE: Final[float] = 0.5
"""Seconds within which a reported position counts as the seek having landed."""

_SEEK_TIMEOUT: Final[float] = 3.0
"""Seconds after which a seek is taken as landed however far off it reports."""


class VideoDisplay(Surface, AbstractMediaDisplay):
    """An :class:`AbstractMediaDisplay` that mpv renders video into.

    mpv draws straight into a native window handle, so decoded frames
    never enter Python or Tk's image system. There are no controls:
    playback is driven through the methods and properties the contract
    names and watched through the Tk variables in :attr:`variables`,
    and :class:`~tkfacade.media.MediaPlayer` is this plus an image display
    and a control bar.

    libmpv itself loads at construction — the one moment a missing
    library can raise in the caller's own stack — and mpv starts
    lazily, once Tk has mapped the surface and a window handle exists.
    Anything set before then — source, pause, loop, mute, volume,
    :attr:`auto_size` — is replayed when it appears, and a :meth:`seek`
    or :attr:`position` write once mpv reports a timeline to seek in.

    Styling exception, per the classic-widget ruling (2026-08-27):
    the surface is a classic frame mpv draws into, so a
    :class:`~tkfacade.Look` is held without acting here — filed for
    the future classic-widget study.
    """

    __slots__ = (
        "_auto_size_limit",
        "_display_watches",
        "_file_loaded",
        "_hwdec",
        "_mpv",
        "_obstructed_pause",
        "_paused_by_policy",
        "_paused_by_user",
        "_pending_seek",
        "_pending_source",
        "_pump_job",
        "_seek_deadline",
        "_seek_target",
        "_source",
        "_stale_timeline",
        "_unloading",
        "_updates",
        "_variables",
        "_wid",
    )

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        source: MediaSource | None = None,
        /,
        **options: Unpack[VideoOptions],
    ) -> None:
        """Build the surface and queue ``source``, without starting mpv yet.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the
                display is created inside.
            source (MediaSource | None): File or URL to play as soon as
                the surface is drawable. Defaults to None, meaning
                nothing is queued.
            **options (Unpack[VideoOptions]): The display's settings,
                each documented as the property of the same name where
                one exists. ``auto_size`` sizes the display to whatever
                is playing rather than to ``width`` x ``height``, never
                exceeding ``auto_size_limit`` (default: the screen);
                ``background`` is the colour shown where mpv has not
                drawn; ``hwdec`` is mpv's hardware-decoding mode; and
                ``obstructed_pause`` decides whether a suppressed
                surface also stops decoding, defaulting to False so
                that audio keeps running, as a hidden
                :class:`~tkfacade.label.ImageLabel` keeps animating.
                The surface is unmapped either way.
        """
        from . import _mpv  # ruff: ignore[unused-import]

        auto_size = options.get("auto_size", False)
        auto_size_limit = options.get("auto_size_limit")
        background = options.get("background", "black")
        height = options.get("height", 540)
        hwdec = options.get("hwdec", "auto-safe")
        loop = options.get("loop", False)
        obstructed_pause = options.get("obstructed_pause", False)
        volume = options.get("volume", 100.0)
        width = options.get("width", 960)
        self._mpv: MPV | None = None
        self._wid: int = 0
        self._pump_job: str | None = None
        self._seek_target: float | None = None
        self._seek_deadline: float = 0.0
        self._pending_seek: float | None = None
        self._stale_timeline: bool = False
        self._unloading: bool = False
        self._file_loaded: bool = False
        self._updates: deque[tuple[Callable[..., None], tuple[Any, ...]]] = deque()
        self._auto_size_limit: tuple[int, int] | None = auto_size_limit
        self._hwdec: str = hwdec
        self._obstructed_pause: bool = obstructed_pause
        self._paused_by_policy: bool = False
        self._paused_by_user: bool = False
        self._source: str | None = None if source is None else str(source)
        self._pending_source: str | None = self._source
        super().__init__(parent, background=background, height=height, width=width)
        self._variables: MediaVariables = MediaVariables(
            auto_size=ObservableBool(auto_size),
            duration=ObservableFloat(0.0),
            loop=ObservableBool(loop),
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
            self._variables.loop.watch(self._on_loop),
            self._variables.muted.watch(self._on_muted),
            self._variables.volume.watch(self._on_volume),
        )

    # -------
    # Surface
    # -------

    def _surface_restore(self) -> None:
        """Remap the surface, (re)attaching mpv and lifting any policy pause.

        :meth:`_ensure_backend` runs on every restore, not just the
        first: it attaches mpv the first time the surface is drawable
        and rebuilds it whenever the window handle has changed. A
        pause the obstruction policy imposed is then released.
        """
        super()._surface_restore()
        self._ensure_backend()
        self._release_policy_pause()

    def _surface_blank(self) -> None:
        """Unmap the surface, pausing with it when the policy says to."""
        super()._surface_blank()
        if self._obstructed_pause:
            self._pause_for_policy()

    def _surface_teardown(self) -> None:
        """Terminate mpv before Tk frees the window it is drawing into.

        Reversed, mpv writes into a freed native window and the
        process dies with a segfault rather than a traceback.
        ``terminate`` joins mpv's event thread, blocking the mainloop
        for as long as that takes; see :meth:`_post` for why that
        thread must never be left waiting on Tk.
        """
        super()._surface_teardown()
        for watch in self._display_watches:
            watch.cancel()
        if self._pump_job is not None:
            with suppress(tk.TclError):
                self._tk.after_cancel(self._pump_job)
            self._pump_job = None
        self._updates.clear()
        if self._mpv is not None:
            player, self._mpv = self._mpv, None
            player.terminate()

    def _ensure_backend(self) -> None:
        """Attach mpv to the surface's window handle, or re-attach on a new one."""
        handle = self._surface.winfo_id()
        if not handle:
            return
        if self._mpv is not None:
            if handle == self._wid:
                return
            player, self._mpv = self._mpv, None
            player.terminate()
        self._wid = handle
        self._seek_target = None  # a fresh player reports its own timeline
        from ._mpv import MPV

        self._mpv = MPV(
            wid=str(handle),
            vo="gpu",
            hwdec=self._hwdec,
            keep_open="yes",
            osc=False,
            input_default_bindings=False,
            input_vo_keyboard=False,
        )
        self._attach_observers()
        if self._pump_job is None:
            self._pump_job = self._tk.after(_PUMP_INTERVAL, self._pump)
        self._push_volume()
        self._push_loop()
        self._push_mute()
        if self._pending_source is not None:
            path, self._pending_source = self._pending_source, None
            self._mpv.play(path)
        self._push_pause(self._paused_by_user)
        self._reassert_policy()

    # ------------------
    # Settable variables
    # ------------------

    def _on_loop(self, _value: bool, /) -> None:
        """Push the loop flag whenever :attr:`~MediaVariables.loop` is written."""
        self._push_loop()

    def _push_loop(self) -> None:
        """Push the loop flag to mpv, if mpv exists to be told.

        One way only: ``loop-file`` reads back as the string ``"inf"``
        rather than the bool it was set from, so :attr:`loop` answers
        from the variable and never consults mpv.
        """
        if self._mpv is not None:
            self._mpv.loop_file = "inf" if self.loop else "no"

    def _on_muted(self, _value: bool, /) -> None:
        """Push the mute flag whenever :attr:`~MediaVariables.muted` is written."""
        self._push_mute()

    def _push_mute(self) -> None:
        """Push the mute flag to mpv, if mpv exists to be told.

        mpv's own ``mute`` leaves ``volume`` alone, so nothing here
        has to remember a level across a mute and restore it.
        """
        if self._mpv is not None:
            self._mpv.mute = self.muted

    def _on_volume(self, value: float, /) -> None:
        """Clamp :attr:`~MediaVariables.volume` on write, then push it to mpv.

        Clamps in place, since a widget bound to the observable — or a
        caller writing it directly — can put anything there, and mpv
        should not be handed a level outside its range.
        """
        clamped = max(0.0, min(100.0, value))
        if clamped != value:
            self._variables.volume.value = clamped  # settles once more, then agrees
            return
        self._push_volume()

    def _push_volume(self) -> None:
        """Push the volume level to mpv, if mpv exists to be told."""
        if self._mpv is not None:
            self._mpv.volume = self._variables.volume.value

    def _on_auto_size(self, value: bool, /) -> None:
        """Re-fit to the video when :attr:`~MediaVariables.auto_size` turns on.

        Turning it *off* does nothing, which is what leaves the
        display at its reached size rather than snapping back.
        """
        if value:
            self._resize_to_media()

    # ------
    # Paused
    # ------

    def _push_pause(self, value: bool, /) -> None:
        """Set mpv's pause flag and mirror it into the variable at once.

        Mirrored here rather than left to mpv's report, so a caller
        that pauses and immediately reads :attr:`paused` sees what it
        just asked for, not what mpv last said.
        """
        self._variables.paused.value = value
        if self._mpv is not None:
            self._mpv.pause = value

    def _set_paused(self, value: bool, /) -> None:
        """Record a deliberate pause decision and push it to mpv.

        An unpause is an intent to start playback, so it reloads a
        source :meth:`stop` unloaded — which is what lets a transport
        play button recover from its own stop button.
        """
        self._paused_by_user = value
        if not value:
            self._ensure_loaded()
        self._push_pause(value)
        self._reassert_policy()

    def _ensure_loaded(self) -> None:
        """Load the recorded source if nothing is loaded or queued.

        :meth:`stop` unloads the file while :attr:`source` keeps
        naming it, so an intent to start playback afterwards means
        loading it again — from the start, mpv holding no position for
        unloaded file. A file a natural end left loaded is the same
        intent in a different state: ``keep_open`` holds it on its
        last frame, where an unpause cannot advance, so it is rewound
        to the start instead. A no-op while a mid-file file is loaded
        or already queued for the backend, and with no source recorded
        at all.
        """
        if self._source is None:
            return
        if self._mpv is None:
            if self._pending_source is None:
                self._pending_source = self._source
        elif self._mpv.path is None or self._unloading:
            self._unloading = False
            self._file_loaded = True
            pending, self._pending_seek = self._pending_seek, None
            if pending is None:
                self._mpv.play(self._source)
            else:
                self._mpv.loadfile(self._source, start=str(pending))
                self._begin_seek(pending)
        elif self._mpv.eof_reached:
            self._mpv.seek(0, reference="absolute", precision="exact")

    def _pause_for_policy(self) -> None:
        """Pause because the surface is hidden, remembering that it was us.

        The push is unconditional even when the flag is already up: a
        deliberate unpause overwrites the pause without touching the
        flag, so :meth:`_reassert_policy` must be able to put it back —
        the flag remembers whose pause it is, not that one still holds.
        """
        if self._mpv is None:
            return
        self._paused_by_policy = True
        self._push_pause(True)

    def _release_policy_pause(self) -> None:
        """Undo a pause the policy imposed, unless something else holds one.

        A deliberate pause survives the release, and so does the pause
        ``keep_open`` imposes at a natural end: the file was finished
        before the surface was covered, so uncovering restores that
        state rather than resuming anything. Pushing the unpause there
        would also poison the mirror — mpv refuses it (nothing can
        advance at EOF) and, its value never changing, reports nothing
        to correct the False the push wrote, so a transport bar would
        claim playing over a frozen last frame indefinitely. Starting
        playback again is the door out of EOF, via its rewind.
        """
        if not self._paused_by_policy:
            return
        self._paused_by_policy = False
        if self._paused_by_user:
            return
        if self._mpv is not None and self._mpv.eof_reached:
            return
        self._push_pause(False)

    def _reassert_policy(self) -> None:
        """Re-apply the obstruction pause after anything that may have lifted it."""
        if self._obstructed_pause and self.obstructed:
            self._pause_for_policy()

    # ---------
    # mpv -> Tk
    # ---------

    def _attach_observers(self) -> None:
        """Subscribe to the mpv properties the Tk variables mirror."""
        player = self._mpv
        if player is None:
            return
        player.observe_property("time-pos", self._observe_time)
        player.observe_property("duration", self._observe_duration)
        player.observe_property("pause", self._observe_pause)
        player.observe_property("dwidth", self._observe_media_width)
        player.observe_property("dheight", self._observe_media_height)

    def _observe_time(self, _name: str, value: float | None) -> None:
        """Post a ``time-pos`` report from mpv's thread to the main one.

        None is a report too — the position of no file — and resets
        the mirror, so an unload does not leave the dead file's
        readout standing.
        """
        self._post(self._apply_position, 0.0 if value is None else float(value))

    def _observe_duration(self, _name: str, value: float | None) -> None:
        """Post a ``duration`` report from mpv's thread to the main one.

        None — no file, or one not yet measured — resets the mirror to
        0.0, the not-reported sentinel, without touching a held seek:
        the replay in :meth:`_apply_duration` waits for a real length.
        """
        if value is None:
            self._post(self._apply_no_duration)
        else:
            self._post(self._apply_duration, float(value))

    def _observe_pause(self, _name: str, value: bool | None) -> None:
        """Post a ``pause`` report from mpv's thread to the main one."""
        if value is not None:
            self._post(self._apply_paused, bool(value))

    def _observe_media_width(self, _name: str, value: int | None) -> None:
        """Post a ``dwidth`` report from mpv's thread to the main one; None is 0."""
        self._post(self._apply_media_size, self._variables.media_width, int(value or 0))

    def _observe_media_height(self, _name: str, value: int | None) -> None:
        """Post a ``dheight`` report from mpv's thread to the main one; None is 0."""
        self._post(self._apply_media_size, self._variables.media_height, int(value or 0))

    def _post(self, fn: Callable[..., None], /, *args: Any) -> None:
        """Hand a state change from an mpv thread to the Tk main thread.

        Nothing may touch Tk from an mpv callback's own thread: a Tcl
        call from a foreign thread blocks until the main thread picks
        it up, and the main thread may be inside ``terminate`` waiting
        for that very thread. The work is queued for :meth:`_pump`
        instead, which drains it on a timer the main thread owns.
        """
        if not self._torn_down:
            self._updates.append((fn, args))

    def _pump(self) -> None:
        """Apply everything mpv has reported since the last tick, then re-arm."""
        if self._torn_down:
            self._pump_job = None
            return
        updates = self._updates
        while updates:
            fn, args = updates.popleft()
            fn(*args)
        with suppress(tk.TclError):
            self._pump_job = self._tk.after(_PUMP_INTERVAL, self._pump)

    def _begin_seek(self, target: float, /) -> None:
        """Hold the reported position at ``target`` until mpv catches up.

        Position reports already in flight when a seek is issued still
        describe where playback *was*; applied as they arrive, they
        drag the seek bar back for a tick before the new position
        lands. Writing the target straight into the variable keeps the
        thumb where the user let go, and :meth:`_apply_position`
        ignores mpv until it agrees.

        Args:
            target (float): The position that was asked for.
        """
        self._seek_target = target
        self._seek_deadline = time.monotonic() + _SEEK_TIMEOUT
        self._variables.position.value = target

    def _apply_position(self, value: float) -> None:
        """Record a reported position, unless a drag or pending seek holds it."""
        if self.position_locked:
            return
        target = self._seek_target
        if target is not None:
            if abs(value - target) > _SEEK_SETTLE and time.monotonic() < self._seek_deadline:
                return  # still describes where playback was before the seek
            self._seek_target = None
        self._variables.position.value = value

    def _apply_no_duration(self) -> None:
        """Record that no file is measured: reset the mirror, open the gate.

        mpv's reports arrive in order, so the None a load or stop
        produces is the unload marker: any duration report still queued
        ahead of it described the previous file, and
        :attr:`_stale_timeline` holds the mirror and the seek replay
        shut until this passes.
        """
        self._stale_timeline = False
        self._unloading = False
        self._variables.duration.value = 0.0

    def _apply_duration(self, value: float) -> None:
        """Record the duration mpv reported, and issue any seek held for it.

        A duration is mpv's first word that there is a timeline to seek
        in, so a request held from before the backend existed is
        replayed here. It is re-clamped on the way through, against a
        length that is only now known. A report from before the current
        load's unload marker is the previous file's length — worthless
        for the mirror, poison for the clamp — and is dropped.
        """
        if self._stale_timeline:
            return
        self._variables.duration.value = value
        pending, self._pending_seek = self._pending_seek, None
        if pending is not None:
            self.seek(pending)

    def _apply_paused(self, value: bool) -> None:
        """Record the pause state mpv reported."""
        self._variables.paused.value = value

    def _apply_media_size(self, observable: ObservableInt, value: int) -> None:
        """Record one axis of the video's size and re-fit if asked to.

        mpv reports the axes as separate properties, so this runs
        twice per size change and the pair is briefly mismatched. In
        practice that stays off the screen: the two reports usually
        arrive within one :meth:`_pump` drain and land in a single
        pass, and even when the timer fires between them, Tk defers
        geometry to idle, so the transient mismatched size request
        does not paint.
        """
        observable.value = value
        if self.auto_size:
            self._resize_to_media()

    # -----
    # State
    # -----

    @property
    def variables(self) -> MediaVariables:
        """The live Tk variables tracking playback; see :class:`MediaVariables`."""
        return self._variables

    @property
    def ready(self) -> bool:
        """Whether mpv exists yet; False until the surface is first drawable."""
        return self._mpv is not None

    @property
    def source(self) -> str | None:
        """The file or URL last given to the constructor or :meth:`play`, or None."""
        return self._source

    @property
    def loop(self) -> bool:
        """Whether the current file restarts when it reaches the end.

        Repeats forever; a finite repeat count is not offered — mpv's
        own ``loop-file`` counts exist, but a setting the next write or
        a rebuilt backend silently loses is not one the facade can
        promise.
        """
        return self._variables.loop.value

    @loop.setter
    def loop(self, value: bool) -> None:
        self._variables.loop.value = value

    @property
    def muted(self) -> bool:
        """Whether audio is silenced, independently of :attr:`volume`.

        mpv's own mute rather than a volume of zero, so unmuting
        restores exactly the level the slider was showing.
        """
        return self._variables.muted.value

    @muted.setter
    def muted(self, value: bool) -> None:
        self._variables.muted.value = value

    @property
    def media_width(self) -> int:
        """The playing video's own display width; 0 until mpv reports one."""
        return self._variables.media_width.value

    @property
    def media_height(self) -> int:
        """The playing video's own display height; 0 until mpv reports one."""
        return self._variables.media_height.value

    @property
    def auto_size(self) -> bool:
        """Whether the display asks for the size of whatever is playing."""
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
        """Whether playback pauses while the surface is suppressed."""
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
        """Length of the current file in seconds."""
        return self._variables.duration.value

    @property
    def paused(self) -> bool:
        """Whether playback is paused, however it came to be."""
        return self._variables.paused.value

    @paused.setter
    def paused(self, value: bool) -> None:
        self._set_paused(value)

    @property
    def volume(self) -> float:
        """Volume from 0.0 to 100.0; assignments outside that range clamp."""
        return self._variables.volume.value

    @volume.setter
    def volume(self, value: float) -> None:
        self._variables.volume.value = max(0.0, min(100.0, value))

    # --------
    # Playback
    # --------

    def play(self, source: MediaSource | None = None, /) -> Self:
        """Play ``source``, or resume the current file when given none.

        Loading before the surface is drawable is allowed: the request
        is held and issued once mpv exists. Resuming a file
        :meth:`stop` unloaded loads it again, so play after stop
        starts the file over rather than doing nothing.

        Args:
            source (MediaSource | None): File or URL to load. Defaults
                to None, meaning keep the current one.

        Returns:
            ``self``, for chaining.
        """
        self._paused_by_user = False
        if source is not None:
            self._source = str(source)
            self._seek_target = None
            self._pending_seek = None
            self._stale_timeline = self._mpv is not None and self._file_loaded
            self._variables.duration.value = 0.0
            self._variables.position.value = 0.0
            self._variables.media_width.value = 0
            self._variables.media_height.value = 0
            if self._mpv is None:
                self._pending_source = self._source
            else:
                self._unloading = False
                self._file_loaded = True
                self._mpv.play(self._source)
        else:
            self._ensure_loaded()
        self._push_pause(False)
        self._reassert_policy()
        return self

    def pause(self) -> Self:
        """Pause playback deliberately.

        Returns:
            ``self``, for chaining.
        """
        self._set_paused(True)
        return self

    def resume(self) -> Self:
        """Resume playback deliberately.

        Returns:
            ``self``, for chaining.
        """
        self._set_paused(False)
        return self

    def toggle_pause(self) -> Self:
        """Pause if playing, resume if paused; deliberate either way.

        Returns:
            ``self``, for chaining.
        """
        self._set_paused(not self.paused)
        return self

    def stop(self) -> Self:
        """Stop playback and unload the file, discarding anything queued.

        A source waiting for the backend and a seek waiting for a
        timeline are both dropped. The display is left paused, and
        unpausing loads :attr:`source` again from the start.
        :attr:`duration` and :attr:`position` read 0 at once, so a
        :meth:`seek` issued straight after this is held and applied to
        that reload.

        Returns:
            ``self``, for chaining.
        """
        self._pending_source = None
        self._seek_target = None
        self._pending_seek = None
        self._paused_by_user = True
        self._push_pause(True)
        if self._mpv is not None:
            self._unloading = self._file_loaded
            self._file_loaded = False
            self._stale_timeline = self._unloading
            self._variables.duration.value = 0.0
            self._variables.position.value = 0.0
            self._variables.media_width.value = 0
            self._variables.media_height.value = 0
            self._mpv.command("stop")
        return self

    def seek(self, seconds: float, /) -> Self:
        """Seek to an absolute position, landing on it exactly.

        Exact seeking decodes forward from the preceding keyframe
        rather than snapping to it, so it costs a little more than
        mpv's default.

        While there is no timeline to seek in — before the surface has
        first been drawable, and between a :meth:`play` and mpv's first
        duration report for the new file — the request is held and
        replayed once the duration lands, the readout unmoved in the
        meantime, so ``play(path).seek(saved)`` works on a live backend
        as well as a fresh one. :meth:`play` with a new source and
        :meth:`stop` both discard a request still waiting, and a seek
        mpv refuses leaves the readout where it was.

        Args:
            seconds (float): Target position from the start of the file.
                Clamped to zero, and to the file's length once mpv has
                reported one — so a request held from before the file
                loaded is clamped against the real length when replayed.

        Returns:
            ``self``, for chaining.
        """
        target = max(0.0, seconds)
        duration = self.duration
        has_timeline = duration > 0.0  # 0.0 is "not reported yet", never a real length
        if has_timeline:
            target = min(target, duration)
        if self._mpv is None or not has_timeline:
            self._pending_seek = target
        else:
            with suppress(SystemError):
                self._mpv.seek(target, reference="absolute", precision="exact")
                self._begin_seek(target)
        return self

    def skip(self, delta: float, /) -> Self:
        """Seek ``delta`` seconds from the last reported position.

        Delegates to :meth:`seek`, so it clamps and lands exactly.
        Measured from the last position mpv reported, which lags the
        live one by at most a tick; repeated skips still accumulate
        exactly, because each records its target as the position the
        next reads. While :meth:`seek` is holding a request for a
        timeline — the load window — the held target is that recording,
        so skips measure from the hold instead of re-reading the same
        stale position and collapsing to the last delta.

        Args:
            delta (float): Seconds to move; negative goes backwards.

        Returns:
            ``self``, for chaining.
        """
        pending = self._pending_seek
        base = pending if pending is not None else self.position
        return self.seek(base + delta)
