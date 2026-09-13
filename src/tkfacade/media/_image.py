"""Image loading, transformation, and display.

The transformations and icon helpers are the pure-PIL half. Each takes
an :data:`ImageInput` — a path, bytes, a PIL image, or the wrapper an
earlier call answered with — and returns a *new* image, so they compose
without a caller ever unwrapping one and none of them mutates a source.
An animation passes through whole, every playback frame transformed and
each frame's delay kept. :class:`ImageWrapper` is what they hand back
and what the widgets hold.

Tk keeps only a weak reference to an image, so a wrapper dropped on the
Python side silently vanishes from the widget showing it. The widgets
here hold their own; code handing Tk an image directly has to.
"""

import io
import tkinter as tk
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Final, NamedTuple, Self, cast

from PIL import Image, ImageOps, ImageSequence, ImageTk

from .._types import Side

type ImageInput = str | Path | bytes | Image.Image | ImageWrapper
"""Anything the image utilities here accept as a source.

A *source*, not an image: a filesystem path, encoded bytes, an
already-open PIL image, or an :class:`ImageWrapper` from an earlier
call — which is what lets the transformations below compose without a
caller ever unwrapping one. Distinct from :data:`~tkfacade.ImageSpec`, which
is the state-keyed form a ttk *style* takes.
"""

NEAREST: Final[Image.Resampling] = Image.Resampling.NEAREST
"""Fastest. Use for pixel art and masks."""

BOX: Final[Image.Resampling] = Image.Resampling.BOX
"""Fast. Integer-factor downscale."""

BILINEAR: Final[Image.Resampling] = Image.Resampling.BILINEAR
"""Fast. Use for interactive previews and real time resizing."""

HAMMING: Final[Image.Resampling] = Image.Resampling.HAMMING
"""Medium. Use for downscaling where quality is *less* significant."""

BICUBIC: Final[Image.Resampling] = Image.Resampling.BICUBIC
"""Medium. Use for upscaling and rotation."""

LANCZOS: Final[Image.Resampling] = Image.Resampling.LANCZOS
"""Slow. Use for downscaling where quality is *more* significant."""

MIN_FRAME_DELAY: Final[int] = 20
"""Floor for an animation frame delay in milliseconds; Tk cannot keep up below it."""

_EXIF_ORIENTATION: Final[int] = 0x0112
"""EXIF tag holding the orientation an image should be rotated to on display."""

_EXIF_TRANSPOSES: Final[dict[int, Image.Transpose]] = {
    2: Image.Transpose.FLIP_LEFT_RIGHT,
    3: Image.Transpose.ROTATE_180,
    4: Image.Transpose.FLIP_TOP_BOTTOM,
    5: Image.Transpose.TRANSPOSE,
    6: Image.Transpose.ROTATE_270,
    7: Image.Transpose.TRANSVERSE,
    8: Image.Transpose.ROTATE_90,
}
"""Transpose undoing each EXIF orientation value; 1 (and unknown) is identity."""

_SIXTEEN_BIT: Final[frozenset[str]] = frozenset({"I;16", "I;16B", "I;16L", "I;16N"})
"""Modes holding unsigned 16-bit samples, one per byte order PIL distinguishes."""

_UNBOUNDED: Final[frozenset[str]] = frozenset({"I", "F"})
"""Modes whose sample range the format does not fix: 32-bit signed and 32-bit float."""

PhotoImage = ImageTk.PhotoImage
"""Tk-side image handle; Pillow's, re-exported so callers need not import it.

A plain re-export, not a ``type`` alias: it is also constructed, and a
PEP 695 alias is not callable.
"""


class AnimFrame(NamedTuple):
    """One animation frame, paired with how long to hold it.

    Attributes:
        frame (PhotoImage): The rendered frame.
        delay (int): Milliseconds to display it; as produced by
            :meth:`ImageWrapper.iter_frames`, never below
            :data:`MIN_FRAME_DELAY`.
    """

    frame: PhotoImage
    delay: int


def _open_source(arg: ImageInput, /) -> io.BytesIO:
    """Coerce an image source into a seekable in-memory stream.

    A path is read whole rather than handed to ``Image.open``: a
    multi-frame image decodes its frames lazily, so its source must
    stay readable for as long as the image lives, and an in-memory
    stream does that without holding an OS file handle open.

    Args:
        arg (ImageInput): The source to coerce. An ``Image.Image`` and
            an :class:`ImageWrapper` are not file sources and are
            rejected; :meth:`ImageWrapper._open` handles those cases
            before calling here.

    Returns:
        A stream positioned at the start of the encoded image.

    Raises:
        TypeError: If ``arg`` is not a str, Path, or bytes.
        OSError: If a path does not exist or cannot be read.
    """
    if isinstance(arg, bytes):
        return io.BytesIO(arg)
    if isinstance(arg, (str, Path)):
        return io.BytesIO(Path(arg).resolve(strict=True).read_bytes())
    raise TypeError("arg must be a str, Path, bytes, or PIL Image")


def _interpreter_alive(app: object, /) -> bool:
    """Whether ``app`` — a Tcl interpreter object — still has a live Tk.

    Args:
        app (object): The interpreter behind some widget's ``tk``.

    Returns:
        False once its application has been destroyed. A pure-Tcl
        command would still answer there, so the probe is a *Tk* one:
        those are what die with the application.
    """
    try:
        app.call("winfo", "exists", ".")  # type: ignore[attr-defined]
    except tk.TclError:
        return False
    return True


def _to_rgba(frame: Image.Image, /) -> Image.Image:
    """Convert a frame to RGBA, rescaling wide samples rather than clipping.

    ``convert`` saturates every sample above 255, turning a 16-bit scan
    into a white rectangle, so wide modes are mapped down to 0-255
    first: the 16-bit family by its fixed full-scale range, ``I`` and
    ``F`` by their own extrema, since neither format fixes a range and
    a float image is as likely to run 0.0-1.0 as 0-65535. A frame of
    one flat value maps to black.

    Args:
        frame (Image.Image): One frame, in any mode.

    Returns:
        The frame in RGBA. Only wide modes are rescaled; narrow ones
        convert directly, so ordinary images are untouched.
    """
    mode = frame.mode
    if mode in _SIXTEEN_BIT:
        wide = frame if mode == "I;16" else frame.convert("I")
        scaled = wide.point(lambda v: v * (255 / 65535) + 0.5)
    elif mode in _UNBOUNDED:
        low, high = cast("tuple[float, float]", frame.getextrema())
        span = high - low
        if not span:
            scaled = frame.point(lambda v: 0.0)
        else:
            factor = 255 / span
            scaled = frame.point(lambda v: (v - low) * factor + 0.5)
    else:
        return frame.convert("RGBA")
    return scaled.convert("L").convert("RGBA")


def _pad_to_canvas(frame: Image.Image, size: tuple[int, int], /) -> Image.Image:
    """Pad a frame to the canvas size; a full-size frame passes through.

    Args:
        frame (Image.Image): One RGBA frame, possibly partial.
        size (tuple[int, int]): The canvas to pad to.

    Returns:
        The frame at exactly ``size``, padded with transparency —
        ``frame`` itself when it is already full-size.
    """
    if frame.size == size:
        return frame
    padded = Image.new("RGBA", size, (0, 0, 0, 0))
    padded.paste(frame)
    return padded


def _mapped_frames(
    frames: list[Image.Image], op: Callable[[Image.Image], Image.Image], /
) -> list[Image.Image]:
    """Apply a pure operation to every frame, carrying each frame's delay.

    Args:
        frames (list[Image.Image]): Playback frames, delays in ``info``.
        op (Callable[[Image.Image], Image.Image]): The operation; must
            return a new image and never mutate its input.

    Returns:
        The mapped frames, each keeping its source frame's delay.
    """
    mapped: list[Image.Image] = []
    for frame in frames:
        new = op(frame)
        if "duration" in frame.info:
            new.info["duration"] = frame.info["duration"]
        mapped.append(new)
    return mapped


class ImageWrapper:
    """An owned ``Image.Image``, in the forms the widgets here need it.

    The adapter a widget holds so its caller does not have to: the
    transformations below take and return wrappers, so a path can be
    passed to every one of them and this class never named.

    Construction takes ownership of its pixels, so no wrapper shares
    pixel data with its source and the source is never mutated.
    Everything is pure PIL except :attr:`photo` and :meth:`iter_frames`,
    which build Tk images and so need a live interpreter.

    Only some sources carry an animation through. A wrapper built from a
    path, from bytes, or from another wrapper keeps every frame; one
    built from an existing ``Image.Image`` keeps that image's current
    frame alone.
    """

    __slots__ = ("_frames", "_image", "_photos")

    def __init__(self, arg: ImageInput, /) -> None:
        """Load ``arg``, copying every pixel out of it.

        Args:
            arg (ImageInput): The image source. Another wrapper's
                playback frames are copied over; the rest is
                :meth:`_open`'s contract.
        """
        self._photos: dict[object, PhotoImage] = {}
        if isinstance(arg, ImageWrapper):
            reel = arg._playback_reel()
            if reel is not None:
                self._frames: list[Image.Image] | None = reel
                self._image: Image.Image = reel[0]
                self._image.format = arg._image.format
                return
            arg = arg._image
        self._frames = None
        self._image = ImageWrapper._open(arg)
        method = _EXIF_TRANSPOSES.get(self._image.getexif().get(_EXIF_ORIENTATION, 1))
        if method is not None:
            reel = self._playback_reel()
            if reel is not None:
                source_format = self._image.format
                self._frames = _mapped_frames(reel, lambda frame: frame.transpose(method))
                self._image = self._frames[0]
                self._image.format = source_format

    @property
    def image(self) -> Image.Image:
        """The wrapped image itself; owned by this wrapper, not a copy."""
        return self._image

    @property
    def format(self) -> str | None:
        """The format decoded from (e.g. ``"PNG"``), or None if there was none.

        Names where the pixels came from: :meth:`copy` preserves it but
        every transformation below reports None, having built a new
        image that was never encoded as anything.
        """
        return self._image.format

    @property
    def photo(self) -> PhotoImage:
        """The image's first frame as a Tk handle on the default root.

        :meth:`photo_for` with no master: fine in a single-interpreter
        process, but a handle for a window or menu on any other
        interpreter must come from :meth:`photo_for` with that
        interpreter's master — Tk images are per-interpreter.

        Raises:
            RuntimeError: If no Tk interpreter exists yet.
        """
        return self.photo_for(None)

    def photo_for(self, master: tk.Misc | None, /) -> PhotoImage:
        """The image's first frame as a Tk handle on ``master``'s interpreter.

        Built once per interpreter and cached: a handle given to a
        widget on any other raises ``can't use "pyimageN"``, so a
        window or menu outside the default root needs its own master
        here. Always frame 0, whatever the wrapped image's current seek
        position, and wide modes (the 16-bit family, ``I``, ``F``) are
        rescaled rather than clipped, exactly as :meth:`iter_frames`
        rescales them.

        Args:
            master (tk.Misc | None): A widget of the interpreter the
                handle is for. None means tkinter's default root.

        Raises:
            RuntimeError: If ``master`` is None and no Tk interpreter
                exists yet.
        """
        self._evict_dead_photos()
        key: object = None if master is None else master.tk
        cached = self._photos.get(key)
        if cached is None:
            if self._frames is None and self._image.tell() != 0:
                self._image.seek(0)
            image = self._image
            if image.mode in _SIXTEEN_BIT or image.mode in _UNBOUNDED:
                image = _to_rgba(image)
            cached = PhotoImage(image, master=master)
            self._photos[key] = cached
        return cached

    def _evict_dead_photos(self) -> None:
        """Drop cached handles whose interpreter has been destroyed.

        Keeps a wrapper reused across roots from pinning every
        interpreter the application has cycled through. Liveness is
        probed with a Tk command rather than asked of the object, since
        a destroyed interpreter still answers pure-Tcl ones; the
        default-root entry is keyed None, names no interpreter to test,
        and is left alone.
        """
        dead = [key for key in self._photos if key is not None and not _interpreter_alive(key)]
        for key in dead:
            del self._photos[key]

    @property
    def width(self) -> int:
        """The image width in pixels."""
        return self._image.size[0]

    @property
    def height(self) -> int:
        """The image height in pixels."""
        return self._image.size[1]

    def copy(self) -> Self:
        """Return an independent wrapper over a copy of this image.

        Keeps :attr:`format`, and every playback frame of an animation.
        """
        return type(self)(self)

    def iter_frames(
        self, default_delay: int = 100, *, master: tk.Misc | None = None
    ) -> Iterator[AnimFrame]:
        """Yield every frame of an animation as a Tk image, lazily.

        Nothing is decoded until the iterator is advanced. Frames pass
        through :func:`_to_rgba`, rescaling 16-bit and float samples
        instead of letting them clip, and are padded to the full
        canvas, so a format that stores partial frames still yields
        whole ones. A delay comes from the frame, then the image, then
        ``default_delay``, floored at :data:`MIN_FRAME_DELAY`.
        Iterating seeks the wrapped image and rewinds it to the first
        frame once the iterator is exhausted or closed — except on a
        wrapper holding already-decoded frames (a transformed or
        copied animation), which yields those and never seeks. A still
        image yields exactly one frame.

        Args:
            default_delay (int): Milliseconds to hold a frame declaring
                no duration of its own. Defaults to 100.
            master (tk.Misc | None): A widget of the interpreter the
                frame handles are for, as for :meth:`photo_for`.
                Defaults to None, meaning tkinter's default root.

        Raises:
            RuntimeError: If ``master`` is None and no Tk interpreter
                exists yet.

        Yields:
            Each :class:`AnimFrame` in playback order.
        """
        fallback = int(self._image.info.get("duration", default_delay))
        if self._frames is not None:
            for stored in self._frames:
                yield AnimFrame(
                    frame=PhotoImage(stored, master=master),
                    delay=max(int(stored.info.get("duration", fallback)), MIN_FRAME_DELAY),
                )
            return
        start = 1 if self._image.info.get("default_image") else 0
        try:
            for i, frame in enumerate(ImageSequence.Iterator(self._image)):
                if i < start:
                    continue
                rgba = _pad_to_canvas(_to_rgba(frame), self._image.size)

                yield AnimFrame(
                    frame=PhotoImage(rgba, master=master),
                    delay=max(int(frame.info.get("duration", fallback)), MIN_FRAME_DELAY),
                )
        finally:
            self._image.seek(0)

    def _playback_reel(self) -> list[Image.Image] | None:
        """The animation's playback frames as independent images, or None.

        None for a still — including a multi-frame image whose only
        frame is an APNG cover. Frames come back RGBA at the full
        canvas size, each carrying its delay as ``info["duration"]``
        where one is known, so a wrapper built over them plays back as
        this one does. Pure PIL: nothing here touches Tk.
        """
        if self._frames is not None:
            return [frame.copy() for frame in self._frames]
        if getattr(self._image, "n_frames", 1) <= 1:
            return None
        fallback = self._image.info.get("duration")
        start = 1 if self._image.info.get("default_image") else 0
        frames: list[Image.Image] = []
        try:
            for i, frame in enumerate(ImageSequence.Iterator(self._image)):
                if i < start:
                    continue
                rgba = _pad_to_canvas(_to_rgba(frame), self._image.size)
                duration = frame.info.get("duration", fallback)
                if duration is not None:
                    rgba.info["duration"] = int(duration)
                frames.append(rgba)
        finally:
            self._image.seek(0)
        return frames or None

    @classmethod
    def _from_reel(cls, frames: list[Image.Image], /) -> Self:
        """Wrap already-decoded playback frames without copying them.

        :func:`_transformed`'s constructor: ``frames`` must be
        normalized as :meth:`_playback_reel` answers them, and
        ownership passes to the new wrapper.
        """
        wrapper = cls.__new__(cls)
        wrapper._frames = frames
        wrapper._image = frames[0]
        wrapper._photos = {}
        return wrapper

    @staticmethod
    def _open(arg: str | Path | bytes | Image.Image, /) -> Image.Image:
        """Load ``arg`` into an owned image, honoring EXIF orientation.

        Args:
            arg (str | Path | bytes | Image.Image): Path, raw encoded
                bytes, or an existing image to copy.

        Returns:
            An image sharing nothing with ``arg``, carrying its source
            format. Encoded sources keep every frame — a multi-frame
            source with an orientation tag arrives untransposed, and
            ``__init__`` reorients its playback frames. An
            ``Image.Image`` yields only its current frame.

        Raises:
            TypeError: If ``arg`` is not an :data:`ImageInput`.
            OSError: If the source cannot be found, read, or decoded.
        """
        if isinstance(arg, Image.Image):
            copied = arg.copy()
            copied.format = arg.format  # Image.copy drops it
            if copied.getexif().get(_EXIF_ORIENTATION, 1) == 1:
                return copied
            transposed = ImageOps.exif_transpose(copied)
            transposed.format = arg.format
            return transposed
        opened = Image.open(_open_source(arg))
        if opened.getexif().get(_EXIF_ORIENTATION, 1) == 1:
            return opened
        if getattr(opened, "n_frames", 1) > 1:
            return opened
        transposed = ImageOps.exif_transpose(opened)
        transposed.format = opened.format
        return transposed


def _transformed(arg: ImageInput, op: Callable[[Image.Image], Image.Image], /) -> ImageWrapper:
    """Apply a pure per-image operation across a whole source.

    The one shape every transformation shares: a still comes back as a
    new wrapper over ``op`` of its image, an animation as a new wrapper
    over ``op`` of every playback frame, each frame keeping its delay.

    Args:
        arg (ImageInput): The image source.
        op (Callable[[Image.Image], Image.Image]): The operation; must
            return a new image and never mutate its input.

    Returns:
        A new wrapper over the transformed image or frames.
    """
    source = arg if isinstance(arg, ImageWrapper) else ImageWrapper(arg)
    reel = source._playback_reel()
    if reel is None:
        return ImageWrapper(op(source.image))
    return ImageWrapper._from_reel(_mapped_frames(reel, op))


def crop_absolute(
    arg: ImageInput,
    /,
    *,
    horizontal: tuple[int, int] | None = None,
    vertical: tuple[int, int] | None = None,
) -> ImageWrapper:
    """Crop ``arg`` to an absolute pixel range on either or both axes.

    Both ranges are half-open ``(start, stop)`` pairs measured from the
    left and top edges respectively.

    >>> from PIL import Image
    >>> crop_absolute(Image.new("RGB", (40, 20)), horizontal=(0, 10)).width
    10

    Args:
        arg (ImageInput): The image source.
        horizontal (tuple[int, int] | None): Left and right bounds.
            Defaults to None, meaning the full width.
        vertical (tuple[int, int] | None): Top and bottom bounds.
            Defaults to None, meaning the full height.

    Returns:
        A new wrapper over the cropped region.

    Raises:
        ValueError: If a range runs backwards or falls outside the image.
    """
    source = arg if isinstance(arg, ImageWrapper) else ImageWrapper(arg)
    if horizontal is None:
        horizontal = (0, source.width)
    if vertical is None:
        vertical = (0, source.height)
    if not 0 <= horizontal[0] <= horizontal[1] <= source.width:
        raise ValueError(f"horizontal must be an ascending range within 0..{source.width}")
    if not 0 <= vertical[0] <= vertical[1] <= source.height:
        raise ValueError(f"vertical must be an ascending range within 0..{source.height}")
    # PIL's crop box is (left, upper, right, lower), not (left, right, upper, lower)
    box = (horizontal[0], vertical[0], horizontal[1], vertical[1])
    return _transformed(source, lambda image: image.crop(box))


def crop_side(arg: ImageInput, anchor: Side, breadth: int, /) -> ImageWrapper:
    """Keep the ``breadth`` pixels of ``arg`` nearest one edge, discarding the rest.

    The anchor names the edge that is *kept*, so ``("bottom", 5)``
    returns the bottom five rows. A breadth at or above the relevant
    dimension keeps the whole image.

    >>> from PIL import Image
    >>> crop_side(Image.new("RGB", (40, 20)), "right", 10).width
    10

    Args:
        arg (ImageInput): The image source.
        anchor (Side): The edge to keep.
        breadth (int): How many pixels inward from that edge to keep.

    Returns:
        A new wrapper over the retained strip.

    Raises:
        ValueError: If ``breadth`` is negative, or ``anchor`` is not a
            :data:`Side`.
    """
    if breadth < 0:
        raise ValueError("breadth must not be negative")
    source = arg if isinstance(arg, ImageWrapper) else ImageWrapper(arg)
    match anchor:
        case "top":
            return crop_absolute(source, vertical=(0, min(breadth, source.height)))
        case "bottom":
            return crop_absolute(source, vertical=(max(source.height - breadth, 0), source.height))
        case "left":
            return crop_absolute(source, horizontal=(0, min(breadth, source.width)))
        case "right":
            return crop_absolute(source, horizontal=(max(source.width - breadth, 0), source.width))
        case _:
            raise ValueError("anchor must be one of 'top', 'bottom', 'left', or 'right'")


def flip_horizontal(arg: ImageInput, /) -> ImageWrapper:
    """Mirror ``arg`` left-to-right.

    Args:
        arg (ImageInput): The image source.

    Returns:
        A new wrapper over the mirrored image.
    """
    return _transformed(arg, lambda image: image.transpose(Image.Transpose.FLIP_LEFT_RIGHT))


def flip_vertical(arg: ImageInput, /) -> ImageWrapper:
    """Mirror ``arg`` top-to-bottom.

    Args:
        arg (ImageInput): The image source.

    Returns:
        A new wrapper over the mirrored image.
    """
    return _transformed(arg, lambda image: image.transpose(Image.Transpose.FLIP_TOP_BOTTOM))


def rotate(arg: ImageInput, angle: int, /) -> ImageWrapper:
    """Rotate ``arg`` **clockwise** by ``angle`` degrees.

    Quarter turns are exact transpositions; any other angle is resampled
    bicubically and the canvas is expanded so no corner is clipped.
    Angles are normalized, so negative values and multiples of 360 are
    accepted.

    >>> from PIL import Image
    >>> rotate(Image.new("RGB", (40, 20)), 90).image.size
    (20, 40)

    Args:
        arg (ImageInput): The image source.
        angle (int): Degrees clockwise.

    Returns:
        A new wrapper over the rotated image.
    """
    angle %= 360
    # PIL rotates counter-clockwise, so a clockwise quarter turn is its complement
    match angle:
        case 0:
            return _transformed(arg, Image.Image.copy)
        case 90:
            return _transformed(arg, lambda image: image.transpose(Image.Transpose.ROTATE_270))
        case 180:
            return _transformed(arg, lambda image: image.transpose(Image.Transpose.ROTATE_180))
        case 270:
            return _transformed(arg, lambda image: image.transpose(Image.Transpose.ROTATE_90))
        case _:
            return _transformed(
                arg, lambda image: image.rotate(-angle, resample=BICUBIC, expand=True)
            )


def rotate_right(arg: ImageInput, angle: int, /) -> ImageWrapper:
    """Rotate ``arg`` clockwise by ``angle`` degrees; delegates to :func:`rotate`.

    Args:
        arg (ImageInput): The image source.
        angle (int): Degrees clockwise.

    Returns:
        A new wrapper over the rotated image.
    """
    return rotate(arg, angle)


def rotate_left(arg: ImageInput, angle: int, /) -> ImageWrapper:
    """Rotate ``arg`` **counter-clockwise** by ``angle`` degrees.

    Args:
        arg (ImageInput): The image source.
        angle (int): Degrees counter-clockwise.

    Returns:
        A new wrapper over the rotated image.
    """
    return rotate(arg, -angle)


def scale(arg: ImageInput, percent: int | float, /) -> ImageWrapper:
    """Resize ``arg`` to ``percent`` of its size, preserving aspect ratio.

    Upscaling resamples bicubically; downscaling uses Lanczos, which is
    slower but markedly better at shrinking. Both axes round to at least
    one pixel.

    >>> from PIL import Image
    >>> scale(Image.new("RGB", (40, 20)), 50).image.size
    (20, 10)

    Args:
        arg (ImageInput): The image source.
        percent (int | float): Target size as a percentage of the current
            one; 100 returns an unscaled copy.

    Returns:
        A new wrapper at the requested size.

    Raises:
        ValueError: If ``percent`` is not greater than zero.
    """
    if percent <= 0:
        raise ValueError("percent must be greater than zero")
    source = arg if isinstance(arg, ImageWrapper) else ImageWrapper(arg)
    if percent == 100:
        unscaled = source.copy()
        unscaled._image.format = None
        return unscaled
    width = max(round(source.width * percent / 100), 1)
    height = max(round(source.height * percent / 100), 1)
    if percent > 100:
        return _transformed(source, lambda image: image.resize((width, height), resample=BICUBIC))

    def shrink(image: Image.Image) -> Image.Image:
        clone = image.copy()
        clone.thumbnail((width, height), resample=LANCZOS, reducing_gap=None)
        return clone

    return _transformed(source, shrink)


def thumbnail(
    arg: ImageInput,
    max_width: int | None = None,
    max_height: int | None = None,
    /,
    *,
    resample: Image.Resampling = BICUBIC,
) -> ImageWrapper:
    """Shrink ``arg`` to fit within a bounding box, preserving aspect ratio.

    Fits *within* the box rather than filling it, and never upscales: an
    image already smaller than the box comes back unchanged.

    >>> from PIL import Image
    >>> thumbnail(Image.new("RGB", (40, 20)), 10, 10).image.size
    (10, 5)

    Args:
        arg (ImageInput): The image source.
        max_width (int | None): Width bound in pixels. Defaults to None,
            meaning the source width.
        max_height (int | None): Height bound in pixels. Defaults to
            None, meaning the source height.
        resample (Image.Resampling): Filter used to shrink. Defaults to
            :data:`BICUBIC`.

    Returns:
        A new wrapper fitted to the box.
    """
    source = arg if isinstance(arg, ImageWrapper) else ImageWrapper(arg)
    box = (
        max_width if max_width is not None else source.width,
        max_height if max_height is not None else source.height,
    )

    def shrink(image: Image.Image) -> Image.Image:
        clone = image.copy()
        clone.thumbnail(box, resample=resample, reducing_gap=None)
        return clone

    return _transformed(source, shrink)


def small_icon(arg: ImageInput, /) -> ImageWrapper:
    """Fit ``arg`` within 16x16, ready for a widget to display.

    A fixed-size :func:`thumbnail`, resampled nearest-neighbour: at
    this size crisp edges beat smooth ones.

    Args:
        arg (ImageInput): The image source.

    Returns:
        A new wrapper fitted to the box.
    """
    return thumbnail(arg, 16, 16, resample=NEAREST)


def medium_icon(arg: ImageInput, /) -> ImageWrapper:
    """Fit ``arg`` within 48x48, ready for a widget to display.

    A fixed-size :func:`thumbnail`, resampled with :data:`HAMMING`.

    Args:
        arg (ImageInput): The image source.

    Returns:
        A new wrapper fitted to the box.
    """
    return thumbnail(arg, 48, 48, resample=HAMMING)


def large_icon(arg: ImageInput, /) -> ImageWrapper:
    """Fit ``arg`` within 96x96, ready for a widget to display.

    A fixed-size :func:`thumbnail`, resampled with :data:`LANCZOS`.

    Args:
        arg (ImageInput): The image source.

    Returns:
        A new wrapper fitted to the box.
    """
    return thumbnail(arg, 96, 96, resample=LANCZOS)


def extra_large_icon(arg: ImageInput, /) -> ImageWrapper:
    """Fit ``arg`` within 256x256, ready for a widget to display.

    A fixed-size :func:`thumbnail`, resampled with :data:`LANCZOS`.

    Args:
        arg (ImageInput): The image source.

    Returns:
        A new wrapper fitted to the box.
    """
    return thumbnail(arg, 256, 256, resample=LANCZOS)


def window_icon(arg: ImageInput, /) -> ImageWrapper:
    """Fit ``arg`` within 64x64, ready for a widget to display.

    A fixed-size :func:`thumbnail`, resampled with :data:`LANCZOS`, at
    the size :class:`~tkfacade.window.Window` hands to Tk for the window
    icon.

    Args:
        arg (ImageInput): The image source.

    Returns:
        A new wrapper fitted to the box.
    """
    return thumbnail(arg, 64, 64, resample=LANCZOS)
