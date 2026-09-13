"""The TextLabel wrapper: the text-only half of the split Label.

A :class:`TextLabel` is a ``ttk.Label`` that holds nothing but text, so
the widget's ``anchor`` is free to say where that text sits within the
label — and :attr:`TextLabel.justify` is the horizontal spelling of it,
which is the behavior the split exists to make honest.
"""

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Final, cast

from .._types import Anchor, Justify
from ..look import Look
from ..widget import BaseWidget, Widget

_HORIZONTAL_OF_ANCHOR: Final[dict[Anchor, Justify]] = {
    "n": "center",
    "ne": "right",
    "e": "right",
    "se": "right",
    "s": "center",
    "sw": "left",
    "w": "left",
    "nw": "left",
    "center": "center",
}
"""The horizontal component each anchor positions text on, read as a justify value."""

_VERTICAL_OF_ANCHOR: Final[dict[Anchor, str]] = {
    "n": "n",
    "ne": "n",
    "e": "center",
    "se": "s",
    "s": "s",
    "sw": "s",
    "w": "center",
    "nw": "n",
    "center": "center",
}
"""The vertical component each anchor positions text on; ``center`` when none."""

_ANCHOR_OF_VERTICAL_AND_JUSTIFY: Final[dict[tuple[str, Justify], Anchor]] = {
    ("n", "left"): "nw",
    ("n", "center"): "n",
    ("n", "right"): "ne",
    ("s", "left"): "sw",
    ("s", "center"): "s",
    ("s", "right"): "se",
    ("center", "left"): "w",
    ("center", "center"): "center",
    ("center", "right"): "e",
}
"""Every anchor, as the pair of a vertical component and a justify value."""


class TextLabel(Widget):
    """A themed Tk label displaying nothing but text.

    Text is assigned through the plain :attr:`text` property, and where
    it sits within the label is :attr:`anchor` — the full compass word.
    :attr:`justify` is the horizontal spelling of the same position, so
    ``justify = "right"`` actually right-justifies the text rather than
    only aligning a multi-line block's lines against each other.

    Appearance comes from the ``TLabel`` style rather than from
    per-widget options: there are no colors, font, or relief to set
    here, and a label restyled through :class:`ttk.Style` follows.
    """

    if TYPE_CHECKING:
        _tk: ttk.Label

    __slots__ = ()

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        /,
        text: str = "",
        *,
        anchor: Anchor = "w",
        justify: Justify | None = None,
        wraplength: int = 0,
        width: int | None = None,
        look: Look | None = None,
    ) -> None:
        """Create the label with the text placed as given.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the label
                is created inside.
            text (str): The text to display. Defaults to ``""``, leaving
                the label textless.
            anchor (Anchor): Where the text sits within the label.
                Defaults to ``"w"``.
            justify (Justify | None): The horizontal half of where the
                text sits, applied after ``anchor`` so the two can be
                spelled in either order. Defaults to None, leaving
                ``anchor`` exactly as given.
            wraplength (int): The width in pixels at which a line wraps;
                0 wraps only on newlines. Defaults to 0.
            width (int | None): Width in characters; the label sizes to
                the text when None. Defaults to None.
            look (Look | None): The look to wear from the start; see
                :attr:`~tkfacade.widget.Widget.look`. Defaults to None,
                the library's base style.
        """
        self._tk = ttk.Label(
            self._as_master(parent),
            text=text,
            anchor=anchor,
            wraplength=wraplength,
        )
        if width is not None:
            self._tk.configure(width=width)
        super().__init__()
        if justify is not None:
            self._apply_justify(justify)
        if look is not None:
            self.look = look

    @property
    def text(self) -> str:
        """The displayed text; the empty string when none is set."""
        return str(self._tk.cget("text"))

    @text.setter
    def text(self, value: str) -> None:
        self._tk.configure(text=value)

    @property
    def anchor(self) -> Anchor:
        """Where the text sits within the label; the full compass word."""
        return cast(Anchor, str(self._tk.cget("anchor")))

    @anchor.setter
    def anchor(self, value: Anchor) -> None:
        self._tk.configure(anchor=value)

    @property
    def justify(self) -> Justify:
        """The horizontal half of where the text sits within the label.

        Read off the label's :attr:`anchor`, not stored separately, so
        the two always agree. Writing it replaces only the anchor's
        horizontal component, leaving its vertical one alone.
        """
        return _HORIZONTAL_OF_ANCHOR[self.anchor]

    @justify.setter
    def justify(self, value: Justify) -> None:
        self._apply_justify(value)

    def _apply_justify(self, value: Justify) -> None:
        """Write ``value`` over the anchor's horizontal component, keeping the vertical."""
        self._tk.configure(
            anchor=_ANCHOR_OF_VERTICAL_AND_JUSTIFY[_VERTICAL_OF_ANCHOR[self.anchor], value]
        )

    @property
    def wraplength(self) -> int:
        """The width in pixels at which a line wraps; 0 wraps only on newlines."""
        pixels = str(self._tk.cget("wraplength"))
        return int(pixels) if pixels else 0

    @wraplength.setter
    def wraplength(self, pixels: int) -> None:
        self._tk.configure(wraplength=pixels)

    @property
    def width(self) -> int | None:
        """The width in characters, or None when the label sizes to the text."""
        chars = str(self._tk.cget("width"))
        value = int(chars) if chars else 0
        return value if value else None

    @width.setter
    def width(self, value: int | None) -> None:
        self._tk.configure(width=value if value is not None else 0)
