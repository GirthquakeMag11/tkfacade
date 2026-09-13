"""The Button wrapper: the themed push button, a command in widget form."""

import concurrent.futures
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from .._command import dispatch_command
from .._types import Command
from ..events import ACTIVATED
from ..look import Look
from ..widget import BaseWidget, Widget


class Button(Widget):
    """A themed push button that runs its command when activated.

    Activation is a click, the keyboard while focused, or
    :meth:`invoke`, and all of them run the same command. The command
    may be a plain callable, run on the mainloop like any Tk command,
    or a coroutine function, scheduled fire-and-forget on the root's
    async core — functions and coroutines are interchangeable here
    from birth.

    Appearance comes from the ``TButton`` style rather than from
    per-widget options: no color, font, or relief rides this
    constructor, and a button restyled through :class:`ttk.Style`
    follows.
    """

    if TYPE_CHECKING:
        _tk: ttk.Button

    __slots__ = ("_command", "_command_tasks")

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        /,
        text: str = "",
        *,
        command: Command | None = None,
        enabled: bool = True,
        width: int | None = None,
        look: Look | None = None,
    ) -> None:
        """Create the button, wired to run ``command`` on activation.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the
                button is created inside.
            text (str): The label on the button. Defaults to ``""``.
            command (Command | None): Run on each
                activation — a plain callable on the mainloop, a
                coroutine function on the root's async core. Defaults
                to None, a button that activates into nothing.
            enabled (bool): Whether the button starts activatable.
                Defaults to True.
            width (int | None): Width in characters; a negative value
                is a minimum. Defaults to None, sizing to the label.
            look (Look | None): The look to wear from the start; see
                :attr:`~tkfacade.widget.Widget.look`. Defaults to None,
                the library's base style.
        """
        self._command: Command | None = command
        self._command_tasks: set[concurrent.futures.Future[Any]] = set()
        self._tk = ttk.Button(
            self._as_master(parent),
            text=text,
            command=self._run_command,
            state="normal" if enabled else "disabled",
        )
        if width is not None:
            self._tk.configure(width=width)
        super().__init__()
        if look is not None:
            self.look = look

    def _run_command(self) -> None:
        """Run the held command, then emit the activation; None runs nothing.

        The command per :func:`.dispatch_command`, first; then
        :data:`~tkfacade.ACTIVATED` on this widget, command or no
        command — activation is subscribable either way.
        """
        held = self._command
        if held is not None:
            dispatch_command(self._tk, held, self._command_tasks, f"the command of {self!r}")
        self.emit(ACTIVATED)

    @property
    def text(self) -> str:
        """The label on the button."""
        return str(self._tk.cget("text"))

    @text.setter
    def text(self, value: str) -> None:
        self._tk.configure(text=value)

    @property
    def command(self) -> Command | None:
        """What activation runs; None is a button that activates into nothing.

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
        """Whether the button can be activated; read live from Tk."""
        return not self._tk.instate(["disabled"])

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._tk.state(["!disabled" if value else "disabled"])

    def invoke(self) -> None:
        """Do what activating the button does; a disabled button does nothing."""
        self._tk.invoke()
