"""The ChoiceButtons wrapper: one value chosen from a set, as a bank of buttons."""

import concurrent.futures
import tkinter as tk
from collections.abc import Sequence
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from .._command import dispatch_command
from .._types import Command, ImageSpec, Orient
from ..events import ACTIVATED, Destroyed, Event
from ..look import Look
from ..media import ImageInput, ImageWrapper, PhotoImage
from ..observable import ObservableStr
from ..widget import BaseWidget, Widget
from ._set import NOTHING_CHOSEN, ChoiceSet, check_option


class ChoiceButton:
    """One button of a bank, of which exactly one is chosen.

    Never built alone — a :class:`ChoiceButtons` builds its whole bank
    at once, because a lone choice bound to an observable nothing else
    shares is permanently chosen and says nothing, the way the menu's
    choice rows say of themselves. A handle rather than a widget: the
    bank owns its buttons' lifetimes and geometry, so the handle offers
    what is this button's own — its value, its face, its command — and
    nothing that would compete with the bank.

    The surface matches :class:`~tkfacade.ChoiceRow` name for name, the
    way :class:`~tkfacade.Checkbutton` matches its menu row: the same
    concept met in a menu or in a bank asks for the same words.
    """

    __slots__ = ("_bank", "_chosen", "_command", "_command_tasks", "_photo", "_tk_button", "_value")

    def __init__(
        self,
        bank: ChoiceButtons,
        value: str,
        command: Command | None,
        enabled: bool,
        /,
    ) -> None:
        """Build this button's ``ttk.Radiobutton`` as a child of the bank.

        Args:
            bank (ChoiceButtons): The bank this button belongs to.
            value (str): What choosing this button writes, and its
                starting text.
            command (Command | None): Run when this button is chosen,
                of either kind; None is nothing beside the write.
            enabled (bool): Whether the button starts choosable.
        """
        self._bank = bank
        self._chosen = bank._chosen
        self._value = value
        self._command = command
        self._command_tasks: set[concurrent.futures.Future[Any]] = set()
        self._photo: PhotoImage | None = None
        self._tk_button = ttk.Radiobutton(
            bank._tk,
            text=value,
            value=value,
            command=self._run_command,
            state="normal" if enabled else "disabled",
        )

    def _run_command(self) -> None:
        """Run the held command, then emit the activation; None runs nothing.

        The emission lands on the bank — the widget subscribers hold —
        with this button in the payload to say which member it was.
        """
        held = self._command
        if held is not None:
            dispatch_command(self._tk_button, held, self._command_tasks, f"the command of {self!r}")
        self._bank.emit(ACTIVATED, {"button": self})

    def __repr__(self) -> str:
        """Name the class and this button's value."""
        return f"<{type(self).__name__} {self._value!r}>"

    @property
    def value(self) -> str:
        """What choosing this button writes into the bank's observable."""
        return self._value

    @property
    def chosen(self) -> bool:
        """Whether this button is the one currently chosen."""
        return self._chosen.value == self._value

    def choose(self) -> None:
        """Make this the chosen button, as picking it would."""
        self._chosen.value = self._value

    @property
    def text(self) -> str:
        """The text drawn on the button.

        Assigning renames what is drawn and nothing else — the button
        still writes :attr:`value` when chosen, so the words a user
        sees and the value a program stores may differ.
        """
        return str(self._tk_button.cget("text"))

    @text.setter
    def text(self, value: str) -> None:
        self._tk_button.configure(text=value)

    @property
    def enabled(self) -> bool:
        """Whether the button can be chosen; read live from Tk."""
        return not self._tk_button.instate(["disabled"])

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._tk_button.state(["!disabled" if value else "disabled"])

    @property
    def image(self) -> ImageSpec | None:
        """The picture drawn beside the text, or None where there is none.

        Answers Tk's own handle for the image, the stratum this relays
        verbatim; assign any :data:`~tkfacade.ImageInput` to replace it,
        or None to take it away.
        """
        held = str(self._tk_button.cget("image"))
        return held or None

    @image.setter
    def image(self, value: ImageInput | None) -> None:
        photo = ImageWrapper(value).photo_for(self._tk_button) if value is not None else None
        self._tk_button.configure(image="" if photo is None else photo)
        self._photo = photo

    @property
    def command(self) -> Command | None:
        """What choosing the button runs; None is nothing.

        Assigning swaps what future choices run. Coroutine runs
        already in flight from the old command are left to finish —
        death narrows the future, never the present.
        """
        return self._command

    @command.setter
    def command(self, value: Command | None) -> None:
        self._command = value

    def invoke(self) -> None:
        """Do what choosing the button does.

        A disabled button does nothing, ttk's own guard rather than a
        second one written here.
        """
        self._tk_button.invoke()


class ChoiceButtons(Widget, ChoiceSet):
    """A bank of themed radiobuttons, of which exactly one is chosen.

    The worn :class:`~tkfacade.ChoiceSet` — one value chosen from a set,
    in a shared :class:`~tkfacade.ObservableStr` — drawn as the set
    itself: one ``ttk.Radiobutton`` per option in a frame, and that
    frame is what a caller lays out. The set is the unit here as it is
    in a menu: the bank is born whole from ``options``, its buttons
    come back as :class:`ChoiceButton` handles, and an empty bank is
    refused because a set with no members is not a set.

    The bank takes one transport ride on the shared observable and
    hands the same variable to every button, so a destroyed bank gives
    back exactly the one ride construction took.

    Appearance comes from the ``TRadiobutton`` style. The bank's
    ``orient`` is layout alone — Tk styles a radiobutton the same
    whichever way its bank runs.
    """

    if TYPE_CHECKING:
        _tk: ttk.Frame

    __slots__ = ("_buttons", "_chosen", "_orient")

    def _look_targets(self) -> tuple[tk.Misc, ...]:
        """Every button of the bank: one look dresses the whole set."""
        return tuple(button._tk_button for button in self._buttons)

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        /,
        options: Sequence[str],
        *,
        chosen: str | ObservableStr = NOTHING_CHOSEN,
        orient: Orient = "vertical",
        command: Command | None = None,
        enabled: bool = True,
        look: Look | None = None,
    ) -> None:
        """Create the bank, and the observable behind it if none is given.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the
                bank is created inside.
            options (Sequence[str]): The values that may be chosen,
                one button per value, each value also its button's
                starting text.
            chosen (str | ObservableStr): The starting value, or the
                observable already holding it, shared with whatever
                else watches or drives that choice. Defaults to ``""``,
                meaning nothing chosen yet.
            orient (Orient): The axis the buttons run along. Defaults
                to ``"vertical"``.
            command (Command | None): Run when a button is chosen — a
                plain callable on the mainloop, a coroutine function on
                the root's async core. Each button holds its own, so
                one can be swapped without the rest. Defaults to None,
                nothing beside the write.
            enabled (bool): Whether the buttons start choosable.
                Defaults to True.
            look (Look | None): The look to wear from the start; see
                :attr:`~tkfacade.widget.Widget.look`. Defaults to None,
                the library's base style.

        Raises:
            ValueError: If ``options`` is empty, or if ``chosen`` is a
                plain string that is neither ``""`` nor one of
                ``options``.
        """
        offered = tuple(options)
        if not offered:
            raise ValueError("a choice set needs at least one option")
        if not isinstance(chosen, ObservableStr):
            check_option(chosen, offered)
        master = self._as_master(parent)
        self._chosen = chosen if isinstance(chosen, ObservableStr) else ObservableStr(chosen)
        self._orient: Orient = orient
        self._tk = ttk.Frame(master)
        self._buttons = tuple(ChoiceButton(self, value, command, enabled) for value in offered)
        # one ride for the whole bank: every button shares the variable, so teardown owes one release
        transport = self._chosen.transport_for(master)
        for button in self._buttons:
            button._tk_button.configure(variable=transport)
        self._grid_buttons()
        self._tk._observables = (self._chosen,)  # type: ignore[attr-defined]
        super().__init__()
        self._route_events(*(button._tk_button for button in self._buttons))
        self.bind(Destroyed(), self._give_back_transport)
        if look is not None:
            self.look = look

    def _give_back_transport(self, _event: Event) -> None:
        """Release the one transport ride construction took; the bank is done.

        Bound to :class:`~tkfacade.events.Destroyed` so a shared
        observable never counts a dead bank among its riders
        (`hazards/tkinter.md`, *Variables*: a `tk.Variable` pins its
        interpreter).
        """
        self._chosen.release_transport()

    def _grid_buttons(self) -> None:
        """Grid every button along the current axis.

        Writes the whole layout rather than the part that changed:
        ``grid`` merges into what is already in place, so the cells a
        previous orientation used are cleared by being written over,
        and the stale axis's cells are forgotten explicitly.
        """
        vertical = self._orient == "vertical"
        for position, button in enumerate(self._buttons):
            button._tk_button.grid_forget()
            row, column = (position, 0) if vertical else (0, position)
            button._tk_button.grid(row=row, column=column, sticky="w")

    @property
    def buttons(self) -> tuple[ChoiceButton, ...]:
        """The bank's buttons, in option order."""
        return self._buttons

    @property
    def options(self) -> tuple[str, ...]:
        """The values that may be chosen, one per button.

        Read off the buttons rather than stored: a value is choosable
        exactly while a button writes it.
        """
        return tuple(button.value for button in self._buttons)

    @property
    def orient(self) -> Orient:
        """The axis the buttons run along.

        Assigning re-lays the whole bank out along the new axis.
        """
        return self._orient

    @orient.setter
    def orient(self, value: Orient) -> None:
        self._orient = value
        self._grid_buttons()

    @property
    def enabled(self) -> bool:
        """Whether every button can be chosen; assigning writes them all.

        True only while every button is enabled — a bank with one
        button disabled through its handle answers False, and
        assigning True re-enables that button with the rest.
        """
        return all(button.enabled for button in self._buttons)

    @enabled.setter
    def enabled(self, value: bool) -> None:
        for button in self._buttons:
            button.enabled = value
