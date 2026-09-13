"""tkfacade: typed wrappers over Tk, and the vocabulary their signatures speak.

The widgets, windows, and media classes are re-exported here from the
subpackage that implements each, beside the value aliases and option
dicts their signatures are written in — :data:`Anchor`, :data:`Sticky`,
:class:`GridSetOptions` and the rest — so calling code can annotate
itself from this one namespace.

:class:`VideoDisplay` resolves lazily (PEP 562) through :mod:`.media`,
and :class:`MediaPlayer` builds its video half only when a video source
arrives, so importing tkfacade does not load libmpv; see that package's
docstring.
"""

import importlib
from typing import TYPE_CHECKING

from ._params import GridSetOptions as GridSetOptions
from ._params import ImageOptions as ImageOptions
from ._params import MediaDisplayOptions as MediaDisplayOptions
from ._params import MediaOptions as MediaOptions
from ._params import MediaPlayerOptions as MediaPlayerOptions
from ._params import PackSetOptions as PackSetOptions
from ._params import PlaceSetOptions as PlaceSetOptions
from ._params import TreeColumnOptions as TreeColumnOptions
from ._params import VideoOptions as VideoOptions
from ._sentinels import OMIT as OMIT
from ._sentinels import Omitted as Omitted
from ._subscription import Subscription as Subscription
from ._types import Anchor as Anchor
from ._types import Arrangement as Arrangement
from ._types import BorderMode as BorderMode
from ._types import Color as Color
from ._types import Command as Command
from ._types import Compound as Compound
from ._types import EdgePosition as EdgePosition
from ._types import Fill as Fill
from ._types import FontSpec as FontSpec
from ._types import GridInfo as GridInfo
from ._types import ImageSpec as ImageSpec
from ._types import Justify as Justify
from ._types import MediaSource as MediaSource
from ._types import MenuDirection as MenuDirection
from ._types import Orient as Orient
from ._types import PackInfo as PackInfo
from ._types import Pad as Pad
from ._types import Padding as Padding
from ._types import PadValue as PadValue
from ._types import PlaceInfo as PlaceInfo
from ._types import Rect as Rect
from ._types import Rel as Rel
from ._types import Relief as Relief
from ._types import ScrollUnit as ScrollUnit
from ._types import Side as Side
from ._types import StateSpec as StateSpec
from ._types import Sticky as Sticky
from .button import Button as Button
from .button import Checkbutton as Checkbutton
from .choice import NOTHING_CHOSEN as NOTHING_CHOSEN
from .choice import ChoiceBox as ChoiceBox
from .choice import ChoiceButton as ChoiceButton
from .choice import ChoiceButtons as ChoiceButtons
from .choice import ChoiceSet as ChoiceSet
from .choice import ChoiceSpinner as ChoiceSpinner
from .dialog import Dialog as Dialog
from .events import ACTIVATED as ACTIVATED
from .events import Destroyed as Destroyed
from .events import Event as Event
from .events import EventSpec as EventSpec
from .events import FocusGained as FocusGained
from .events import FocusLost as FocusLost
from .events import Key as Key
from .events import ModifierState as ModifierState
from .events import Motion as Motion
from .events import MouseButton as MouseButton
from .events import PointerEnter as PointerEnter
from .events import PointerLeave as PointerLeave
from .events import Press as Press
from .events import Release as Release
from .events import Virtual as Virtual
from .events import VirtualEvent as VirtualEvent
from .events import Wheel as Wheel
from .frame import AbstractMultiFrame as AbstractMultiFrame
from .frame import Frame as Frame
from .frame import LabelFrame as LabelFrame
from .frame import PanedFrame as PanedFrame
from .frame import StackFrame as StackFrame
from .frame import TabFrame as TabFrame
from .input import Chord as Chord
from .input import InputName as InputName
from .input import InputObserver as InputObserver
from .input import KeyGroup as KeyGroup
from .label import ImageLabel as ImageLabel
from .label import TextLabel as TextLabel
from .listbox import Listbox as Listbox
from .look import Look as Look
from .look import LookOptions as LookOptions
from .look import LookPart as LookPart
from .look import LookState as LookState
from .media import AbstractMediaDisplay as AbstractMediaDisplay
from .media import AnimFrame as AnimFrame
from .media import ImageDisplay as ImageDisplay
from .media import ImageInput as ImageInput
from .media import ImageWrapper as ImageWrapper
from .media import MediaPlayer as MediaPlayer
from .media import MediaVariables as MediaVariables
from .media import PhotoImage as PhotoImage
from .media import PlayerSource as PlayerSource
from .media import crop_absolute as crop_absolute
from .media import crop_side as crop_side
from .media import extra_large_icon as extra_large_icon
from .media import flip_horizontal as flip_horizontal
from .media import flip_vertical as flip_vertical
from .media import large_icon as large_icon
from .media import medium_icon as medium_icon
from .media import rotate as rotate
from .media import rotate_left as rotate_left
from .media import rotate_right as rotate_right
from .media import scale as scale
from .media import small_icon as small_icon
from .media import thumbnail as thumbnail
from .media import window_icon as window_icon
from .menu import CheckboxRow as CheckboxRow
from .menu import ChoiceRow as ChoiceRow
from .menu import ChoiceRows as ChoiceRows
from .menu import CommandMenu as CommandMenu
from .menu import CommandRow as CommandRow
from .menu import Menubar as Menubar
from .menu import MenuBase as MenuBase
from .menu import Menubutton as Menubutton
from .menu import MenuPart as MenuPart
from .menu import OptionMenu as OptionMenu
from .menu import RuledMenu as RuledMenu
from .menu import Submenu as Submenu
from .observable import DivergenceError as DivergenceError
from .observable import Observable as Observable
from .observable import ObservableBool as ObservableBool
from .observable import ObservableFloat as ObservableFloat
from .observable import ObservableInt as ObservableInt
from .observable import ObservableStr as ObservableStr
from .progressbar import ItemBasedProgressBar as ItemBasedProgressBar
from .progressbar import PercentageBasedProgressBar as PercentageBasedProgressBar
from .scale import AbstractScale as AbstractScale
from .scale import FloatScale as FloatScale
from .scale import IntScale as IntScale
from .scroll import AbstractScrollable as AbstractScrollable
from .scroll import Scrollbar as Scrollbar
from .scroll import ScrollbarSpec as ScrollbarSpec
from .separator import Separator as Separator
from .spinbox import AbstractSpinbox as AbstractSpinbox
from .spinbox import FloatSpinbox as FloatSpinbox
from .spinbox import IntSpinbox as IntSpinbox
from .text import AbstractTextInterface as AbstractTextInterface
from .text import Combobox as Combobox
from .text import Entry as Entry
from .text import TextBox as TextBox
from .text import TitleEntry as TitleEntry
from .tree import ROOT as ROOT
from .tree import Table as Table
from .tree import Tree as Tree
from .tree import TreeColumn as TreeColumn
from .tree import TreeColumnSpec as TreeColumnSpec
from .tree import TreeRow as TreeRow
from .window import Root as Root
from .window import Window as Window
from .window import get_root as get_root

if TYPE_CHECKING:
    from .media import VideoDisplay as VideoDisplay

_VIDEO_EXPORTS: frozenset[str] = frozenset({"VideoDisplay"})
"""Names resolved through ``__getattr__``, keeping ``_video`` out of the package import."""


def __getattr__(name: str) -> object:
    """Resolve the lazily exposed video classes on first access."""
    if name in _VIDEO_EXPORTS:
        value: object = getattr(importlib.import_module(f"{__name__}.media"), name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """List the lazily exposed names alongside the module's real globals."""
    return sorted({*globals(), *_VIDEO_EXPORTS})
