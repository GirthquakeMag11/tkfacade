"""The timed-media contract: what a display of media with a timeline offers.

An :class:`AbstractMediaDisplay` plays media that has a position in it,
with :class:`MediaVariables` publishing that state as observables to
watch. It is a face, not a widget: :class:`~tkfacade.media.ImageDisplay` and
:class:`~tkfacade.media.VideoDisplay` wear it over
:class:`~tkfacade.widget.Surface`, and :class:`~tkfacade.media.MediaPlayer`
wears it over a composite holding both, so code holding the contract
drives any of them without knowing which.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

from .._types import MediaSource
from ..observable import ObservableBool, ObservableFloat, ObservableInt

if TYPE_CHECKING:
    import tkinter as tk


@dataclass(slots=True, frozen=True, kw_only=True, eq=False)
class MediaVariables:
    """A display's playback state, as observables to watch.

    The live observables, not copies; bundles compare by identity.
    Writing one changes what anything watching it sees, not what the
    display is doing: read state through the display's properties,
    change it through its methods, and use these to watch. The
    exceptions are :attr:`auto_size`, :attr:`loop`, :attr:`muted` and
    :attr:`volume`, which a display watches and acts on, so writing one
    is the same as assigning the matching property.

    Attributes:
        auto_size (ObservableBool): Whether the display asks for the
            size of whatever is playing.
        duration (ObservableFloat): Length of the current media in
            seconds; 0.0 until a length is known.
        loop (ObservableBool): Whether the current media repeats when
            it ends.
        media_height (ObservableInt): The media's own display height in
            pixels; 0 until one is known. Not the widget's height — see
            :attr:`AbstractMediaDisplay.height` for that.
        media_width (ObservableInt): The media's own display width in
            pixels; 0 until one is known.
        muted (ObservableBool): Whether audio is silenced, independently
            of :attr:`volume`, which keeps its level.
        obstructed (ObservableBool): Whether the surface is suppressed
            rather than drawing — the surface's own published channel.
            Read-only: the surface machinery restores its own value
            over any other write.
        paused (ObservableBool): Whether playback is paused.
        position (ObservableFloat): Playback position in seconds.
        volume (ObservableFloat): Volume from 0.0 to 100.0.
    """

    auto_size: ObservableBool
    duration: ObservableFloat
    loop: ObservableBool
    media_height: ObservableInt
    media_width: ObservableInt
    muted: ObservableBool
    obstructed: ObservableBool
    paused: ObservableBool
    position: ObservableFloat
    volume: ObservableFloat


class AbstractMediaDisplay(ABC):
    """Something playing media with a timeline, driven entirely from code.

    Playback is driven through the methods and properties here and
    watched through the observables in :attr:`variables`; there are no
    controls. Anything set before the display can draw is applied once it
    can, so a caller may configure a display and lay it out in either
    order.

    The face every player of timed media wears, not a widget of its
    own: :class:`~tkfacade.media.ImageDisplay` and
    :class:`~tkfacade.media.VideoDisplay` wear it over
    :class:`~tkfacade.widget.Surface` — whose drawing area is suppressed
    whenever Tk reports something in front of it, with
    :attr:`obstructed_pause` deciding whether playback stops too — and
    :class:`~tkfacade.media.MediaPlayer` wears it over a composite holding
    both displays. Wearers supply the widget half the face reads:
    ``_tk`` and the ``width``/``height`` size request that
    :meth:`_resize_to_media` writes.
    """

    if TYPE_CHECKING:
        # tk.Frame exactly: sibling bases must agree on an attribute's type, not merely overlap
        _tk: tk.Frame

        @property
        def width(self) -> int:
            """The width the wearer asks its master for, in pixels."""

        @width.setter
        def width(self, value: int) -> None: ...

        @property
        def height(self) -> int:
            """The height the wearer asks its master for, in pixels."""

        @height.setter
        def height(self, value: int) -> None: ...

    # without this subclasses keep no __slots__ and silently gain a __dict__
    __slots__ = ()

    def _resize_to_media(self) -> None:
        """Ask for the media's own size, scaled down to fit the size limit.

        Both axes take the same factor, so the box keeps the media's
        shape, and the scale is never up. Does nothing until both axes
        are known, so a display with auto-sizing on keeps its
        constructed size until something plays.
        """
        width = self.media_width
        height = self.media_height
        if width <= 0 or height <= 0:
            return
        limit_width, limit_height = self.auto_size_limit or (
            self._tk.winfo_screenwidth(),
            self._tk.winfo_screenheight(),
        )
        factor = min(1.0, limit_width / width, limit_height / height)
        self.width = max(1, round(width * factor))
        self.height = max(1, round(height * factor))

    # -----
    # State
    # -----

    @property
    @abstractmethod
    def variables(self) -> MediaVariables:
        """The live observables tracking playback; see :class:`MediaVariables`."""

    @property
    @abstractmethod
    def loop(self) -> bool:
        """Whether the current media restarts when it reaches the end.

        Takes effect immediately, mid-playback included, and repeats
        forever.
        """

    @loop.setter
    @abstractmethod
    def loop(self, value: bool) -> None:
        """Set whether the current media restarts when it reaches the end.

        Args:
            value (bool): True to repeat forever, False to stop at the
                end.
        """

    @property
    @abstractmethod
    def muted(self) -> bool:
        """Whether audio is silenced, independently of :attr:`volume`.

        Unmuting restores exactly the level :attr:`volume` reports.
        """

    @muted.setter
    @abstractmethod
    def muted(self, value: bool) -> None:
        """Silence the audio, or restore it at its existing level.

        Args:
            value (bool): True to silence, False to restore.
        """

    @property
    @abstractmethod
    def media_width(self) -> int:
        """The playing media's own display width in pixels; 0 until one is known.

        The media's width, not the widget's: :attr:`width` is what the
        display asks its master for, and :attr:`auto_size` keeps the two
        in step.
        """

    @property
    @abstractmethod
    def media_height(self) -> int:
        """The playing media's own display height in pixels; 0 until one is known.

        See :attr:`media_width`.
        """

    @property
    @abstractmethod
    def auto_size(self) -> bool:
        """Whether the display asks for the size of whatever is playing.

        With this on, :attr:`width` and :attr:`height` follow the media's
        own display size, scaled down to fit :attr:`auto_size_limit` when
        larger; both axes take the same factor, so the box keeps the
        media's shape. Turning it off leaves the display at whatever size
        it has reached, not the size it was built with.

        Only ever a *request*: a master with a weighted cell may hand the
        display more, and a toplevel with explicit geometry will not
        resize itself to suit, so a window meant to follow the media has
        to watch :attr:`variables` and set its own geometry.
        """

    @auto_size.setter
    @abstractmethod
    def auto_size(self, value: bool) -> None:
        """Start or stop following the size of whatever is playing.

        Args:
            value (bool): True to follow the media's size, False to keep
                the size already reached.
        """

    @property
    @abstractmethod
    def auto_size_limit(self) -> tuple[int, int] | None:
        """The largest size auto-sizing may ask for, or None for the screen."""

    @auto_size_limit.setter
    @abstractmethod
    def auto_size_limit(self, value: tuple[int, int] | None) -> None:
        """Cap what auto-sizing may ask for, taking effect immediately.

        Args:
            value (tuple[int, int] | None): Maximum width and height in
                pixels, or None for the screen's.
        """

    @property
    @abstractmethod
    def obstructed_pause(self) -> bool:
        """Whether playback pauses while the surface is suppressed.

        Only the pausing is optional; the surface is unmapped whenever
        something is in front of it either way. Takes effect immediately:
        turning it on while the surface is already hidden pauses
        playback, and turning it off resumes it unless the caller paused
        deliberately too.
        """

    @obstructed_pause.setter
    @abstractmethod
    def obstructed_pause(self, policy: bool) -> None:
        """Decide whether a suppressed surface also stops playing.

        Args:
            policy (bool): True to pause while hidden, False to play on.
        """

    @property
    @abstractmethod
    def position(self) -> float:
        """Playback position in seconds; setting it seeks."""

    @position.setter
    @abstractmethod
    def position(self, seconds: float) -> None:
        """Seek to an absolute position; delegates to :meth:`seek`.

        Args:
            seconds (float): Target position from the start of the media.
        """

    @property
    @abstractmethod
    def duration(self) -> float:
        """Length of the current media in seconds.

        0.0 until a length is known, and permanently 0.0 for a medium
        with no timeline — a still image, which has no position to be
        at.
        """

    @property
    @abstractmethod
    def paused(self) -> bool:
        """Whether playback is paused, however it came to be.

        A pause the caller asked for outlives the surface being hidden
        and shown again; one :attr:`obstructed_pause` imposed does not.
        """

    @paused.setter
    @abstractmethod
    def paused(self, value: bool) -> None:
        """Pause or resume deliberately, as :meth:`pause` and :meth:`resume` do.

        Args:
            value (bool): True to pause, False to resume.
        """

    @property
    @abstractmethod
    def volume(self) -> float:
        """Volume from 0.0 to 100.0; assignments outside that range clamp.

        Silencing without losing the level is :attr:`muted`.
        """

    @volume.setter
    @abstractmethod
    def volume(self, value: float) -> None:
        """Set the volume, clamping to the range.

        Args:
            value (float): Level from 0.0 to 100.0.
        """

    @property
    def position_locked(self) -> bool:
        """Whether to withhold the reported position from the variable.

        An override hook, and why it is public: a subclass with its own
        seek bar returns True while the user drags it, so the display
        does not fight the thumb. Always False here; a bare display has
        nothing to drag.
        """
        return False

    # --------
    # Playback
    # --------

    @abstractmethod
    def play(self, source: MediaSource | None = None, /) -> Self:
        """Play ``source``, or resume the current media when given none.

        Loading before the display can draw is allowed: the request is
        held and issued once it can. Resuming media :meth:`stop`
        unloaded loads it again, so play after stop starts it over
        rather than doing nothing.

        Args:
            source (MediaSource | None): File or URL to load. Defaults to
                None, meaning keep the current one.

        Returns:
            ``self``, for chaining.
        """

    @abstractmethod
    def pause(self) -> Self:
        """Pause playback deliberately.

        Returns:
            ``self``, for chaining.
        """

    @abstractmethod
    def resume(self) -> Self:
        """Resume playback deliberately.

        Returns:
            ``self``, for chaining.
        """

    @abstractmethod
    def toggle_pause(self) -> Self:
        """Pause if playing, resume if paused; deliberate either way.

        Returns:
            ``self``, for chaining.
        """

    @abstractmethod
    def stop(self) -> Self:
        """Stop playback and unload the media, discarding anything queued.

        A source waiting to be loaded and a seek waiting for a timeline
        are both dropped. The display is left paused with
        :attr:`duration` and :attr:`position` reading 0, and starting
        playback again loads the same media from the start.

        Returns:
            ``self``, for chaining.
        """

    @abstractmethod
    def seek(self, seconds: float, /) -> Self:
        """Seek to an absolute position, landing on it exactly.

        While there is no timeline to seek in, the request is held and
        replayed once one arrives, the readout unmoved in the meantime,
        so ``play(path).seek(saved)`` works whether or not anything is
        loaded yet. :meth:`play` with a new source and :meth:`stop` both
        discard a request still waiting.

        Args:
            seconds (float): Target position from the start of the media.
                Clamped to zero, and to :attr:`duration` once a length is
                known — so a request held from before the media loaded is
                clamped against the real length when replayed.

        Returns:
            ``self``, for chaining.
        """

    @abstractmethod
    def skip(self, delta: float, /) -> Self:
        """Seek ``delta`` seconds from the current position.

        Delegates to :meth:`seek`, so it clamps and lands exactly.
        Repeated skips accumulate exactly, a held request included, and
        so never collapse to the last delta.

        Args:
            delta (float): Seconds to move; negative goes backwards.

        Returns:
            ``self``, for chaining.
        """
