"""The ChoiceBox wrapper: one value chosen from a set, in a dropdown."""

import tkinter as tk
from collections.abc import Sequence
from tkinter import ttk
from typing import TYPE_CHECKING

from .._types import Justify
from ..events import Destroyed, Event
from ..look import Look
from ..observable import ObservableStr
from ..widget import BaseWidget, Widget
from ._set import NOTHING_CHOSEN, ChoiceSet, check_option


class ChoiceBox(Widget, ChoiceSet):
    """A dropdown holding one value chosen from a set of options.

    Not a text input: nothing here can be typed into, the value's
    whole domain is :attr:`options`, and the members a text input
    would bring — a cursor, a selection, a read-only mode — would all
    be answers to questions this widget does not raise. Where a caller
    wants to type as well as choose, :class:`~tkfacade.Combobox` is
    that widget.

    The choosing itself is :class:`~tkfacade.ChoiceSet`, worn — the
    chosen value an :class:`~tkfacade.ObservableStr`, the box's own
    unless one is passed in, shared with whatever else watches or
    drives it. A user's pick is announced by
    ``Virtual(VirtualEvent.COMBOBOX_SELECTED)``, which Tk fires for
    the dropdown only and never for a write.

    ``""`` is the value meaning nothing has been chosen, which is a
    real state rather than an error: a form's box starts there. Tk
    itself models it as no row selected in the list.

    Tk does not enforce the domain — a readonly combobox accepts any
    value the program hands it — so :attr:`chosen` enforces it here.
    A caller driving a shared observable directly reaches the widget
    without passing that check, as it does on the progress bars and
    the scales.

    Appearance comes from the ``TCombobox`` style. The dropdown itself
    is a classic Tk listbox no ttk style reaches (`hazards/tkinter.md`,
    *Styling*).
    """

    if TYPE_CHECKING:
        _tk: ttk.Combobox

    __slots__ = ("_chosen",)

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        /,
        options: Sequence[str] = (),
        *,
        chosen: str | ObservableStr = NOTHING_CHOSEN,
        visible_rows: int = 10,
        width: int = 20,
        justify: Justify = "left",
        enabled: bool = True,
        look: Look | None = None,
    ) -> None:
        """Create the box, and the observable behind it if none is given.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the
                box is created inside.
            options (Sequence[str]): The values that may be chosen.
                Defaults to ``()``, a box with nothing to choose from.
            chosen (str | ObservableStr): The starting value, or the
                observable already holding it, shared with whatever
                else watches or drives that choice. Defaults to
                ``""``, meaning nothing chosen yet.
            visible_rows (int): How many options the dropdown shows
                before it scrolls. Defaults to 10.
            width (int): Width in characters. Defaults to 20.
            justify (Justify): How the value aligns. Defaults to
                ``"left"``.
            enabled (bool): Whether the box starts choosable. Defaults
                to True.
            look (Look | None): The look to wear from the start; see
                :attr:`~tkfacade.widget.Widget.look`. Defaults to None,
                the library's base style.

        Raises:
            ValueError: If ``visible_rows`` is below 1, or if
                ``chosen`` is a plain string that is neither ``""``
                nor one of ``options``.
        """
        if visible_rows < 1:
            raise ValueError(f"visible_rows must be at least 1, not {visible_rows}")
        offered = tuple(options)
        if not isinstance(chosen, ObservableStr):
            check_option(chosen, offered)
        master = self._as_master(parent)
        self._chosen = chosen if isinstance(chosen, ObservableStr) else ObservableStr(chosen)
        self._tk = ttk.Combobox(
            master,
            values=offered,
            textvariable=self._chosen.transport_for(master),
            height=visible_rows,
            width=width,
            justify=justify,
            # readonly rather than disabled: a chooser refuses the keyboard but keeps the dropdown live
            state="readonly" if enabled else "disabled",
        )
        self._tk._observables = (self._chosen,)  # type: ignore[attr-defined]
        super().__init__()
        self.bind(Destroyed(), self._give_back_transport)
        if look is not None:
            self.look = look

    def _give_back_transport(self, _event: Event) -> None:
        """Release the transport ride construction took; the widget is done.

        Bound to :class:`~tkfacade.events.Destroyed` so a shared
        observable never counts a dead widget among its riders
        (`hazards/tkinter.md`, *Variables*: a `tk.Variable` pins its
        interpreter).
        """
        self._chosen.release_transport()

    @property
    def options(self) -> tuple[str, ...]:
        """The values that may be chosen; read live from Tk.

        Assigning replaces the set. :attr:`chosen` is left where it
        is, even where it is no longer among them — the box then shows
        it with nothing selected in the list, which is the state a box
        starts in. Refusing the replacement instead would make
        reloading a list of options raise for the ordinary reason that
        the old choice is gone.
        """
        return tuple(str(value) for value in self._tk.cget("values"))

    @options.setter
    def options(self, values: Sequence[str]) -> None:
        self._tk.configure(values=tuple(values))

    @property
    def visible_rows(self) -> int:
        """How many options the dropdown shows before it scrolls."""
        return int(self._tk.cget("height"))

    @visible_rows.setter
    def visible_rows(self, value: int) -> None:
        if value < 1:
            raise ValueError(f"visible_rows must be at least 1, not {value}")
        self._tk.configure(height=value)

    @property
    def justify(self) -> Justify:
        """How the value aligns within the box."""
        return str(self._tk.cget("justify"))  # type: ignore[return-value]

    @justify.setter
    def justify(self, value: Justify) -> None:
        self._tk.configure(justify=value)

    @property
    def enabled(self) -> bool:
        """Whether the box can be opened and chosen from; read live from Tk."""
        return not self._tk.instate(["disabled"])

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._tk.configure(state="readonly" if value else "disabled")
