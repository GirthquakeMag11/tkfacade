"""The Combobox wrapper: a text input that offers suggestions."""

import tkinter as tk
from collections.abc import Sequence
from tkinter import ttk
from typing import TYPE_CHECKING, ClassVar

from .._types import Justify
from ..look import Look
from ..observable import ObservableStr
from ..widget import BaseWidget
from ._entry import Entry


class Combobox(Entry):
    """A themed text input with a dropdown of suggestions.

    Everything :class:`~tkfacade.Entry` offers works here — the
    content, its observable, the selection, the cursor — and the
    dropdown is an addition rather than a restriction: **the value is
    not bound by the suggestions.** A caller may type anything, and
    assigning :attr:`text` accepts anything. Where the value must be
    one of a set, :class:`~tkfacade.ChoiceBox` is the widget for that
    and this one is not.

    A user's pick is announced by
    ``Virtual(VirtualEvent.COMBOBOX_SELECTED)``, which Tk fires for
    the dropdown only — never for a write through the observable — so
    it carries the same user-only meaning ``command`` carries on the
    button family.

    One clause of the inherited contract is refused outright: what is
    narrowed is :class:`~tkfacade.AbstractTextInterface`'s own promise
    that a read-only input keeps its place in focus traversal and stays
    selectable and copyable. This widget cannot keep it: the Tk state
    that would keep focus — ``readonly`` — leaves the dropdown live,
    so a "read-only" combobox would still have its value changed by
    the user. :meth:`disable` therefore turns the widget off outright,
    and a disabled combobox is not focusable and not copyable.
    Assigning :attr:`text` works in either mode, as the contract
    requires.

    Tk's ``postcommand`` — the hook that runs just before the dropdown
    appears, for filling the list late — is not wrapped: its whole
    purpose is to finish before the list is shown, so a coroutine
    cannot serve it.

    Appearance comes from the ``TCombobox`` style, with the same font
    exception the rest of the family carries. The dropdown itself is a
    classic Tk listbox no ttk style reaches (`hazards/tkinter.md`,
    *Styling*).
    """

    if TYPE_CHECKING:
        _tk: ttk.Combobox

    __slots__ = ()

    _widget_type: ClassVar[type[ttk.Entry]] = ttk.Combobox

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        /,
        text: str | ObservableStr = "",
        *,
        suggestions: Sequence[str] = (),
        visible_rows: int = 10,
        width: int = 20,
        justify: Justify = "left",
        mask: str = "",
        look: Look | None = None,
    ) -> None:
        """Create the combobox, and the observable behind it if none is given.

        There is no ``read_only``: a combobox locked out of typing is
        still a chooser, which is :class:`~tkfacade.ChoiceBox`'s job
        rather than a mode of this one. :meth:`disable` turns the whole
        widget off.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the
                combobox is created inside.
            text (str | ObservableStr): The content — a starting
                string, or the observable already holding it, shared
                with whatever else watches or drives that value.
                Defaults to ``""``.
            suggestions (Sequence[str]): The strings the dropdown
                offers. Defaults to ``()``, a combobox whose dropdown
                is empty. They constrain nothing.
            visible_rows (int): How many suggestions the dropdown
                shows before it scrolls. Defaults to 10.
            width (int): Width in characters. Defaults to 20.
            justify (Justify): How the content aligns. Defaults to
                ``"left"``.
            mask (str): Character to display in place of each real
                one. Defaults to ``""``, showing the content itself.
            look (Look | None): The look to wear from the start; see
                :attr:`~tkfacade.widget.Widget.look`. Defaults to None,
                the library's base style.

        Raises:
            ValueError: If ``visible_rows`` is below 1, which Tk would
                take and render as a dropdown nothing can be picked
                from.
        """
        if visible_rows < 1:
            raise ValueError(f"visible_rows must be at least 1, not {visible_rows}")
        super().__init__(parent, text, width=width, justify=justify, mask=mask)
        self._tk.configure(values=tuple(suggestions), height=visible_rows)
        if look is not None:
            self.look = look

    @property
    def disabled(self) -> bool:
        """Whether the widget is turned off; read live from Tk.

        Off means off, not read-only: see the refusal in the class
        body. A disabled combobox refuses typing *and* the dropdown,
        and drops out of focus traversal.
        """
        return self._tk.instate(["disabled"])

    @property
    def suggestions(self) -> tuple[str, ...]:
        """The strings the dropdown offers; they constrain nothing.

        Assigning replaces the list. The content is untouched by the
        replacement, even where it is no longer among the offered
        strings, since it never had to be.
        """
        return tuple(str(value) for value in self._tk.cget("values"))

    @suggestions.setter
    def suggestions(self, values: Sequence[str]) -> None:
        self._tk.configure(values=tuple(values))

    @property
    def visible_rows(self) -> int:
        """How many suggestions the dropdown shows before it scrolls."""
        return int(self._tk.cget("height"))

    @visible_rows.setter
    def visible_rows(self, value: int) -> None:
        if value < 1:
            raise ValueError(f"visible_rows must be at least 1, not {value}")
        self._tk.configure(height=value)

    def disable(self) -> None:
        """Turn the widget off; the content is left alone.

        Unlike an :class:`~tkfacade.Entry`, this locks out the
        dropdown as well as the keyboard, and costs focus traversal
        with it — the refusal the class body records.
        """
        self._tk.configure(state="disabled")

    def enable(self) -> None:
        """Turn the widget back on; the content is left alone."""
        self._tk.configure(state="normal")
