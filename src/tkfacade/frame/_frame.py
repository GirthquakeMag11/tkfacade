"""The plain container: a themed frame to build a layout inside."""

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, ClassVar

from .._types import Padding, PadValue, Relief
from ..look import Look
from ..widget import BaseWidget, Widget


class Frame(Widget):
    """A themed Tk frame: a container to build a layout inside.

    A frame masters whatever is created in it and is itself placed by
    its own master's geometry manager, so it is the seam a layout nests
    at. :attr:`padding` is the space it keeps between its border and
    those children; :attr:`width` and :attr:`height` are what it *asks*
    for, which a frame overrides by sizing to its children unless
    propagation is turned off with
    :meth:`~tkfacade.widget.ContainerWidget.grid_propagate` or
    :meth:`~tkfacade.widget.ContainerWidget.pack_propagate`.

    Appearance comes from the ``TFrame`` style rather than from
    per-widget options: there is no colour to set here, and a frame
    restyled through :class:`ttk.Style` follows. :attr:`relief` and
    :attr:`padding` are the exceptions, and being the widget's own they
    win outright over the same options set in a style.
    """

    __slots__ = ()

    if TYPE_CHECKING:
        _tk: ttk.Frame | ttk.LabelFrame

    _widget_type: ClassVar[type[ttk.Frame | ttk.LabelFrame]] = ttk.Frame
    """The Tk widget this wrapper drives.

    The one seam the container family is built on. A frame's four
    options — relief, padding, and the two requested sizes — are
    answered by every ttk container, so a subclass over one of them
    names its widget here and inherits the properties whole.
    :class:`~tkfacade.LabelFrame` is the standing example.
    """

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        /,
        *,
        relief: Relief = "flat",
        padding: Padding = 0,
        width: PadValue = 0,
        height: PadValue = 0,
        look: Look | None = None,
    ) -> None:
        """Create the empty frame.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the
                frame is created inside.
            relief (Relief): Border style of the frame. Defaults to
                ``"flat"``, meaning no visible border.
            padding (Padding): Space between the frame's border and its
                children. Defaults to 0, meaning none.
            width (PadValue): Width to ask for, honoured only with
                propagation off. Defaults to 0, meaning ask for nothing
                and size to the children.
            height (PadValue): Height to ask for, honoured only with
                propagation off. Defaults to 0, meaning ask for nothing
                and size to the children.
            look (Look | None): The look to wear from the start; see
                :attr:`~tkfacade.widget.Widget.look`. Defaults to None,
                the library's base style.
        """
        self._tk = self._widget_type(
            self._as_master(parent),
            relief=relief,
            padding=padding,  # type: ignore[arg-type]
            width=width,
            height=height,
        )
        super().__init__()
        if look is not None:
            self.look = look

    @property
    def relief(self) -> Relief:
        """Border style of the frame, which wins over a relief asked for by a style."""
        return str(self._tk.cget("relief"))  # type: ignore[return-value]

    @relief.setter
    def relief(self, value: Relief) -> None:
        self._tk.configure(relief=value)

    @property
    def padding(self) -> tuple[PadValue, ...]:
        """Space between the frame's border and its children, in CSS order.

        Always a tuple, whatever shape it was set in: Tk keeps a single
        amount as a one-element list, so ``6`` assigned answers ``(6,)``
        and the constructor's own default answers ``(0,)``. Clearing the
        padding by assigning ``""`` is the one case answering ``()``.
        """
        amounts = self._tk.cget("padding")
        if not amounts:
            return ()
        return tuple(amount if isinstance(amount, int) else str(amount) for amount in amounts)

    @padding.setter
    def padding(self, value: Padding) -> None:
        self._tk.configure(padding=value)  # type: ignore[arg-type]

    @property
    def width(self) -> int:
        """The width the frame asks for, in pixels; 0 asks for nothing.

        What it asks for rather than what it gets: a frame sizes to its
        children instead unless propagation is turned off with
        :meth:`~tkfacade.widget.ContainerWidget.grid_propagate` or
        :meth:`~tkfacade.widget.ContainerWidget.pack_propagate` — and
        turned off *before* the children are laid out, since the call
        holds the size the frame has settled at rather than restoring
        this one. Assigning again afterwards is the way back.

        A screen distance assigned is answered as the pixels it resolves
        to, so ``"2c"`` reads back as a count that depends on the display.
        """
        return self._tk.winfo_pixels(self._tk.cget("width"))

    @width.setter
    def width(self, value: PadValue) -> None:
        self._tk.configure(width=value)

    @property
    def height(self) -> int:
        """The height the frame asks for, in pixels; 0 asks for nothing.

        What it asks for rather than what it gets, on the same terms as
        :attr:`width`.
        """
        return self._tk.winfo_pixels(self._tk.cget("height"))

    @height.setter
    def height(self, value: PadValue) -> None:
        self._tk.configure(height=value)
