"""The out-of-the-box media widget: both displays and the controls, as one.

:class:`MediaPlayer` owns an :class:`~tkfacade.media.ImageDisplay`, a
:class:`~tkfacade.media.VideoDisplay` built the first time a video is
asked for, and the control bar beneath them, switching displays by what
each ``play`` source resolves to. It wears
:class:`~tkfacade.media.AbstractMediaDisplay` itself, so driving the
player is driving a display — one contract, whichever medium is up.

Requires libmpv only when a video source arrives; a player that only
ever shows images never loads it.
"""

import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import ttk
from typing import TYPE_CHECKING, Literal, Self, Unpack, cast

from PIL import Image

from .._params import ImageOptions, MediaDisplayOptions, VideoOptions
from .._subscription import Subscription
from .._types import MediaSource
from .._utils import format_time
from ..events import Destroyed, Event
from ..observable import ObservableBool, ObservableFloat, ObservableInt
from ..widget import BaseWidget, Widget
from ._abstract import AbstractMediaDisplay, MediaVariables
from ._image import ImageInput
from ._image_display import ImageDisplay

if TYPE_CHECKING:
    from ._video import VideoDisplay

type PlayerSource = MediaSource | ImageInput
"""Anything a :class:`MediaPlayer` plays: a path or URL, or an image source.

The union of the two displays' worlds — :data:`~tkfacade.MediaSource`
for anything mpv streams, :data:`~tkfacade.ImageInput` for anything
:class:`~tkfacade.media.ImageWrapper` decodes — resolved to one of them
per source by :func:`_resolve_kind`.
"""

_GLYPH_PLAY: str = "▶"  # U+25B6 black right-pointing triangle
_GLYPH_PAUSE: str = "⏸"  # U+23F8 double vertical bar
_GLYPH_BACK: str = "⏪"  # U+23EA black left-pointing double triangle
_GLYPH_FORWARD: str = "⏩"  # U+23E9 black right-pointing double triangle
_GLYPH_STOP: str = "■"  # U+25A0 black square
_GLYPH_LOOP: str = "↻"  # U+21BB clockwise open circle arrow
_GLYPH_FIT: str = "⛶"  # U+26F6 square four corners
_GLYPH_AUDIBLE: str = "♪"  # U+266A eighth note
_GLYPH_MUTED: str = "✗"  # U+2717 ballot X


def _resolve_kind(source: PlayerSource, /) -> Literal["image", "video"]:
    """Decide which display a source belongs to.

    Anything that is not a path-or-string is an image by construction —
    bytes, a PIL image, a wrapper — since mpv takes only paths and
    URLs. A string naming no existing file is a URL or stream target,
    mpv's world, since PIL reads files only. An existing file is asked
    of PIL itself:     identifiable means the image display (animated
    formats included), and a file PIL
    cannot identify — every video container — goes to mpv.

    Args:
        source (PlayerSource): What a caller asked to play.

    Returns:
        ``"image"`` or ``"video"``.
    """
    if not isinstance(source, (str, Path)):
        return "image"
    path = Path(source)
    if not path.is_file():
        return "video"
    try:
        with Image.open(path):
            pass
    except OSError:
        return "video"
    return "image"


class MediaPlayer(Widget, AbstractMediaDisplay):
    """Both media displays and a control bar, switching by source.

    The out-of-the-box player: ``play`` resolves each source to an
    image or a video (:func:`_resolve_kind`), routes it to the display
    for that medium — the video display built lazily on the first video,
    so a player that never shows one never loads libmpv — and shows
    exactly one display above the bar. A source given at construction
    plays as soon as its display can draw.

    The player wears the timed-media contract itself and owns its own
    :class:`MediaVariables`, so a watch or a bar binding survives every
    switch: the settable four (``auto_size``, ``loop``, ``muted``,
    ``volume``) live here and are pushed into whichever display is
    active, and the rest mirror the active display through watches the
    switch re-seats. Before anything has played, the mirrors answer
    the constructed state — paused, empty, obstructed.

    The bar holds transport buttons, mode toggles, a seek bar, a
    clock, and volume controls, and is not configurable: a different
    bar means composing displays and controls yourself. Appearance:
    the bar is ttk (``TButton``, ``Toolbutton``, ``TScale``,
    ``TLabel`` on a ``TFrame``); the display area is the displays'
    own surfaces over the constructed background.

    Styling exception, per the classic-widget ruling (2026-08-27):
    the container is a classic frame and the bar keeps the base ttk
    styles, so a :class:`~tkfacade.Look` is held without acting here —
    filed for the future classic-widget study.
    """

    if TYPE_CHECKING:
        _tk: tk.Frame

    __slots__ = (
        "_active",
        "_auto_size_limit",
        "_back",
        "_bar",
        "_bar_watches",
        "_bridge_watches",
        "_forward",
        "_image_display",
        "_loop_button",
        "_mute_button",
        "_obstructed_pause",
        "_obstructed_shown",
        "_pending_seek",
        "_play",
        "_player_watches",
        "_scrubbing",
        "_seek_scale",
        "_seek_step",
        "_size_button",
        "_source",
        "_stop",
        "_time",
        "_variables",
        "_video_display",
        "_video_options",
        "_volume_label",
        "_volume_scale",
    )

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        source: PlayerSource | None = None,
        /,
        *,
        seek_step: float = 5.0,
        **options: Unpack[MediaDisplayOptions],
    ) -> None:
        """Build the composite, and start ``source`` if one is given.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the
                player is created inside.
            source (PlayerSource | None): What to play as soon as its
                display can draw. Defaults to None, meaning an empty
                player.
            seek_step (float): Seconds the skip buttons move by, in
                either direction. Defaults to 5.0.
            **options (Unpack[MediaDisplayOptions]): The union of both
                displays' options — see :class:`VideoDisplay` and
                :class:`ImageDisplay`. The shared ones govern the
                player and reach whichever display is active;
                ``hwdec`` reaches only the video display and
                ``default_delay`` only the image display. ``loop``
                defaults to False for either medium — one knob, one
                default, where the bare displays disagree. ``width``,
                ``height`` and ``auto_size`` apply to the display
                area, the bar keeping its own height beneath it. A
                whole :class:`~tkfacade.MediaPlayerOptions` unpacks here,
                its ``seek_step`` binding to the parameter above.

        Raises:
            OSError: If ``source`` is a video and libmpv is not
                installed — raised here, before anything is built.
        """
        kind = None if source is None else _resolve_kind(source)
        if kind == "video":
            from . import _mpv  # ruff: ignore[unused-import]
        auto_size = options.get("auto_size", False)
        background = options.get("background", "black")
        height = options.get("height", 540)
        volume = options.get("volume", 100.0)
        width = options.get("width", 960)
        self._auto_size_limit: tuple[int, int] | None = options.get("auto_size_limit")
        self._obstructed_pause: bool = options.get("obstructed_pause", False)
        self._seek_step: float = seek_step
        self._scrubbing: bool = False
        self._pending_seek: float | None = None
        self._source: PlayerSource | None = source
        self._active: ImageDisplay | VideoDisplay | None = None
        self._video_display: VideoDisplay | None = None
        self._bridge_watches: tuple[Subscription, ...] = ()
        self._obstructed_shown: bool = True

        master = self._as_master(parent)
        self._tk = tk.Frame(master, background=background, highlightthickness=0)
        self._tk.grid_rowconfigure(0, weight=1, minsize=height)
        self._tk.grid_columnconfigure(0, weight=1, minsize=width)
        self._tk.grid_rowconfigure(1, weight=0)

        self._video_options: VideoOptions = {
            "background": background,
            "height": height,
            "width": width,
        }
        if "hwdec" in options:
            self._video_options["hwdec"] = options["hwdec"]
        image_options: ImageOptions = {
            "background": background,
            "height": height,
            "width": width,
        }
        if "default_delay" in options:
            image_options["default_delay"] = options["default_delay"]
        self._image_display: ImageDisplay = ImageDisplay(self, **image_options)

        self._variables: MediaVariables = MediaVariables(
            auto_size=ObservableBool(auto_size),
            duration=ObservableFloat(0.0),
            loop=ObservableBool(options.get("loop", False)),
            media_height=ObservableInt(0),
            media_width=ObservableInt(0),
            muted=ObservableBool(False),
            obstructed=ObservableBool(True),
            paused=ObservableBool(True),
            position=ObservableFloat(0.0),
            volume=ObservableFloat(max(0.0, min(100.0, volume))),
        )
        self._player_watches: tuple[Subscription, ...] = (
            self._variables.auto_size.watch(self._on_auto_size),
            self._variables.loop.watch(self._on_loop),
            self._variables.muted.watch(self._on_muted),
            self._variables.volume.watch(self._on_volume),
            self._variables.obstructed.watch(self._reassert_obstructed),
        )

        self._bar = ttk.Frame(self._tk, padding=(6, 4))
        self._bar.grid(row=1, column=0, sticky="ew")
        self._bar.grid_columnconfigure(list(range(11)), weight=0)
        self._bar.grid_columnconfigure(6, weight=1)

        def transport(glyph: str, column: int, command: Callable[[], object]) -> ttk.Button:
            """Build one fixed-width transport button and place it."""
            button = ttk.Button(self._bar, text=glyph, width=3, command=command)
            button.grid(row=0, column=column, padx=1, sticky="ew")
            return button

        def toggle(glyph: str, column: int, observable: ObservableBool) -> ttk.Checkbutton:
            """Build one mode toggle driving ``observable`` and place it.

            ``Toolbutton`` draws a Checkbutton flat until it is on,
            then depressed — the whole affordance, since no label
            changes and no width jumps. ``onvalue``/``offvalue`` are
            explicit rather than trusting Checkbutton's 1/0 defaults
            to round-trip through a BooleanVar. The transport ride
            taken here is one of the five :meth:`_give_back` returns.
            """
            button = ttk.Checkbutton(
                self._bar,
                text=glyph,
                width=3,
                style="Toolbutton",
                variable=observable.transport_for(self._tk),
                onvalue=True,
                offvalue=False,
            )
            button.grid(row=0, column=column, padx=1, sticky="ew")
            return button

        self._play = transport(_GLYPH_PLAY, 0, self.toggle_pause)
        self._back = transport(_GLYPH_BACK, 1, lambda: self.skip(-self._seek_step))
        self._forward = transport(_GLYPH_FORWARD, 2, lambda: self.skip(self._seek_step))
        self._stop = transport(_GLYPH_STOP, 3, self.stop)
        self._loop_button = toggle(_GLYPH_LOOP, 4, self._variables.loop)

        self._time = ttk.Label(self._bar, text="0:00 / 0:00", width=12, anchor="e")
        self._time.grid(row=0, column=5, padx=1, sticky="ew")

        self._seek_scale = ttk.Scale(
            self._bar,
            from_=0.0,
            to=1.0,
            # cast: an ObservableFloat's transport is the DoubleVar typeshed's Scale wants
            variable=cast(tk.DoubleVar, self._variables.position.transport_for(self._tk)),
        )
        self._seek_scale.grid(row=0, column=6, padx=1, sticky="ew")

        self._size_button = toggle(_GLYPH_FIT, 7, self._variables.auto_size)
        self._mute_button = toggle(_GLYPH_AUDIBLE, 8, self._variables.muted)

        self._volume_scale = ttk.Scale(
            self._bar,
            from_=0.0,
            to=100.0,
            variable=cast(tk.DoubleVar, self._variables.volume.transport_for(self._tk)),
            length=80,
        )
        self._volume_scale.grid(row=0, column=9, padx=1, sticky="ew")

        self._volume_label = ttk.Label(self._bar, text="100%", width=5, anchor="e")
        self._volume_label.grid(row=0, column=10, padx=1, sticky="ew")

        self._route_events(self._bar)
        self._seek_scale.bind("<ButtonPress-1>", self._on_drag_start, add="+")
        self._seek_scale.bind("<ButtonRelease-1>", self._on_drag_end, add="+")

        self._bar_watches: tuple[Subscription, ...] = (
            self._variables.position.watch(self._on_position),
            self._variables.duration.watch(self._on_duration),
            self._variables.paused.watch(self._on_paused),
            self._variables.volume.watch(self._on_volume_shown),
            self._variables.muted.watch(self._on_muted_shown),
        )

        super().__init__()
        self.bind(Destroyed(), self._give_back)
        if source is not None:
            self.play(source)

    # ---------
    # Lifetime
    # ---------

    def _give_back(self, _event: Event) -> None:
        """Return what construction took; the player is done.

        The bar's five widgets took one transport ride each — the
        three toggles and the two scales — and every watch redraws or
        pushes into things now dying. Bound to
        :class:`~tkfacade.events.Destroyed` so the player's observables
        never count a dead bar among their riders; extra runs from the
        parts' own destroys release past zero, which the transport
        counting documents as harmless, the player being its
        observables' only rider.
        """
        for watch in (*self._bar_watches, *self._player_watches, *self._bridge_watches):
            watch.cancel()
        self._bridge_watches = ()
        self._variables.loop.release_transport()
        self._variables.auto_size.release_transport()
        self._variables.muted.release_transport()
        self._variables.position.release_transport()
        self._variables.volume.release_transport()

    # ----------
    # Switching
    # ----------

    def _activate(self, kind: Literal["image", "video"], /) -> ImageDisplay | VideoDisplay:
        """Make ``kind``'s display the one shown, bridged, and driven.

        The outgoing display is stopped and leaves the grid; the
        incoming one receives the player's settled settings — the
        settable four, the size limit, the obstruction policy — before
        its own reports bridge back up, so the mirrors never show a
        stale display's state. A no-op when ``kind`` is already up.

        Args:
            kind (Literal["image", "video"]): Which display to seat.

        Returns:
            The display now active.
        """
        display: ImageDisplay | VideoDisplay
        if kind == "image":
            display = self._image_display
        else:
            if self._video_display is None:
                from ._video import VideoDisplay

                self._video_display = VideoDisplay(self, **self._video_options)
            display = self._video_display
        if display is self._active:
            return display
        outgoing, self._active = self._active, display
        for watch in self._bridge_watches:
            watch.cancel()
        self._bridge_watches = ()
        if outgoing is not None:
            outgoing.stop()
            outgoing.grid_remove()
        display.auto_size = self.auto_size
        display.loop = self.loop
        display.muted = self.muted
        display.volume = self.volume
        display.auto_size_limit = self._auto_size_limit
        display.obstructed_pause = self._obstructed_pause
        display.grid(row=0, column=0, sticky="nsew")
        held = display.variables
        self._bridge_watches = (
            held.position.watch(self._bridge_position),
            held.duration.watch(self._bridge_duration),
            held.paused.watch(self._bridge_paused),
            held.media_width.watch(self._bridge_media_width),
            held.media_height.watch(self._bridge_media_height),
            held.obstructed.watch(self._bridge_obstructed),
        )
        return display

    # -------------------------------
    # The bridge: display -> mirrors
    # -------------------------------

    def _bridge_position(self, value: float, /) -> None:
        """Mirror the active display's position, unless a drag holds the thumb."""
        if not self._scrubbing:
            self._variables.position.value = value

    def _bridge_duration(self, value: float, /) -> None:
        """Mirror the active display's duration."""
        self._variables.duration.value = value

    def _bridge_paused(self, value: bool, /) -> None:
        """Mirror the active display's pause state."""
        self._variables.paused.value = value

    def _bridge_media_width(self, value: int, /) -> None:
        """Mirror the active display's media width."""
        self._variables.media_width.value = value

    def _bridge_media_height(self, value: int, /) -> None:
        """Mirror the active display's media height."""
        self._variables.media_height.value = value

    def _bridge_obstructed(self, value: bool, /) -> None:
        """Mirror the active display's obstruction, and remember the truth."""
        self._obstructed_shown = value
        self._variables.obstructed.value = value

    def _reassert_obstructed(self, value: bool, /) -> None:
        """Put the bridged truth back whenever anything else writes the mirror.

        The bundle documents ``obstructed`` as read-only; the display's
        own guard protects its observable, and this one protects the
        player's copy the same way.
        """
        if value != self._obstructed_shown:
            self._variables.obstructed.value = self._obstructed_shown

    # ------------------------------------
    # The settable four: player -> display
    # ------------------------------------

    def _on_auto_size(self, value: bool, /) -> None:
        """Push ``auto_size`` into the active display, if one is up."""
        if self._active is not None:
            self._active.auto_size = value

    def _on_loop(self, value: bool, /) -> None:
        """Push ``loop`` into the active display, if one is up."""
        if self._active is not None:
            self._active.loop = value

    def _on_muted(self, value: bool, /) -> None:
        """Push ``muted`` into the active display, if one is up."""
        if self._active is not None:
            self._active.muted = value

    def _on_volume(self, value: float, /) -> None:
        """Clamp ``volume`` on write, then push it into the active display.

        Clamps in place, since a widget bound to the observable — the
        bar's slider is — can put anything there.
        """
        clamped = max(0.0, min(100.0, value))
        if clamped != value:
            self._variables.volume.value = clamped
            return
        if self._active is not None:
            self._active.volume = clamped

    # --------
    # The bar
    # --------

    def _on_drag_start(self, _event: tk.Event[tk.Misc]) -> None:
        """Close the position bridge so reports do not fight the dragging thumb."""
        self._scrubbing = True

    def _on_drag_end(self, _event: tk.Event[tk.Misc]) -> None:
        """Seek to wherever the thumb was released, and reopen the bridge."""
        self._scrubbing = False
        self.seek(self._variables.position.value)

    def _on_position(self, _value: float, /) -> None:
        """Follow the position onto the time label."""
        self._refresh_time()

    def _on_duration(self, _value: float, /) -> None:
        """Rescale the seek bar to the new length, and refresh the label.

        The 0.1 floor keeps ``to`` above ``from_`` while no duration
        is known, so the scale never spans an empty range.
        """
        self._seek_scale["to"] = max(self.duration, 0.1)
        self._refresh_time()

    def _refresh_time(self) -> None:
        """Redraw the time label from the current position and duration."""
        self._time["text"] = f"{format_time(self.position)} / {format_time(self.duration)}"

    def _on_paused(self, value: bool, /) -> None:
        """Follow the paused flag onto the play button's glyph."""
        self._play["text"] = _GLYPH_PLAY if value else _GLYPH_PAUSE

    def _on_volume_shown(self, _value: float, /) -> None:
        """Follow the volume onto its readout."""
        self._refresh_volume()

    def _on_muted_shown(self, _value: bool, /) -> None:
        """Follow the mute flag onto its button's glyph."""
        self._refresh_volume()

    def _refresh_volume(self) -> None:
        """Redraw the percentage readout, and the mute button's glyph.

        The percentage shows the level muted or not — a display's mute
        leaves it untouched, so it stays the number unmuting restores.
        Mute is legible twice over instead: the glyph changes, and as
        a Toolbutton the button also stays depressed.
        """
        self._volume_label["text"] = f"{round(self.volume)}%"
        self._mute_button["text"] = _GLYPH_MUTED if self.muted else _GLYPH_AUDIBLE

    # -----
    # State
    # -----

    @property
    def variables(self) -> MediaVariables:
        """The player's own live observables; see :class:`MediaVariables`.

        The mirrors of whichever display is active, so a watch taken
        here survives every switch — the display bundles behind them
        are not handed out.
        """
        return self._variables

    @property
    def source(self) -> PlayerSource | None:
        """What was last given to the constructor or :meth:`play`, or None."""
        return self._source

    @property
    def kind(self) -> Literal["image", "video"] | None:
        """The medium currently seated, or None before anything has played."""
        if self._active is None:
            return None
        return "image" if self._active is self._image_display else "video"

    @property
    def seek_step(self) -> float:
        """Seconds the skip buttons move by, in either direction."""
        return self._seek_step

    @seek_step.setter
    def seek_step(self, value: float) -> None:
        self._seek_step = value

    @property
    def width(self) -> int:
        """The width the display area asks for, in pixels; the bar rides beneath.

        A request, not a size: a weighted master cell may grant more,
        and an active display's own request — ``auto_size`` grows it —
        stretches the cell past this floor.
        """
        return int(self._tk.grid_columnconfigure(0)["minsize"])

    @width.setter
    def width(self, value: int) -> None:
        self._tk.grid_columnconfigure(0, minsize=value)

    @property
    def height(self) -> int:
        """The height the display area asks for, in pixels; see :attr:`width`."""
        return int(self._tk.grid_rowconfigure(0)["minsize"])

    @height.setter
    def height(self, value: int) -> None:
        self._tk.grid_rowconfigure(0, minsize=value)

    @property
    def loop(self) -> bool:
        """Whether the current media restarts when it reaches the end.

        Takes effect immediately, mid-playback included, and holds
        across switches: the player's own setting, pushed into
        whichever display is active.
        """
        return self._variables.loop.value

    @loop.setter
    def loop(self, value: bool) -> None:
        self._variables.loop.value = value

    @property
    def muted(self) -> bool:
        """Whether audio is silenced, independently of :attr:`volume`.

        Held by the player across switches; inert while an image is
        up, an image having no audio.
        """
        return self._variables.muted.value

    @muted.setter
    def muted(self, value: bool) -> None:
        self._variables.muted.value = value

    @property
    def media_width(self) -> int:
        """The playing media's own display width; 0 until one is known."""
        return self._variables.media_width.value

    @property
    def media_height(self) -> int:
        """The playing media's own display height; 0 until one is known."""
        return self._variables.media_height.value

    @property
    def auto_size(self) -> bool:
        """Whether the display area asks for the size of whatever is playing.

        The player's own setting, pushed into whichever display is
        active; the active display's request stretches the display
        cell, the bar keeping its own height beneath. Only ever a
        request, as on the bare displays.
        """
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
        if self._active is not None:
            self._active.auto_size_limit = value

    @property
    def obstructed_pause(self) -> bool:
        """Whether playback pauses while the active display's surface is hidden.

        The player's own policy, applied to whichever display is
        active; the surfaces are unmapped when covered either way.
        """
        return self._obstructed_pause

    @obstructed_pause.setter
    def obstructed_pause(self, policy: bool) -> None:
        self._obstructed_pause = policy
        if self._active is not None:
            self._active.obstructed_pause = policy

    @property
    def position(self) -> float:
        """Playback position in seconds; setting it seeks."""
        return self._variables.position.value

    @position.setter
    def position(self, seconds: float) -> None:
        self.seek(seconds)

    @property
    def duration(self) -> float:
        """Length of the current media in seconds; 0.0 until a length is known."""
        return self._variables.duration.value

    @property
    def paused(self) -> bool:
        """Whether playback is paused, however it came to be.

        True on an empty player: nothing is playing before the first
        source arrives.
        """
        return self._variables.paused.value

    @paused.setter
    def paused(self, value: bool) -> None:
        if value:
            self.pause()
        else:
            self.resume()

    @property
    def volume(self) -> float:
        """Volume from 0.0 to 100.0; assignments outside that range clamp.

        Held by the player across switches, so a level set over a
        video still holds after an image and the video after that.
        """
        return self._variables.volume.value

    @volume.setter
    def volume(self, value: float) -> None:
        self._variables.volume.value = max(0.0, min(100.0, value))

    # --------
    # Playback
    # --------

    def play(self, source: PlayerSource | None = None, /) -> Self:
        """Play ``source`` on the display its kind resolves to, or resume.

        A new source seats its medium's display — built on the spot
        for the first video — stopping and hiding the other; the
        player's held settings ride into it. With no source, the
        active display resumes whatever it holds; an empty player
        with nothing recorded does nothing.

        Args:
            source (PlayerSource | None): A path or URL, or an image
                source. Defaults to None, meaning keep the current one.

        Returns:
            ``self``, for chaining.

        Raises:
            OSError: If ``source`` is the first video and libmpv is
                not installed.
        """
        if source is None:
            if self._active is not None:
                self._active.play()
            return self
        self._source = source
        display = self._activate(_resolve_kind(source))
        display.play(source)  # type: ignore[arg-type]
        pending, self._pending_seek = self._pending_seek, None
        if pending is not None:
            display.seek(pending)
        return self

    def pause(self) -> Self:
        """Pause playback deliberately; nothing on an empty player.

        Returns:
            ``self``, for chaining.
        """
        if self._active is not None:
            self._active.pause()
        return self

    def resume(self) -> Self:
        """Resume playback deliberately; nothing on an empty player.

        Returns:
            ``self``, for chaining.
        """
        if self._active is not None:
            self._active.resume()
        return self

    def toggle_pause(self) -> Self:
        """Pause if playing, resume if paused; deliberate either way.

        Returns:
            ``self``, for chaining.
        """
        if self._active is not None:
            self._active.toggle_pause()
        return self

    def stop(self) -> Self:
        """Stop playback and unload the media, discarding anything queued.

        Returns:
            ``self``, for chaining.
        """
        self._pending_seek = None
        if self._active is not None:
            self._active.stop()
        return self

    def seek(self, seconds: float, /) -> Self:
        """Seek to an absolute position, landing on it exactly.

        Delegates to the active display, which holds a request while
        there is no timeline; on an empty player the request is held
        here and rides the first :meth:`play`.

        Args:
            seconds (float): Target position from the start of the
                media. Clamped to zero, and to the length once one is
                known.

        Returns:
            ``self``, for chaining.
        """
        if self._active is None:
            self._pending_seek = max(0.0, seconds)
            return self
        self._active.seek(seconds)
        return self

    def skip(self, delta: float, /) -> Self:
        """Seek ``delta`` seconds from the current position.

        Delegates to :meth:`seek`, so it clamps and lands exactly, and
        a request held on an empty player is the base the next skip
        measures from.

        Args:
            delta (float): Seconds to move; negative goes backwards.

        Returns:
            ``self``, for chaining.
        """
        if self._active is None:
            base = self._pending_seek if self._pending_seek is not None else 0.0
            return self.seek(base + delta)
        self._active.skip(delta)
        return self
