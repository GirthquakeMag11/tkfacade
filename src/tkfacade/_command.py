"""The dual-kind command dispatch every command-bearing widget shares."""

import concurrent.futures
import tkinter as tk
from collections.abc import Coroutine
from inspect import iscoroutinefunction
from typing import Any, cast

from ._core import launch, resolve_core
from ._report import report
from ._types import Command


def dispatch_command(
    widget: tk.Misc,
    held: Command,
    tasks: set[concurrent.futures.Future[Any]],
    context: str,
) -> None:
    """Run a widget's held command, handling either command kind.

    A plain callable runs here, on the mainloop, its raise routed to
    the interpreter's hook by Tk itself; a coroutine function is
    scheduled on the root's core, fire-and-forget, its raise retrieved
    and routed to the same hook.

    Args:
        widget (tk.Misc): The widget the command belongs to; the core
            is resolved through its interpreter and reports route by
            it.
        held (Command): The command, of either kind.
            Callers keep their own None-means-nothing check.
        tasks (set[concurrent.futures.Future[Any]]): Where a scheduled
            run is tracked while in flight.
        context (str): What the command is, for the report.
    """
    if iscoroutinefunction(held):
        core = resolve_core(widget.tk)
        if core is None:
            report(widget, RuntimeError(f"no core to run {context}"), context)
            return
        # cast sanctioned by the guard above: a coroutine function's
        # call is a coroutine
        coro = cast(Coroutine[Any, Any, object], held())
        launch(core, coro, tasks, lambda exc: report(widget, exc, context))
        return
    held()
