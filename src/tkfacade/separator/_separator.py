"""The Separator wrapper: a themed rule dividing what sits either side of it."""

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from .._types import Orient
from ..look import Look
from ..widget import BaseWidget, Widget


class Separator(Widget):
    """A themed line drawn between neighbours, horizontal or vertical.

    The whole of the widget: it holds no value, masters nothing, and
    answers no interactions of its own. What it offers a caller is
    :attr:`orient`, the axis the line runs along, and a place in the
    layout — a divider drawn by the theme rather than faked with a
    one-pixel frame.

    Appearance comes from the ``TSeparator`` style rather than from
    per-widget options, and here that is the whole story rather than a
    rule with exceptions: ``ttk.Separator`` has no appearance options
    at all, so a separator's thickness and color are the style's
    business without remainder.
    """

    if TYPE_CHECKING:
        _tk: ttk.Separator

    __slots__ = ()

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        /,
        *,
        orient: Orient = "horizontal",
        look: Look | None = None,
    ) -> None:
        """Create the separator on the given axis.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the
                separator is created inside.
            orient (Orient): The axis the line runs along. Defaults to
                ``"horizontal"``, a rule dividing what is above it from
                what is below.
            look (Look | None): The look to wear from the start; see
                :attr:`~tkfacade.widget.Widget.look`. Defaults to None,
                the library's base style.
        """
        master = self._as_master(parent)
        self._tk = ttk.Separator(master, orient=orient)
        super().__init__()
        if look is not None:
            self.look = look

    @property
    def orient(self) -> Orient:
        """The axis the line runs along; read live, and assignable.

        Assignable because Tk allows it, which is worth saying beside
        :attr:`~tkfacade.PanedFrame.orient`, where Tk refuses the same
        option — "attempt to change read-only option" — and the wrapper
        reports that refusal as a read-only property. The two postures
        differ because the widgets differ, not because the library is
        inconsistent about the option's name.

        Read through ``str`` rather than passed through: Tk answers an
        enumerated option with an index object that prints as the word
        but compares unequal to it (`hazards/tkinter.md`, *Query answers*).
        """
        return str(self._tk.cget("orient"))  # type: ignore[return-value]

    @orient.setter
    def orient(self, value: Orient) -> None:
        self._tk.configure(orient=value)
