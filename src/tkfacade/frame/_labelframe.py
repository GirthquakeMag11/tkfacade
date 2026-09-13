"""The captioned container: a frame that says what the group inside it is."""

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, ClassVar

from .._types import EdgePosition, Padding, PadValue, Relief
from ..widget import BaseWidget, Widget
from ._frame import Frame


class LabelFrame(Frame):
    """A themed frame with a caption on its border.

    Everything :class:`~tkfacade.Frame` is — a container to build a
    layout inside, with a relief, a padding, and a size it asks for —
    plus a caption saying what the group is for. Nothing the frame
    promises is narrowed here: ``ttk.LabelFrame`` answers every option
    a frame's properties read, so all four are inherited whole.

    The caption is one slot and so one setting. It may be a string, or
    a widget for the cases a string cannot serve — a
    :class:`~tkfacade.Checkbutton` captioning a group it enables is
    the usual one. Tk keeps a string and a widget as two options with
    the widget shadowing the string, which is its bookkeeping rather
    than a distinction worth passing on: :attr:`caption` is the one
    place either is set, and reading it answers whichever is showing.

    A widget caption is built as a **sibling** of the frame rather
    than inside it — the frame need not exist first that way, and Tk
    accepts either. It stays the caller's widget: it hears its own
    events and is laid out by nothing, this frame merely displaying
    it.

    Appearance comes from the ``TLabelframe`` style, with
    :attr:`relief` and :attr:`padding` the widget's own exceptions
    that win over it, as on a plain frame.
    """

    if TYPE_CHECKING:
        _tk: ttk.LabelFrame

    __slots__ = ("_caption_widget",)

    _widget_type: ClassVar[type[ttk.Frame | ttk.LabelFrame]] = ttk.LabelFrame

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        /,
        caption: str | Widget = "",
        *,
        caption_position: EdgePosition = "nw",
        relief: Relief = "flat",
        padding: Padding = 0,
        width: PadValue = 0,
        height: PadValue = 0,
    ) -> None:
        """Create the frame, captioned and empty.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the
                frame is created inside.
            caption (str | Widget): What sits on the border — a
                string, or a widget to show there instead. Defaults to
                ``""``, an uncaptioned frame.
            caption_position (EdgePosition): Where on the border the
                caption sits. Defaults to ``"nw"``, the top border at
                its left.
            relief (Relief): Border style. Defaults to ``"flat"``.
            padding (Padding): Space between the border and the
                children. Defaults to 0.
            width (PadValue): Width to ask for, honoured only with
                propagation off. Defaults to 0.
            height (PadValue): Height to ask for, honoured only with
                propagation off. Defaults to 0.
        """
        self._caption_widget: Widget | None = None
        super().__init__(parent, relief=relief, padding=padding, width=width, height=height)
        self._tk.configure(labelanchor=caption_position)
        self.caption = caption

    @property
    def caption(self) -> str | Widget:
        """What sits on the border: a string, or the widget showing there.

        Assigning either replaces whichever is showing. A widget must
        already exist — build it as a sibling of this frame, with the
        same parent — and remains the caller's: it is displayed here,
        not adopted, so it keeps its own events and its own lifetime.
        """
        if self._caption_widget is not None:
            return self._caption_widget
        return str(self._tk.cget("text"))

    @caption.setter
    def caption(self, value: str | Widget) -> None:
        if isinstance(value, Widget):
            self._caption_widget = value
            self._tk.configure(labelwidget=value._tk)
            return
        self._caption_widget = None
        # clearing the widget is what makes the string visible again
        self._tk["labelwidget"] = ""
        self._tk.configure(text=value)

    @property
    def caption_position(self) -> EdgePosition:
        """Where on the border the caption sits; read live from Tk.

        There is no centre. A caption is on one of the four borders,
        at one end of it or the other, which is the whole of what
        :data:`~tkfacade.EdgePosition` names.
        """
        return str(self._tk.cget("labelanchor"))  # type: ignore[return-value]

    @caption_position.setter
    def caption_position(self, value: EdgePosition) -> None:
        self._tk.configure(labelanchor=value)
