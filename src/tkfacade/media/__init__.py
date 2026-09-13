"""Image and video: PIL-backed transformations, icon helpers, and mpv.

:class:`AbstractMediaDisplay` is the contract a display of timed media
answers, and the widget wrappers here implement it: :class:`ImageDisplay`
for a still or an animation, :class:`VideoDisplay` with mpv behind it,
and :class:`MediaPlayer` holding one of each beneath a control bar,
switching by what a source resolves to. Code holding the contract
drives any of them without knowing which. :class:`ImageWrapper` wraps a
PIL image rather than a widget, and :class:`~tkfacade.label.ImageLabel` displays
one as a label rather than as media. The transformations answer with a
wrapper and the widgets hold one, so a caller passes a source and gets
one back without naming the class.

:class:`VideoDisplay` resolves lazily (PEP 562), libmpv itself loads
only when a video display is constructed, and :class:`MediaPlayer`
builds its video half only when a video source arrives, so importing
this package — and tkfacade with it — stands on a machine without one.
"""

import importlib
from typing import TYPE_CHECKING

from .._types import MediaSource as MediaSource
from .._types import Side as Side
from ._abstract import AbstractMediaDisplay as AbstractMediaDisplay
from ._abstract import MediaVariables as MediaVariables
from ._image import BICUBIC as BICUBIC
from ._image import BILINEAR as BILINEAR
from ._image import BOX as BOX
from ._image import HAMMING as HAMMING
from ._image import LANCZOS as LANCZOS
from ._image import MIN_FRAME_DELAY as MIN_FRAME_DELAY
from ._image import NEAREST as NEAREST
from ._image import AnimFrame as AnimFrame
from ._image import ImageInput as ImageInput
from ._image import ImageWrapper as ImageWrapper
from ._image import PhotoImage as PhotoImage
from ._image import crop_absolute as crop_absolute
from ._image import crop_side as crop_side
from ._image import extra_large_icon as extra_large_icon
from ._image import flip_horizontal as flip_horizontal
from ._image import flip_vertical as flip_vertical
from ._image import large_icon as large_icon
from ._image import medium_icon as medium_icon
from ._image import rotate as rotate
from ._image import rotate_left as rotate_left
from ._image import rotate_right as rotate_right
from ._image import scale as scale
from ._image import small_icon as small_icon
from ._image import thumbnail as thumbnail
from ._image import window_icon as window_icon
from ._image_display import ImageDisplay as ImageDisplay
from ._player import MediaPlayer as MediaPlayer
from ._player import PlayerSource as PlayerSource

if TYPE_CHECKING:
    from ._video import VideoDisplay as VideoDisplay

_VIDEO_EXPORTS: frozenset[str] = frozenset({"VideoDisplay"})
"""Names resolved through ``__getattr__``, keeping ``_video`` out of the package import."""


def __getattr__(name: str) -> object:
    """Resolve the lazily exposed video classes on first access."""
    if name in _VIDEO_EXPORTS:
        value: object = getattr(importlib.import_module(f"{__name__}._video"), name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """List the lazily exposed names alongside the module's real globals."""
    return sorted({*globals(), *_VIDEO_EXPORTS})
