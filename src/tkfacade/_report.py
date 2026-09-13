"""Route a callback's raise to the interpreter's error seam, or stderr.

The one reporting path every callback route shares: raising the
exception inside an ``after_idle`` job sends it down Tk's own swallow
path to the interpreter's ``report_callback_exception`` — the hook
:attr:`~tkfacade.window.Root.callback_error_handler` owns when a
tkfacade root owns the interpreter — so an application's error routing
is one hook however a callback failed. With no host to route through,
the report goes to stderr.
"""

import sys
import tkinter as tk
import traceback
from contextlib import suppress


def report(host: tk.Misc | None, exc: BaseException, context: str) -> None:
    """Report ``exc`` through ``host``'s interpreter, or to stderr.

    Args:
        host (tk.Misc | None): A widget on the interpreter whose error
            seam the report rides, or None for the stderr fallback.
        exc (BaseException): The exception to report, traceback
            attached.
        context (str): What raised, for the stderr fallback's one-line
            preamble; unused on the interpreter route, where the
            traceback speaks for itself.
    """
    if host is not None:

        def declare() -> None:
            raise exc

        with suppress(tk.TclError, RuntimeError):
            host.after_idle(declare)
            return
    print(f"Exception in {context}:", file=sys.stderr)
    traceback.print_exception(exc)
