"""Shared fixtures for the tkfacade test suite.

Tk is process-global state: one interpreter, a module-level root
singleton, and class-level registries on
:class:`~tkfacade.widget.BaseWidget` and :class:`~tkfacade.widget.Surface`.
The fixtures here hand each test a fresh root and window and tear that
state all the way down afterwards, so no test inherits another's
interpreter.

Tests that touch Tk should depend on :func:`root` (directly or via
:func:`window`); through it they skip cleanly on machines with no
display. Mark display-dependent tests ``gui`` as well, so they can be
selected or excluded as a group.
"""

import gc
import os
import sys
import threading
import time
import tkinter as tk
import traceback
from collections.abc import Callable, Iterator
from contextlib import suppress
from pathlib import Path
from typing import Protocol

import pytest

import tkfacade
from tkfacade.widget import BaseWidget, Surface
from tkfacade.window import _root as _root_module
from tkfacade.window import get_root
from tkfacade.window._root import Root

# A uv-managed CPython is reached through a minor-version *junction*
# (``cpython-3.14-...`` -> ``cpython-3.14.3-...``), and file reads
# through that junction intermittently fail under this suite's rapid
# interpreter churn — Tcl's init scripts then die sourcing files that
# exist, killing a fresh ``tk.Tk()`` mid-suite. Pinning both variables
# through the *resolved* install directory keeps every init-script read
# off the junction. ``setdefault`` so a deliberate override outside
# still wins; skipped entirely where the layout does not exist.
_TCL_DIR = Path(sys.base_prefix).resolve() / "tcl"
if (_TCL_DIR / "tcl8.6").is_dir():
    os.environ.setdefault("TCL_LIBRARY", str(_TCL_DIR / "tcl8.6"))
if (_TCL_DIR / "tk8.6").is_dir():
    os.environ.setdefault("TK_LIBRARY", str(_TCL_DIR / "tk8.6"))


def _fresh_tk[T](factory: Callable[[], T]) -> T:
    """Build a Tk interpreter via ``factory``, riding out transient failures.

    Tcl initialization on this machine intermittently fails to read
    init scripts that exist — roughly one interpreter creation per full
    run, only under pytest's I/O load, sometimes outlasting an
    immediate retry; antivirus-shaped interference, never reproduced
    outside pytest. Two spaced retries absorb the transient; a genuine
    failure (no display, broken install) fails all three attempts and
    still surfaces.

    Args:
        factory (Callable[[], T]): Zero-argument interpreter builder.

    Returns:
        Whatever ``factory`` returns.
    """
    for pause in (0.1, 0.25):
        try:
            return factory()
        except tk.TclError:
            time.sleep(pause)
    return factory()


@pytest.fixture(scope="session")
def display() -> None:
    """Skip the dependent test when no display can serve a Tk window."""
    try:
        probe = _fresh_tk(tk.Tk)
    except tk.TclError:
        pytest.skip("no display available; run under xvfb-run")
    probe.destroy()


@pytest.fixture
def root(display: None) -> Iterator[Root]:
    """A fresh shared :class:`Root`, hard-torn-down after the test.

    The root comes with the callback-error seam guarded: a collecting
    :attr:`~tkfacade.window.Root.callback_error_handler` is installed,
    and a test that ends with anything collected fails. A raise inside
    a Tk callback is swallowed to the interpreter's seam rather than
    propagating, so without the guard it prints into captured stderr
    and the test passes over it. A test whose subject is error routing
    installs its own handler and is exempt by construction — the guard
    only judges the seam while it still owns it.

    Teardown reads the module global directly rather than calling
    :func:`get_root`, which *constructs* an interpreter when none is
    live. The class-level registries on :class:`Surface` and
    :class:`~tkfacade.widget.BaseWidget` clean themselves up as their
    widgets die; they are swept here only so a test that tore an
    interpreter down behind Tk's back cannot leak an entry into the
    next one.
    """
    built = _fresh_tk(get_root)
    seam: list[BaseException] = []
    collector = seam.append
    built.callback_error_handler = collector
    yield built
    # judge the seam before teardown mutates anything: the guard holds
    # only while the collector is still installed, and reports routed
    # through after_idle (tkfacade._report) land on the next idle pass,
    # so a live root is pumped once to settle them before reading
    guard_active = built.callback_error_handler is collector
    if guard_active and not built.destroyed:
        with suppress(tk.TclError, RuntimeError):
            built._tk.update()
    leaked = list(seam) if guard_active else []
    live = _root_module._root
    if live is not None and not live.destroyed:
        live.destroy()
    _root_module._root = None
    Surface._surfaces.clear()
    Surface._review_job.clear()
    Surface._review_bound_to.clear()
    BaseWidget._wrappers.clear()
    # Every tkinter widget tree is a master<->children reference cycle, so
    # each test's dead widgets linger until a cycle collection. The
    # interpreter object itself is safe on any thread now -- Root.destroy
    # retires it into the main-thread pin that _flush_retired releases --
    # but collecting here still frees each test's widget garbage before
    # the next test piles its own on top, keeping the suite's memory flat
    # and the pin's release prompt.
    gc.collect()
    if leaked:
        rendered = "\n".join("".join(traceback.format_exception(exc)).rstrip() for exc in leaked)
        pytest.fail(
            f"{len(leaked)} exception(s) landed on the callback-error seam "
            f"during the test:\n{rendered}"
        )


@pytest.fixture
def window(root: Root) -> tkfacade.Window:
    """A :class:`~tkfacade.Window` on the per-test root; the root fixture reaps it."""
    return tkfacade.Window(title="test", root=root)


type Pump = Callable[[tk.Misc | BaseWidget], None]
"""The :func:`pump` fixture's type, for tests that take it as a parameter."""


@pytest.fixture
def pump() -> Pump:
    """Run every pending Tk event now, timers included.

    ``update_idletasks`` never fires ``after(0, ...)`` jobs, and some
    behaviour (a :class:`~tkfacade.StackFrame`'s deferred first show, submit
    futures) only settles once those run. Never call the returned
    function from inside a Tk callback — it re-enters the event loop.
    """

    def _pump(target: tk.Misc | BaseWidget) -> None:
        widget = target if isinstance(target, tk.Misc) else target._tk
        widget.update()

    return _pump


class RunMainloop(Protocol):
    """The shape of the :func:`run_mainloop` fixture's callable."""

    def __call__(
        self, window: tkfacade.Window, done: threading.Event, timeout: float = 5.0
    ) -> None: ...


@pytest.fixture
def run_mainloop() -> RunMainloop:
    """Run the real mainloop until an event is set, polled from inside it.

    The async-route tests need the main thread genuinely inside Tk's
    loop — the thread wall (`hazards/tkinter.md`, *Threads*) refuses off-thread
    crossings whenever it is merely spinning ``update()`` between
    sleeps — so the completion flag is polled by an ``after`` chain
    rather than waited on, and a test that hangs quits at the timeout
    to fail on its assertions instead of freezing the suite.
    """

    def _run(window: tkfacade.Window, done: threading.Event, timeout: float = 5.0) -> None:
        deadline = window._tk.after(int(timeout * 1000), window._tk.quit)

        def poll() -> None:
            if done.is_set():
                window._tk.after_cancel(deadline)
                window._tk.quit()
            else:
                window._tk.after(20, poll)

        window._tk.after(0, poll)
        window._tk.mainloop()

    return _run
