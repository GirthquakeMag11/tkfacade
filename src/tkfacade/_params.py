"""TypedDicts for the options this library's wider signatures accept.

Three families, unrelated to each other: the geometry facets' ``cnf``
dicts, the ttk style option sets, and the keyword bundles that more than
one method spells out identically — those last are consumed with
``Unpack``, so the TypedDict *is* the signature rather than shadowing it.

The first and third families are re-exported from :mod:`tkfacade`; the style
sets are reference data for the ``clam`` theme, measured rather than
consumed, and stay here.
"""

import tkinter as tk
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Final, TypedDict

from ._sentinels import Omitted
from ._types import (
    Anchor,
    BorderMode,
    Color,
    Command,
    Compound,
    EdgePosition,
    Fill,
    FontSpec,
    ImageSpec,
    Justify,
    Pad,
    Padding,
    PadValue,
    Rel,
    Relief,
    Side,
    Sticky,
)
from .observable import ObservableStr

if TYPE_CHECKING:
    from .widget._base import BaseWidget


class PlaceSetOptions(TypedDict, total=False):
    """Options accepted by :meth:`Widget.place` via ``cnf``.

    Mirrors the method's keyword parameters, with the target master
    spelled ``in_`` and taking a wrapper exactly as the keyword does,
    so a prebuilt options dict type-checks the same as keyword
    arguments.
    """

    anchor: Anchor
    bordermode: BorderMode
    x: PadValue
    y: PadValue
    relx: Rel
    rely: Rel
    width: PadValue
    height: PadValue
    relwidth: Rel
    relheight: Rel
    in_: tk.Misc | BaseWidget


class PackSetOptions(TypedDict, total=False):
    """Options accepted by :meth:`Widget.pack` via ``cnf``.

    Mirrors the method's keyword parameters, with the target master
    spelled ``in_`` and taking a wrapper exactly as the keyword does,
    so a prebuilt options dict type-checks the same as keyword
    arguments. Unlike :class:`~tkfacade.PackInfo` it carries
    ``after``/``before``, which exist only at set time.
    """

    after: tk.Misc | BaseWidget
    anchor: Anchor
    before: tk.Misc | BaseWidget
    expand: bool
    fill: Fill
    side: Side
    ipadx: PadValue
    ipady: PadValue
    padx: Pad
    pady: Pad
    in_: tk.Misc | BaseWidget


class GridSetOptions(TypedDict, total=False):
    """Options accepted by :meth:`Widget.grid` via ``cnf``.

    Mirrors the method's keyword parameters, with the target master
    spelled ``in_`` and taking a wrapper exactly as the keyword does,
    so a prebuilt options dict type-checks the same as keyword
    arguments.
    """

    column: int
    columnspan: int
    row: int
    rowspan: int
    ipadx: PadValue
    ipady: PadValue
    padx: Pad
    pady: Pad
    sticky: Sticky
    in_: tk.Misc | BaseWidget


class TreeColumnOptions(TypedDict, total=False):
    """The configurable half of a tree column, minus its name.

    Every key matches a field of :class:`~tkfacade.TreeColumnSpec`, which is
    where the defaults and the validation live: an option left out here
    is one the spec answers for. Unpacked by
    :meth:`~tkfacade.Tree.add_column` and :meth:`~tkfacade.Table.add_column`,
    which take the name and position separately because those are not
    configuration.
    """

    displayed: bool | Omitted
    heading_text: str | ObservableStr | None
    heading_command: Command | None
    incoming_converter: Callable[[Any], str] | Omitted
    outgoing_converter: Callable[[str], Any] | Omitted
    width: int | Omitted
    minwidth: int | Omitted
    stretch: bool | Omitted
    anchor: Anchor | Omitted
    default: Any
    default_factory: Callable[[], Any] | None


class MediaOptions(TypedDict, total=False):
    """Options every :class:`~tkfacade.AbstractMediaDisplay` takes, minus parent and source.

    Those two are positional and required-ish, so they stay in the
    signature; everything a caller may leave alone lives here. What one
    medium's display adds to these is its own dict below.
    """

    auto_size: bool
    auto_size_limit: tuple[int, int] | None
    background: str
    height: int
    loop: bool
    obstructed_pause: bool
    volume: float
    width: int


class VideoOptions(MediaOptions, total=False):
    """:class:`MediaOptions` plus mpv's own option."""

    hwdec: str


class ImageOptions(MediaOptions, total=False):
    """:class:`MediaOptions` plus ``default_delay``, an animation's fallback per-frame delay."""

    default_delay: int


class MediaDisplayOptions(VideoOptions, ImageOptions, total=False):
    """The union of both displays' options: what a :class:`~tkfacade.MediaPlayer` routes.

    The shared keys govern the player and reach whichever display is
    active; ``hwdec`` reaches only the video display and
    ``default_delay`` only the image display — which is what the
    double inheritance says, rather than a second copy of the keys.
    """


class MediaPlayerOptions(MediaDisplayOptions, total=False):
    """:class:`MediaDisplayOptions` plus the control bar's own option."""

    seek_step: float


# --------------------------------------------------------------------------- #
# ttk style options — clam only, measured on Tk 8.6.14 (`hazards/tkinter.md`, *Styling*)
# --------------------------------------------------------------------------- #


class TButtonStyleOptions(TypedDict, total=False):
    """Options that act on the ``TButton`` style under ``clam``.

    ``compound`` is read only while the widget's own ``-compound`` is empty,
    ``focuscolor`` only while the widget holds focus, and ``justify``/``space``
    only with content that shows them. ``width`` counts text characters, not
    pixels; a negative value is a minimum.
    """

    anchor: Anchor
    background: Color
    bordercolor: Color
    borderwidth: PadValue
    compound: Compound
    darkcolor: Color
    embossed: int
    focuscolor: Color
    focusthickness: PadValue
    font: FontSpec
    foreground: Color
    image: ImageSpec
    justify: Justify
    lightcolor: Color
    padding: Padding
    relief: Relief
    shiftrelief: PadValue
    space: PadValue
    width: int
    wraplength: PadValue


class ToolbuttonStyleOptions(TypedDict, total=False):
    """Options that act on the ``Toolbutton`` style under ``clam``.

    The flat toolbar look, and a top-level style rather than one derived from
    ``TButton`` -- configuring ``TButton`` does not reach it. Also accepted by
    Checkbutton and Radiobutton, where it renders a toggle button in place of an
    indicator. ``bordercolor``, ``lightcolor`` and ``darkcolor`` draw only in the
    ``selected`` state, and the style has no focus ring at all.
    """

    anchor: Anchor
    background: Color
    bordercolor: Color
    borderwidth: PadValue
    compound: Compound
    darkcolor: Color
    embossed: int
    font: FontSpec
    foreground: Color
    image: ImageSpec
    justify: Justify
    lightcolor: Color
    padding: Padding
    relief: Relief
    shiftrelief: PadValue
    space: PadValue
    width: int
    wraplength: PadValue


class TCheckbuttonStyleOptions(TypedDict, total=False):
    """Options that act on the ``TCheckbutton`` style under ``clam``.

    The indicator is drawn from ``indicatorbackground``,
    ``indicatorforeground``, ``upperbordercolor`` and ``lowerbordercolor``;
    ``indicatorcolor``, ``indicatordiameter``, ``indicatorrelief`` and
    ``shadecolor`` are accepted and inert. So are ``anchor``, ``relief``,
    ``bordercolor`` and ``borderwidth``.
    """

    background: Color
    compound: Compound
    embossed: int
    focuscolor: Color
    focusthickness: PadValue
    font: FontSpec
    foreground: Color
    image: ImageSpec
    indicatorbackground: Color
    indicatorforeground: Color
    indicatormargin: Padding
    indicatorsize: PadValue
    justify: Justify
    lowerbordercolor: Color
    padding: Padding
    shiftrelief: PadValue
    space: PadValue
    upperbordercolor: Color
    width: int
    wraplength: PadValue


class TMenubuttonStyleOptions(TypedDict, total=False):
    """Options that act on the ``TMenubutton`` style under ``clam``.

    The arrow is drawn from ``arrowcolor``, ``arrowsize`` and ``arrowpadding``;
    ``indicatorwidth``, ``indicatorheight`` and ``indicatormargin`` are inert.
    """

    anchor: Anchor
    arrowcolor: Color
    arrowpadding: Padding
    arrowsize: PadValue
    background: Color
    bordercolor: Color
    borderwidth: PadValue
    compound: Compound
    darkcolor: Color
    embossed: int
    focuscolor: Color
    focusthickness: PadValue
    font: FontSpec
    foreground: Color
    image: ImageSpec
    justify: Justify
    lightcolor: Color
    padding: Padding
    relief: Relief
    shiftrelief: PadValue
    space: PadValue
    width: int
    wraplength: PadValue


class TEntryStyleOptions(TypedDict, total=False):
    """Options that act on the ``TEntry`` style under ``clam``.

    ``font`` is not reachable from a style -- use ``entry.configure(font=...)``.
    The selection colours need a selection to exist before they show, and the
    insert-cursor options need the widget to hold focus. ``borderwidth`` and
    ``relief`` are inert; the border comes from ``bordercolor`` and
    ``lightcolor``.
    """

    background: Color
    bordercolor: Color
    fieldbackground: Color
    foreground: Color
    insertcolor: Color
    insertwidth: PadValue
    lightcolor: Color
    padding: Padding
    selectbackground: Color
    selectborderwidth: PadValue
    selectforeground: Color
    shiftrelief: PadValue


class TComboboxStyleOptions(TypedDict, total=False):
    """Options that act on the ``TCombobox`` style under ``clam``.

    ``font`` is not reachable from a style -- use ``combobox.configure(font=...)``.
    The dropdown is a classic :class:`tkinter.Listbox` that no style option
    reaches; configure it through the option database::

        root.option_add("*TCombobox*Listbox.background", "#202020")

    The frame around that list is ttk, under the style name
    ``ComboboxPopdownFrame``.
    """

    arrowcolor: Color
    arrowsize: PadValue
    background: Color
    bordercolor: Color
    darkcolor: Color
    fieldbackground: Color
    foreground: Color
    insertcolor: Color
    insertwidth: PadValue
    lightcolor: Color
    padding: Padding
    selectbackground: Color
    selectborderwidth: PadValue
    selectforeground: Color
    shiftrelief: PadValue


class TFrameStyleOptions(TypedDict, total=False):
    """Options that act on the ``TFrame`` style under ``clam``."""

    background: Color
    relief: Relief


class TLabelStyleOptions(TypedDict, total=False):
    """Options that act on the ``TLabel`` style under ``clam``.

    ``underline`` is inert: the widget carries its own, which wins. ``width``
    counts text characters, not pixels.
    """

    background: Color
    borderwidth: PadValue
    compound: Compound
    embossed: int
    font: FontSpec
    foreground: Color
    image: ImageSpec
    padding: Padding
    relief: Relief
    shiftrelief: PadValue
    space: PadValue
    width: int
    wraplength: PadValue


class TLabelframeStyleOptions(TypedDict, total=False):
    """Options that act on the ``TLabelframe`` style under ``clam``.

    The caption is a separate style -- see :class:`TLabelframeLabelStyleOptions`.
    """

    background: Color
    bordercolor: Color
    borderwidth: PadValue
    darkcolor: Color
    labelmargins: Padding
    labeloutside: bool
    lightcolor: Color
    padding: Padding
    relief: Relief


class TLabelframeLabelStyleOptions(TypedDict, total=False):
    """Options that act on the ``TLabelframe.Label`` style under ``clam``.

    The caption of a labelframe. The suffix hangs off whatever style the widget
    was given, so ``Wide.TLabelframe`` takes its caption from
    ``Wide.TLabelframe.Label``.
    """

    background: Color
    embossed: int
    font: FontSpec
    foreground: Color
    justify: Justify
    width: int
    wraplength: PadValue


class TNotebookStyleOptions(TypedDict, total=False):
    """Options that act on the ``TNotebook`` style under ``clam``.

    Tabs are a separate style -- see :class:`TNotebookTabStyleOptions`.
    """

    background: Color
    bordercolor: Color
    darkcolor: Color
    lightcolor: Color
    mintabwidth: PadValue
    padding: Padding
    tabmargins: Padding
    tabposition: EdgePosition


class TNotebookTabStyleOptions(TypedDict, total=False):
    """Options that act on the ``TNotebook.Tab`` style under ``clam``.

    ``background`` and ``lightcolor`` are listed but **cannot be set with**
    :meth:`ttk.Style.configure` under ``clam``: the theme maps them with an empty
    state specification, which matches every state and defeats ``configure``.
    Reach them through :meth:`ttk.Style.map` instead::

        style.map("TNotebook.Tab",
                  background=[("selected", "white"), ("", "#d8d8d8")])

    ``focuscolor`` draws only while the widget holds focus.
    """

    background: Color
    bordercolor: Color
    embossed: int
    expand: Padding
    focuscolor: Color
    focusthickness: PadValue
    font: FontSpec
    foreground: Color
    image: ImageSpec
    lightcolor: Color
    padding: Padding
    shiftrelief: PadValue
    width: int
    wraplength: PadValue


class TPanedwindowStyleOptions(TypedDict, total=False):
    """Options that act on the ``TPanedwindow`` style under ``clam``.

    Measured as ``Horizontal.TPanedwindow``; configure the name above. The sash
    is a separate style with a name trap of its own -- see
    :class:`SashStyleOptions`.
    """

    background: Color


class SashStyleOptions(TypedDict, total=False):
    """Options that act on the ``Sash`` style under ``clam``.

    The layout is registered as ``Horizontal.Sash``/``Vertical.Sash``, but the
    widget reads its options from the bare name ``"Sash"``, so configuring an
    oriented name changes what :meth:`ttk.Style.lookup` reports and nothing on
    screen, and the two orientations cannot differ within a theme.
    ``background``, ``sashpad``, ``sashrelief``, ``handlepad`` and
    ``handlesize`` are inert.
    """

    bordercolor: Color
    gripcount: PadValue
    lightcolor: Color
    sashthickness: PadValue


class TProgressbarStyleOptions(TypedDict, total=False):
    """Options that act on the ``TProgressbar`` style under ``clam``.

    Measured as ``Horizontal.TProgressbar``; configure the name above.
    ``thickness`` is inert under ``clam`` despite being the documented way to
    set it, as are ``troughrelief``, ``troughborderwidth``, ``pbarrelief`` and
    ``groovewidth``.
    """

    arrowsize: PadValue
    background: Color
    bordercolor: Color
    darkcolor: Color
    lightcolor: Color
    troughcolor: Color


class TScaleStyleOptions(TypedDict, total=False):
    """Options that act on the ``TScale`` style under ``clam``.

    Measured as ``Horizontal.TScale``; configure the name above.
    ``sliderrelief``, ``sliderthickness``, ``troughrelief`` and ``groovewidth``
    are inert.
    """

    arrowsize: PadValue
    background: Color
    bordercolor: Color
    darkcolor: Color
    gripcount: PadValue
    lightcolor: Color
    sliderlength: PadValue
    troughcolor: Color


class TScrollbarStyleOptions(TypedDict, total=False):
    """Options that act on the ``TScrollbar`` style under ``clam``.

    Measured as ``Horizontal.TScrollbar``; configure the name above. ``width``
    and ``relief`` are inert; ``arrowsize`` sets the thickness.
    """

    arrowcolor: Color
    arrowsize: PadValue
    background: Color
    bordercolor: Color
    darkcolor: Color
    gripcount: PadValue
    lightcolor: Color
    troughcolor: Color


class TSeparatorStyleOptions(TypedDict, total=False):
    """Options that act on the ``TSeparator`` style under ``clam``.

    Measured as ``Horizontal.TSeparator``; configure the name above.
    """

    background: Color


class TSizegripStyleOptions(TypedDict, total=False):
    """Options that act on the ``TSizegrip`` style under ``clam``."""

    background: Color


class TreeviewStyleOptions(TypedDict, total=False):
    """Options that act on the ``Treeview`` style under ``clam``.

    Row text is not styleable. ``Treeview.Item`` and ``Treeview.Cell`` declare
    ``font``, ``foreground`` and ``background``, and none of them act; row
    appearance comes from tags on the widget instead::

        tree.tag_configure("overdue", foreground="red", background="#ffe9e9")
        tree.insert("", "end", text="invoice 42", tags=("overdue",))

    Row *height* is the exception and does come from the style, as ``rowheight``
    here. Set it whenever a tag uses a larger font, or the text clips. Column
    headers are a separate style -- see :class:`TreeviewHeadingStyleOptions`.
    """

    background: Color
    bordercolor: Color
    fieldbackground: Color
    font: FontSpec
    foreground: Color
    image: ImageSpec
    indent: PadValue
    lightcolor: Color
    padding: Padding
    rowheight: PadValue
    shiftrelief: PadValue


class TreeviewHeadingStyleOptions(TypedDict, total=False):
    """Options that act on the ``Treeview.Heading`` style under ``clam``.

    ``underline`` acts here, unlike on buttons and labels, because a heading has
    no widget-level ``-underline`` to shadow it. ``anchor``, ``image``,
    ``justify``, ``width`` and ``rownumber`` are accepted and inert.
    """

    background: Color
    bordercolor: Color
    borderwidth: PadValue
    darkcolor: Color
    embossed: int
    font: FontSpec
    foreground: Color
    lightcolor: Color
    padding: Padding
    relief: Relief
    shiftrelief: PadValue
    underline: int
    wraplength: PadValue


class TreeviewItemStyleOptions(TypedDict, total=False):
    """Options that act on the ``Treeview.Item`` style under ``clam``.

    The expand/collapse indicator and the item image. Text appearance is not
    here -- see :class:`TreeviewStyleOptions` on tags.
    """

    embossed: int
    image: ImageSpec
    indicatormargins: Padding
    indicatorsize: PadValue
    padding: Padding
    shiftrelief: PadValue
    underline: int
    wraplength: PadValue


class TreeviewCellStyleOptions(TypedDict, total=False):
    """Options that act on the ``Treeview.Cell`` style under ``clam``.

    Text appearance is not here -- see :class:`TreeviewStyleOptions` on tags.
    """

    embossed: int
    padding: Padding
    shiftrelief: PadValue
    underline: int


TRadiobuttonStyleOptions = TCheckbuttonStyleOptions
"""``TRadiobutton`` acts on exactly the same options as ``TCheckbutton``."""

TSpinboxStyleOptions = TComboboxStyleOptions
"""``TSpinbox`` acts on exactly the same options as ``TCombobox``."""


STYLE_NAMES: Final[dict[str, str]] = {
    "Button": "TButton",
    "Checkbutton": "TCheckbutton",
    "Combobox": "TCombobox",
    "Entry": "TEntry",
    "Frame": "TFrame",
    "Label": "TLabel",
    "Labelframe": "TLabelframe",
    "Menubutton": "TMenubutton",
    "Notebook": "TNotebook",
    "Panedwindow": "TPanedwindow",
    "Progressbar": "TProgressbar",
    "Radiobutton": "TRadiobutton",
    "Scale": "TScale",
    "Scrollbar": "TScrollbar",
    "Separator": "TSeparator",
    "Sizegrip": "TSizegrip",
    "Spinbox": "TSpinbox",
    "Treeview": "Treeview",
}
"""Tk widget class to the style name to configure, as ``winfo_class`` reports it.

A widget's class *is* its default style name, so ``widget.winfo_class()`` is the
route from a widget to the name to configure. The orientation widgets are the
exception: their bare class has no layout of its own, but configuring it still
reaches both oriented styles through dotted fallback.
"""

SUB_STYLES: Final[dict[str, tuple[str, ...]]] = {
    "TLabelframe": ("TLabelframe.Label",),
    "TNotebook": ("TNotebook.Tab",),
    "TPanedwindow": ("Sash",),
    "Treeview": ("Treeview.Heading", "Treeview.Item", "Treeview.Cell"),
}
"""Parts of a compound widget that are styled separately from their parent.

Each suffix hangs off whatever style the widget was given, so a treeview using
``Wide.Treeview`` takes its headings from ``Wide.Treeview.Heading``. ``Sash`` is
the exception: not a suffix at all, but a bare top-level name.
"""
