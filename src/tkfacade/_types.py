"""Shared vocabulary: value aliases and the dicts Tk returns from ``*_info``."""

import tkinter as tk
from collections.abc import Callable, Coroutine, Sequence
from pathlib import Path
from typing import Any, Literal, TypedDict

type Command = Callable[[], object] | Callable[[], Coroutine[Any, Any, object]]
"""A dual-kind command: a plain callable or a coroutine function.

A plain callable, run on the mainloop like any Tk command, or a
coroutine function, scheduled fire-and-forget on the root's async core
— interchangeable everywhere a command is taken. The second arm of the
union is subsumed by the first; it is spelled out so the signature
says coroutine functions are accepted.
"""

type Sticky = str
"""Compass letters (a subset of ``"nsew"``) naming the cell edges a widget clings to."""

type PadValue = int | str
"""One padding amount: pixels, or any Tk screen-distance string (e.g. ``"2c"``)."""

type Pad = PadValue | tuple[PadValue, PadValue]
"""Symmetric padding, or an asymmetric ``(before, after)`` pair."""

type Anchor = Literal["n", "ne", "e", "se", "s", "sw", "w", "nw", "center"]
"""Compass position within available space."""

type Side = Literal["left", "right", "top", "bottom"]
"""One of the four edges of a rectangle, named without reference to a compass.

The side of the master a packed widget is placed against, and the edge of an
image a crop keeps.
"""

type Fill = Literal["none", "x", "y", "both"]
"""Axes along which a packed widget stretches to fill its parcel."""

type BorderMode = Literal["inside", "outside", "ignore"]
"""How place measures coordinates and sizes against the master's border."""

type Rel = str | float
"""A coordinate or size as a fraction of the master's dimension, usually 0.0 to 1.0."""

type Rect = tuple[int, int, int, int]
"""A screen-space ``(left, top, right, bottom)`` box, in pixels."""


type Color = str
"""A colour: ``"#rrggbb"``, ``"#rgb"``, or an X11 name.

Prefer hex. Tk reads the X11 colour database, so ``"tomato"`` resolves, but CSS
later overrode some of those values: Tk's ``"green"`` is ``#00FF00`` (CSS calls
that ``"lime"``) and Tk's ``"gray"`` is ``#BEBEBE`` against CSS's ``#808080``.
"""

type Padding = PadValue | tuple[PadValue, ...]
"""One to four screen distances, in CSS order, as ttk styles accept them.

``6`` is every side; ``(12, 6)`` is ``(horizontal, vertical)``; ``(l, t, r)``
takes bottom from top; ``(l, t, r, b)`` is each side. Distinct from
:data:`Pad`, which is the geometry managers' one-or-two-value form.
"""

type Relief = Literal["flat", "raised", "sunken", "groove", "ridge", "solid"]
"""Border drawing style."""

type Justify = Literal["left", "center", "right"]
"""Horizontal alignment of text within a widget.

On a text input (entry, spinbox, combobox) it is the value's own
alignment; on a :class:`~tkfacade.TextLabel` it is the horizontal half
of where the text sits in the label, spelled through the label's
``anchor``.
"""

type Compound = Literal["text", "image", "top", "bottom", "left", "right", "center", "none"]
"""Placement of an image relative to text when a widget carries both."""

type EdgePosition = Literal["nw", "n", "ne", "en", "e", "es", "se", "s", "sw", "ws", "w", "wn"]
"""A place on a rectangle's border: which edge, and where along it.

The first letter names the edge and the second the end of it, so
``"nw"`` is the top border at its left and ``"wn"`` the left border at
its top. There is no centre: a thing on a border is on one of them.

Shared rather than named for the first widget to want it — a
notebook's tabs and a label frame's caption both sit at one of these
twelve places, and the question they answer is the same one.
"""

type FontSpec = str | tuple[str, int] | tuple[str, int, str]
"""A named font, or ``(family, size)``, or ``(family, size, style)``.

The style component is space-separated: ``"bold italic"``,
``"bold underline overstrike"``.
"""

type ImageSpec = str | tuple[str, ...]
"""An image name, or a state-keyed sequence ``(default, "disabled", other)``.

Set through a style this is only a *default*, used while the widget's own
``-image`` is empty.
"""

type StateSpec[T] = Sequence[tuple[str | tuple[str, ...], T] | tuple[str, ...]]
"""Value list for :meth:`ttk.Style.map`: ``(state, value)`` pairs, first match wins.

A state may be negated with ``"!"`` (``"!disabled"``) or combined in a tuple
(``("pressed", "!disabled")`` requires both). An empty state matches every
state, which is how a theme can defeat :meth:`ttk.Style.configure` for an
option outright.
"""


type MediaSource = str | Path
"""Where media is loaded from: a filesystem path, or a URL as a string."""

type MenuDirection = Literal["above", "below", "left", "right", "flush"]
"""Where a menubutton's menu appears relative to the button.

``"flush"`` puts it over the button itself rather than beside it. The
menu still opens downward from wherever it lands; this names the corner
it is anchored to, not the direction it grows.
"""

type Orient = Literal["horizontal", "vertical"]
"""The axis a widget lays itself out along, and fills toward.

The orientation is fixed into the widget's style name rather than read from
this option alone — ``Horizontal.TProgressbar`` against ``Vertical.TProgressbar``
— so it decides appearance as well as direction.
"""

type SelectParam = Literal["extended", "browse", "none"]
"""Tk's ``selectmode``: many rows selectable, one, or none at all.

Shared by every widget that offers a selection over rows, so that the
two booleans a caller states — whether selection is possible, and
whether more than one thing may be selected — fold to Tk's word in one
place rather than once per widget.
"""

type ScrollUnit = Literal["steps", "pages"]
"""What one unit of relative scrolling counts.

A step is whatever the widget itself counts as one — a line for a text
box, a row for a tree. A page is a viewport's worth.
"""

type Arrangement = Literal["top-bottom", "bottom-top", "left-right", "right-left"]
"""How a labelled widget's two halves sit against each other.

Each value names both positions in order: the first word is where the label
goes and the second is where the widget it labels goes, so ``"top-bottom"``
puts the label above and ``"right-left"`` puts it to the right. Naming both
is what lets the pair be reversed — an axis alone (:data:`Orient`) says which
way they stack but not which of them comes first.
"""


GridInfo = TypedDict(
    "GridInfo",
    {
        "in": tk.Misc,
        "column": int,
        "columnspan": int,
        "row": int,
        "rowspan": int,
        "ipadx": PadValue,
        "ipady": PadValue,
        "padx": Pad,
        "pady": Pad,
        "sticky": Sticky,
    },
    total=False,
)
"""A widget's grid options as *returned* by Tk (``grid_info``), keyed ``in``."""


PackInfo = TypedDict(
    "PackInfo",
    {
        "in": tk.Misc,
        "anchor": Anchor,
        "expand": int,
        "fill": Fill,
        "side": Side,
        "ipadx": PadValue,
        "ipady": PadValue,
        "padx": Pad,
        "pady": Pad,
    },
    total=False,
)
"""A widget's pack options as *returned* by Tk (``pack_info``), keyed ``in``.

No ``after``/``before`` keys, unlike ``PackSetOptions``: those are
placement directives resolved at pack time, not stored options —
and ``expand`` comes back as Tk's 0/1 int, not the bool it was set
with.
"""


PlaceInfo = TypedDict(
    "PlaceInfo",
    {
        "in": tk.Misc,
        "anchor": Anchor,
        "bordermode": BorderMode,
        "x": PadValue,
        "y": PadValue,
        "relx": Rel,
        "rely": Rel,
        "width": PadValue,
        "height": PadValue,
        "relwidth": Rel,
        "relheight": Rel,
    },
    total=False,
)
"""A widget's place options as *returned* by Tk (``place_info``), keyed ``in``."""
