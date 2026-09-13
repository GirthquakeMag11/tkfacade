"""The ChoiceSpinner wrapper: one value chosen from a set, stepped through."""

import concurrent.futures
import tkinter as tk
from collections.abc import Sequence
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from .._command import dispatch_command
from .._types import Command, Justify
from ..events import ACTIVATED, Destroyed, Event
from ..look import Look
from ..observable import ObservableStr
from ..widget import BaseWidget, Widget
from ._set import NOTHING_CHOSEN, ChoiceSet, check_option


class ChoiceSpinner(Widget, ChoiceSet):
    """A pair of arrows stepping through a set of options, one at a time.

    The same thing :class:`~tkfacade.ChoiceBox` is — the worn
    :class:`~tkfacade.ChoiceSet`, one value chosen from a set in a
    shared :class:`~tkfacade.ObservableStr` —
    shown as a step-through instead of a dropdown. It lives beside the
    choice box rather than beside the spinboxes for that reason: what
    it has in common with a :class:`~tkfacade.IntSpinbox` is a pair of
    arrows, and what it has in common with a choice box is everything
    else.

    Which to reach for is a question about the options rather than
    about the widget. A handful a user will step past comfortably —
    sizes, difficulties, a rating — suits this; a list they would
    rather scan suits the box.

    A user's step is announced by :attr:`command`, which Tk runs for
    the arrows only and never for a write. The options do not wrap by
    default: stepping stops at each end, as a bounded set usually
    should.

    ``""`` is the value meaning nothing has been chosen, which is a
    real state rather than an error, and stepping from it lands on the
    first option.

    Tk enforces no domain — a spinbox accepts any value handed to it,
    listed or not — so :attr:`chosen` enforces it here. A caller
    driving a shared observable directly reaches the widget without
    passing that check, as it does on the choice box, the scales and
    the progress bars.

    Appearance comes from the ``TSpinbox`` style.
    """

    if TYPE_CHECKING:
        _tk: ttk.Spinbox

    __slots__ = ("_chosen", "_command", "_command_tasks")

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        /,
        options: Sequence[str] = (),
        *,
        chosen: str | ObservableStr = NOTHING_CHOSEN,
        wraps: bool = False,
        command: Command | None = None,
        enabled: bool = True,
        width: int = 20,
        justify: Justify = "left",
        look: Look | None = None,
    ) -> None:
        """Create the spinner, and the observable behind it if none is given.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the
                spinner is created inside.
            options (Sequence[str]): The values that may be chosen.
                Defaults to ``()``, a spinner with nothing to choose
                from.
            chosen (str | ObservableStr): The starting value, or the
                observable already holding it, shared with whatever
                else watches or drives that choice. Defaults to
                ``""``, meaning nothing chosen yet.
            wraps (bool): Whether stepping past an end cycles round.
                Defaults to False, stopping at the end.
            command (Command | None): Run on each user
                step — a plain callable on the mainloop, a coroutine
                function on the root's async core. Defaults to None.
            enabled (bool): Whether the spinner may be used. Defaults
                to True.
            width (int): Width in characters. Defaults to 20.
            justify (Justify): How the value aligns. Defaults to
                ``"left"``.
            look (Look | None): The look to wear from the start; see
                :attr:`~tkfacade.widget.Widget.look`. Defaults to None,
                the library's base style.

        Raises:
            ValueError: If ``chosen`` is a plain string that is
                neither ``""`` nor one of ``options``.
        """
        offered = tuple(options)
        if not isinstance(chosen, ObservableStr):
            check_option(chosen, offered)
        master = self._as_master(parent)
        self._chosen = chosen if isinstance(chosen, ObservableStr) else ObservableStr(chosen)
        self._command: Command | None = command
        self._command_tasks: set[concurrent.futures.Future[Any]] = set()
        self._tk = ttk.Spinbox(
            master,
            values=offered,
            textvariable=self._chosen.transport_for(master),
            wrap=wraps,
            command=self._run_command,
            # readonly rather than normal: the options are the domain
            state="readonly" if enabled else "disabled",
            width=width,
            justify=justify,
        )
        self._tk._observables = (self._chosen,)  # type: ignore[attr-defined]
        super().__init__()
        self.bind(Destroyed(), self._give_back_transport)
        if look is not None:
            self.look = look

    def _run_command(self) -> None:
        """Run the held command; None is nothing.

        Tk calls this for a step and for nothing else — not for a
        write through the variable — so it is the user's channel, as
        ``command`` is across the button family.
        :data:`~tkfacade.ACTIVATED` is emitted after the command,
        command or no command, on the same user-only terms.
        """
        held = self._command
        if held is not None:
            dispatch_command(self._tk, held, self._command_tasks, f"the command of {self!r}")
        self.emit(ACTIVATED)

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
        is, even where it is no longer among them, as on
        :class:`~tkfacade.ChoiceBox`: reloading a set of options is
        ordinary, and refusing it because the old choice is gone would
        make the ordinary case raise.
        """
        return tuple(str(value) for value in self._tk.cget("values"))

    @options.setter
    def options(self, values: Sequence[str]) -> None:
        self._tk.configure(values=tuple(values))

    @property
    def wraps(self) -> bool:
        """Whether stepping past an end cycles round to the other."""
        return bool(self._tk.cget("wrap"))

    @property
    def command(self) -> Command | None:
        """What a user's step runs; None is nothing extra.

        Assigning swaps what future steps run. Coroutine runs already
        in flight from the old command are left to finish — death
        narrows the future, never the present.
        """
        return self._command

    @command.setter
    def command(self, value: Command | None) -> None:
        self._command = value

    @property
    def enabled(self) -> bool:
        """Whether the spinner may be stepped; read live from Tk."""
        return not self._tk.instate(["disabled"])

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._tk.configure(state="readonly" if value else "disabled")

    def step_up(self) -> None:
        """Move to the next option; stops at the last unless :attr:`wraps`.

        The same route the arrows take, so it runs :attr:`command` as
        a user's press would.
        """
        self._tk.event_generate("<<Increment>>")

    def step_down(self) -> None:
        """Move to the previous option; stops at the first unless :attr:`wraps`.

        The same route the arrows take, so it runs :attr:`command` as
        a user's press would.
        """
        self._tk.event_generate("<<Decrement>>")
