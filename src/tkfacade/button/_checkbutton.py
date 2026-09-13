"""The Checkbutton wrapper: one boolean in widget form, ticked or not."""

import concurrent.futures
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from .._command import dispatch_command
from .._types import Command
from ..events import ACTIVATED, Destroyed, Event
from ..look import Look
from ..observable import ObservableBool
from ..widget import BaseWidget, Widget


class Checkbutton(Widget):
    """A themed toggle holding one boolean, ticked or not.

    The tick is an :class:`~tkfacade.ObservableBool` — the widget's
    own unless one is passed in, shared with whatever else watches or
    drives the value. The menu's checkbox rows speak the same
    observable, so one value can be a widget and a menu row at once.
    The tick is two-state by construction: the transport always holds
    True or False, so ttk's third, indeterminate look is unreachable.

    The optional command runs on user activation only — a click, the
    keyboard, or :meth:`invoke` — never on writes through the
    observable. That is the distinction a watcher cannot make, and
    the whole of why the command exists beside one. It takes a plain
    callable or a coroutine function, the latter scheduled
    fire-and-forget on the root's async core.

    Appearance comes from the ``TCheckbutton`` style rather than from
    per-widget options: no color, font, or relief rides this
    constructor, and a checkbutton restyled through :class:`ttk.Style`
    follows.
    """

    if TYPE_CHECKING:
        _tk: ttk.Checkbutton
        _observable: ObservableBool

    __slots__ = ("_command", "_command_tasks", "_observable")

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        /,
        text: str = "",
        *,
        checked: bool | ObservableBool = False,
        command: Command | None = None,
        enabled: bool = True,
        look: Look | None = None,
    ) -> None:
        """Create the checkbutton, and the observable behind it if none is given.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the
                checkbutton is created inside.
            text (str): The label beside the tick. Defaults to ``""``.
            checked (bool | ObservableBool): The starting state, or the
                observable already holding it, shared with whatever
                else watches or drives that value. Defaults to False,
                an unticked checkbutton with an observable of its own.
            command (Command | None): Run on each user
                activation — a plain callable on the mainloop, a
                coroutine function on the root's async core. Defaults
                to None.
            enabled (bool): Whether the checkbutton starts activatable.
                Defaults to True.
            look (Look | None): The look to wear from the start; see
                :attr:`~tkfacade.widget.Widget.look`. Defaults to None,
                the library's base style.
        """
        master = self._as_master(parent)
        self._command: Command | None = command
        self._command_tasks: set[concurrent.futures.Future[Any]] = set()
        self._observable = (
            checked if isinstance(checked, ObservableBool) else ObservableBool(checked)
        )
        self._tk = ttk.Checkbutton(
            master,
            text=text,
            variable=self._observable.transport_for(master),
            command=self._run_command,
            state="normal" if enabled else "disabled",
        )
        self._tk._observables = (self._observable,)  # type: ignore[attr-defined]
        super().__init__()
        self.bind(Destroyed(), self._give_back_transport)
        if look is not None:
            self.look = look

    def _run_command(self) -> None:
        """Run the held command, then emit the activation; None runs nothing.

        Both fire exactly when the command channel does — a user's
        toggle — so :data:`~tkfacade.ACTIVATED` keeps the user-only
        meaning while any number of subscribers may hear it.
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
        self._observable.release_transport()

    @property
    def text(self) -> str:
        """The label beside the tick."""
        return str(self._tk.cget("text"))

    @text.setter
    def text(self, value: str) -> None:
        self._tk.configure(text=value)

    @property
    def checked(self) -> bool:
        """Whether the tick is on.

        Assigning writes through :attr:`checked_observable`, so it
        works while disabled and every watcher hears it; the command
        does not run, being the user's channel.
        """
        return self._observable.value

    @checked.setter
    def checked(self, value: bool) -> None:
        self._observable.value = value

    @property
    def checked_observable(self) -> ObservableBool:
        """The observable holding the tick, for watching or sharing.

        The checkbutton's own unless one was passed to the
        constructor. Every change to the tick passes through it,
        clicked or assigned, so a watcher on it sees both.
        """
        return self._observable

    @property
    def command(self) -> Command | None:
        """What user activation runs beside the toggle; None is nothing extra.

        Assigning swaps what future activations run. Coroutine runs
        already in flight from the old command are left to finish —
        death narrows the future, never the present.
        """
        return self._command

    @command.setter
    def command(self, value: Command | None) -> None:
        self._command = value

    @property
    def enabled(self) -> bool:
        """Whether the checkbutton can be activated; read live from Tk."""
        return not self._tk.instate(["disabled"])

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._tk.state(["!disabled" if value else "disabled"])

    def invoke(self) -> None:
        """Do what activating does: toggle the tick, then run the command.

        A disabled checkbutton does nothing; the state guard is ttk's
        own.
        """
        self._tk.invoke()
