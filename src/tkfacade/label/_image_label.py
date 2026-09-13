"""The ImageLabel wrapper: the image-only half of the split Label.

A :class:`ImageLabel` is a ``ttk.Label`` that holds nothing but an
image — still or animated — with the playback and transformation
surface the split took over from the old ``Label.image`` view. The
image state lives on the label itself, so every accessor and method
here reads and drives one widget directly.
"""

import tkinter as tk
from collections.abc import Iterator
from tkinter import ttk
from typing import TYPE_CHECKING, Self

from ..events import Destroyed, Event
from ..look import Look
from ..media import (
    ImageInput,
    ImageWrapper,
    PhotoImage,
    flip_horizontal,
    flip_vertical,
    rotate,
    rotate_left,
    scale,
)
from ..widget import BaseWidget, Widget


class ImageLabel(Widget):
    """A themed Tk label displaying nothing but an image.

    Every frame is decoded up front and held for the label's lifetime,
    and playback loops. A still image, and a label with no image at
    all, are both safe to drive: playback and the transformations are
    no-ops, and the dimensions read 0.

    Each transformation replaces the image with its result and
    re-decodes from it, so an animation's frames are transformed
    together and playback stops and rewinds to the transformed first
    frame.

    Appearance comes from the ``TLabel`` style rather than from
    per-widget options, as for any themed label.
    """

    if TYPE_CHECKING:
        _tk: ttk.Label

    __slots__ = (
        "_default_delay",
        "_delays",
        "_frames",
        "_index",
        "_job",
        "_playing",
        "_wrapper",
    )

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        /,
        image: ImageInput | None = None,
        *,
        default_delay: int = 100,
        look: Look | None = None,
    ) -> None:
        """Create the label and display ``image`` in it.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the label
                is created inside.
            image (ImageInput | None): The image source; anything
                :class:`~tkfacade.media.ImageWrapper` accepts. Defaults to
                None, leaving the label imageless.
            default_delay (int): Milliseconds to hold an animation frame
                declaring no duration of its own. Defaults to 100.
            look (Look | None): The look to wear from the start; see
                :attr:`~tkfacade.widget.Widget.look`. Defaults to None,
                the library's base style.
        """
        self._default_delay: int = default_delay
        self._delays: list[int] = []
        self._frames: list[PhotoImage] = []
        self._index: int = 0
        self._job: str | None = None
        self._playing: bool = False
        self._wrapper: ImageWrapper | None = None
        self._tk = ttk.Label(self._as_master(parent))
        if image is not None:
            self.set(image)
        super().__init__()
        self.bind(Destroyed(), self._on_destroy)
        if look is not None:
            self.look = look

    def _on_destroy(self, _event: Event) -> None:
        """Cancel any pending tick once the label is gone."""
        self.pause()

    def _tick(self) -> None:
        """Display the current frame and schedule the next."""
        self._tk.configure(image=self._frames[self._index])
        delay = self._delays[self._index]
        self._index = (self._index + 1) % len(self._frames)
        self._job = self._tk.after(delay, self._tick)

    @property
    def wrapper(self) -> ImageWrapper | None:
        """The wrapper currently on display, or None when there is no image.

        The adapter the media functions answer with, for code that needs
        the PIL object or the Tk handle behind it. A caller who only
        wants to display and transform an image never reaches for it.
        """
        return self._wrapper

    @property
    def width(self) -> int:
        """The displayed image's width in pixels; 0 when there is none."""
        wrapper = self._wrapper
        return wrapper.width if wrapper is not None else 0

    @property
    def height(self) -> int:
        """The displayed image's height in pixels; 0 when there is none."""
        wrapper = self._wrapper
        return wrapper.height if wrapper is not None else 0

    @property
    def format(self) -> str | None:
        """The format decoded from, or None when unset or there is no image."""
        wrapper = self._wrapper
        return wrapper.format if wrapper is not None else None

    @property
    def playing(self) -> bool:
        """Whether playback is running."""
        return self._playing

    @property
    def index(self) -> int:
        """Index of the frame the next tick will display."""
        return self._index

    def set(self, arg: ImageInput | None, /) -> None:
        """Display ``arg`` in place of whatever is there now.

        Args:
            arg (ImageInput | None): The new image source; anything
                :class:`~tkfacade.media.ImageWrapper` accepts. None clears the
                label's image.
        """
        self._wrapper = ImageWrapper(arg) if arg is not None else None
        self.refresh()

    def refresh(self) -> None:
        """Re-decode every frame from the current image and rewind.

        Playback stops, the frame cache is rebuilt, and the first frame
        is shown.
        """
        if self._playing:
            self.pause()
        self._frames.clear()
        self._delays.clear()
        if self._wrapper is not None:
            for animframe in self._wrapper.iter_frames(self._default_delay, master=self._tk):
                self._frames.append(animframe.frame)
                self._delays.append(animframe.delay)
            if not self._frames:
                self._frames.append(self._wrapper.photo_for(self._tk))
                self._delays.append(self._default_delay)
        self._index = 0
        self._tk.configure(image=self._frames[0] if self._frames else "")

    def iter_frames(self) -> Iterator[PhotoImage]:
        """Iterate the decoded frames, in playback order.

        Walks a snapshot of the cache :meth:`refresh` built, so it is
        safe to hold across a refresh. A still image yields one frame,
        and a label with no image yields none.

        Yields:
            Each frame as a :class:`~tkfacade.media.PhotoImage`.
        """
        return iter(tuple(self._frames))

    def play(self) -> Self:
        """Start looping playback.

        An image of fewer than two frames never plays, and calling this
        while already playing does nothing.

        Returns:
            ``self``, for chaining.
        """
        if not self._playing and len(self._frames) > 1:
            self._playing = True
            self._tick()
        return self

    def pause(self) -> Self:
        """Stop playback on the current frame.

        Returns:
            ``self``, for chaining.
        """
        self._playing = False
        if self._job is not None:
            self._tk.after_cancel(self._job)
            self._job = None
        return self

    def stop(self) -> Self:
        """Stop playback and rewind to the first frame.

        Returns:
            ``self``, for chaining.
        """
        self.pause()
        self._index = 0
        if self._frames:
            self._tk.configure(image=self._frames[0])
        return self

    def flip_horizontal(self) -> None:
        """Mirror the displayed image left-to-right."""
        if self._wrapper is not None:
            self._wrapper = flip_horizontal(self._wrapper)
            self.refresh()

    def flip_vertical(self) -> None:
        """Mirror the displayed image top-to-bottom."""
        if self._wrapper is not None:
            self._wrapper = flip_vertical(self._wrapper)
            self.refresh()

    def rotate(self, angle: int, /) -> None:
        """Rotate the displayed image clockwise; see :func:`~tkfacade.media.rotate`.

        Args:
            angle (int): Degrees clockwise.
        """
        if self._wrapper is not None:
            self._wrapper = rotate(self._wrapper, angle)
            self.refresh()

    def rotate_right(self, angle: int, /) -> None:
        """Rotate the displayed image clockwise; delegates to :meth:`rotate`.

        Args:
            angle (int): Degrees clockwise.
        """
        self.rotate(angle)

    def rotate_left(self, angle: int, /) -> None:
        """Rotate the displayed image counter-clockwise.

        Args:
            angle (int): Degrees counter-clockwise.
        """
        if self._wrapper is not None:
            self._wrapper = rotate_left(self._wrapper, angle)
            self.refresh()

    def scale(self, percent: int | float, /) -> None:
        """Resize the displayed image; see :func:`~tkfacade.media.scale`.

        Args:
            percent (int | float): Target size as a percentage of the
                current one.
        """
        if self._wrapper is not None:
            self._wrapper = scale(self._wrapper, percent)
            self.refresh()
