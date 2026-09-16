"""The process-wide Tk root: lazy creation, mainloop plumbing, teardown cascade."""

import gc
import sys
import threading
import tkinter as tk
import traceback
from collections.abc import Callable
from tkinter import ttk
from typing import TYPE_CHECKING, Any, Final

from .._core import Core, attach_core, detach_core
from ..input import InputObserver
from ..widget import BaseWidget, Surface

if TYPE_CHECKING:
    from types import TracebackType

    from ._window import Window


class Root(BaseWidget):
    """Owner of the process's hidden ``tk.Tk`` interpreter.

    Constructing one creates a real, withdrawn ``tk.Tk``; prefer
    :func:`get_root` so the whole process shares one interpreter.
    """

    __slots__ = (
        "_callback_error_handler",
        "_children",
        "_core",
        "_default_callback_report",
        "_destroyed",
        "_inputs",
        "_running",
        "_style",
    )

    def __init__(self) -> None:
        """Create and withdraw the underlying ``tk.Tk`` interpreter.

        Raises:
            RuntimeError: If called off the main thread. A Tcl
                interpreter binds to the thread that creates it, and
                everything here — the mainloop's own main-thread
                requirement, worker marshaling, retired-interpreter
                flushing — assumes that thread is the main one. A
                worker's first-touch construction would poison the
                shared root for the whole process: every main-thread
                call would raise, and the self-heal path could not
                even ask ``destroyed`` without raising too. Checked
                unconditionally, so the contract holds under
                ``python -O``.
        """
        current = threading.current_thread()
        if current is not threading.main_thread():
            raise RuntimeError(
                f"a Tk interpreter binds to the thread that creates it; "
                f"create the root on the main thread first, not on {current.name!r}"
            )
        _flush_retired()
        self._tk: tk.Tk = tk.Tk()
        self._tk.option_add("*tearOff", False)
        self._tk.event_delete("<<LineStart>>", "<Control-Key-a>", "<Control-Lock-Key-A>")
        self._tk.event_add("<<SelectAll>>", "<Control-Key-a>", "<Control-Lock-Key-A>")
        self._tk.withdraw()
        self._running: threading.Event = threading.Event()
        self._destroyed: bool = False
        self._children: list[Window] = []
        self._style: ttk.Style = ttk.Style(self._tk)
        self._style.theme_use("clam")
        self._callback_error_handler: Callable[[BaseException], None] | None = None
        self._default_callback_report = self._tk.report_callback_exception
        self._tk.report_callback_exception = self._route_callback_error
        self._core: Core | None = None
        self._inputs: InputObserver | None = None
        attach_core(self._tk.tk, self._ensure_core)
        super().__init__()

    def _ensure_core(self) -> Core:
        """Return the root's async core, building and starting it on first need.

        The registry hands this out per interpreter
        (`tkfacade._core`), so the dispatch reaches the core from any
        widget without holding the root.
        """
        if self._core is None:
            core = Core()
            core.start()
            self._core = core
        return self._core

    def _route_callback_error(
        self,
        exc: type[BaseException],
        val: BaseException,
        tb: TracebackType | None,
    ) -> None:
        """Deliver a callback's raise to the application's handler, or print it.

        Installed as the interpreter's ``report_callback_exception``, so
        every raise Tk swallows — from an event handler, a command, a
        variable trace, an ``after`` job — lands here. With no handler
        set the report is Tk's own print-and-continue. A raise inside
        the handler itself cannot be routed through the handler: both
        tracebacks go to stderr, and the loop keeps running either way.
        """
        handler = self._callback_error_handler
        if handler is None:
            self._default_callback_report(exc, val, tb)
            return
        try:
            handler(val)
        except Exception:
            self._default_callback_report(exc, val, tb)
            print("Exception in the callback error handler itself:", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

    @property
    def inputs(self) -> InputObserver:
        """The root's keyboard and mouse observer, built on first use.

        The record of what is pressed right now — every key and
        button, queryable from any widget through
        :func:`~tkfacade.get_root` — and the door to
        :meth:`~tkfacade.input.InputObserver.chord`. See
        :class:`~tkfacade.input.InputObserver`.
        """
        if self._inputs is None:
            self._inputs = InputObserver(self)
        return self._inputs

    @property
    def windows(self) -> tuple[Window, ...]:
        """The :class:`Window` wrappers registered on this root, oldest first.

        A snapshot, so mutating it registers nothing. Named for what it
        holds: ``children`` is the Tk child dict tkinter reads off a
        master, and these are wrappers rather than Tk widgets.
        """
        return tuple(self._children)

    @property
    def destroyed(self) -> bool:
        """Whether the underlying interpreter is gone.

        Probes the interpreter rather than trusting a flag alone: the
        ``tk.Tk`` can die without :meth:`destroy` being called, since
        :class:`BaseWindow` tears down the root it belongs to when that
        root's last toplevel closes.
        """
        if self._destroyed:
            return True
        try:
            return not bool(self._tk.winfo_exists())
        except tk.TclError:
            return True

    @property
    def callback_error_handler(self) -> Callable[[BaseException], None] | None:
        """The application's handler for raises inside callbacks, or None.

        The application's error hook for raises inside callbacks: a
        raise inside a notification callback — an event handler, a
        command, a variable trace, an ``after`` job — is swallowed by
        Tk and routed here instead of propagating, with the operation
        that triggered the callback completing regardless. The handler
        receives the exception instance, its traceback attached.
        Defaults to None, which keeps Tk's own report — the traceback
        printed to stderr and the loop running — and assigning None
        restores that default.
        """
        return self._callback_error_handler

    @callback_error_handler.setter
    def callback_error_handler(self, handler: Callable[[BaseException], None] | None) -> None:
        self._callback_error_handler = handler

    def add_child(self, child: Window, /) -> None:
        """Register ``child``, holding a strong reference to the wrapper.

        Idempotent. The reference is what keeps the wrapper — and what
        it holds, such as its icon image — alive even after the caller
        drops theirs; :meth:`destroy` releases the lot.
        """
        if child not in self._children:
            self._children.append(child)

    def rem_child(self, child: Window, /) -> None:
        """Drop every registered reference to ``child``; missing is fine."""
        while child in self._children:
            self._children.remove(child)

    def run_mainloop(self) -> None:
        """Enter the Tk mainloop; blocks until the interpreter is destroyed.

        The running flag is raised for exactly as long as the loop is
        in it, so a root whose loop has exited — destroyed or merely
        quit — can be run again.

        Raises:
            RuntimeError: If called off the main thread, which Tk
                requires. Checked unconditionally, so the contract
                holds under ``python -O`` too.
        """
        current = threading.current_thread()
        if current is not threading.main_thread():
            raise RuntimeError(
                f"Root mainloop can only run from the main thread, not {current.name!r}"
            )
        self._running.set()
        try:
            self._tk.mainloop()
        finally:
            self._running.clear()

    def mainloop_running(self) -> bool:
        """Return whether a :meth:`run_mainloop` call is in its loop right now.

        False again once the loop exits, however it ended, so it never
        answers for a finished loop.
        """
        return self._running.is_set()

    def destroy(self) -> None:
        """Destroy the interpreter and every window under it.

        Live surfaces go first, while their native windows still
        exist: a backend drawing into one — mpv — must be terminated
        before Tk frees it, or the process dies instead of raising
        (see :meth:`Surface._teardown_all`). The wrapper registry is
        emptied too: a destroyed root holds nothing, so the
        :class:`Window` wrappers it was keeping alive become
        collectable. The dead interpreter itself is retired into the
        main-thread pin (see :data:`_retired_apps`) rather than left
        to die on whatever thread collects its cycles.
        """
        if not self._destroyed:
            self._destroyed = True
            Surface._teardown_all(self._tk.tk)
            detach_core(self._tk.tk)
            if self._inputs is not None:
                self._inputs._teardown()
                self._inputs = None
            if self._core is not None:
                self._core.stop()
            _retired_apps.append(self._tk.tk)
            self._tk.destroy()
        self._children.clear()


GLOBAL_LOCK: Final[threading.RLock] = threading.RLock()
"""Serializes root creation and last-window teardown.

Never held across a blocking call: the mainloop runs outside it, so
:func:`get_root` and the running flag stay reachable from other
threads for the loop's whole life.
"""

_root: Root | None = None
"""The shared :class:`Root`; None until :func:`get_root` first runs."""

_retired_apps: Final[list[Any]] = []
"""Destroyed roots' interpreter objects, pinned until a main-thread flush.

``_tkinter`` deallocates an interpreter with ``Tcl_AsyncDelete``, which
panics — aborting the whole process — when it runs on any thread but
the interpreter's own. A destroyed root's ``tk.Tk`` dies only by cycle
collection (every widget tree is a master↔children reference cycle),
and cycle collection runs on whichever thread happens to trigger it: an
mpv event thread or a ``submit`` worker often enough. The pin keeps a
foreign-thread collection from ever dropping the interpreter's last
reference; :func:`_flush_retired` releases it where that is safe.
"""


def _flush_retired() -> None:
    """Release retired interpreters, only ever from the main thread.

    The collect first frees any widget cycles still holding the
    retired interpreters — the pin keeps the interpreter objects
    themselves alive through it — so dropping the pins afterwards is
    the last reference going, and the deallocation runs right here on
    the main thread by plain refcounting. Off the main thread this is
    a no-op, which is the entire point.
    """
    if not _retired_apps or threading.current_thread() is not threading.main_thread():
        return
    gc.collect()
    _retired_apps.clear()


def get_root() -> Root:
    """Return the process-wide :class:`Root`, creating it on first use.

    No ``tk.Tk`` exists at import time, and a destroyed root is
    transparently replaced on the next call. Any thread may *read*
    the live root this way; only creating one is a main-thread act.

    Returns:
        The live shared root; never a destroyed one.

    Raises:
        RuntimeError: If no live root exists and this call is off the
            main thread — construction would bind the interpreter to
            the worker and poison it for the process (see
            :meth:`Root.__init__`). Create the root on the main
            thread before workers first touch it.
    """
    global _root
    with GLOBAL_LOCK:
        _flush_retired()
        if _root is None or _root.destroyed:
            _root = Root()
        return _root


class BaseWindow(tk.Toplevel):
    """A ``tk.Toplevel`` that tears down its own root when the last window closes."""

    def __init__(
        self,
        master: tk.Misc | None = None,
        cnf: dict[str, Any] | None = None,
        *,
        owner: Root | None = None,
        **kw: Any,
    ) -> None:
        """Create the toplevel and record which :class:`Root` owns it.

        Args:
            master (tk.Misc | None): The widget to create the toplevel
                under, as for ``tk.Toplevel``. Defaults to None.
            cnf (dict[str, Any] | None): Toplevel options as a dict,
                merged with keyword options. Defaults to None.
            owner (Root | None): The root whose teardown cascade this
                window takes part in. Defaults to None, meaning the
                module-global shared root.
            **kw (Any): Further toplevel options.
        """
        self._owner: Root | None = owner
        super().__init__(master, cnf if cnf is not None else {}, **kw)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def destroy(self) -> None:
        """Destroy this toplevel, then tear down its own root if bare.

        Surfaces under this window go first, while it still exists —
        the same terminate-before-free ordering :meth:`Root.destroy`
        keeps interpreter-wide, and needed here because a titlebar
        close or a standalone window destroy frees this window's
        natives without any root teardown running (see
        :meth:`Surface._teardown_window`). The root consulted is the
        :class:`Root` this window was built on — the shared one only
        when no owner was given. When that root's last live toplevel
        is gone, its ``tk.Tk`` — and with it the mainloop — is
        destroyed too, and no other root is touched. A window-manager
        close lands here as well, via the ``WM_DELETE_WINDOW`` handler
        registered at construction, and any :class:`Window` wrapper
        holding this toplevel leaves the root's registry so a dead
        window is never pinned by it.
        """
        Surface._teardown_window(self.tk, str(self))
        super().destroy()
        with GLOBAL_LOCK:
            root = self._owner if self._owner is not None else _root
            if root is None or root.destroyed:
                return
            for child in root.windows:
                if child._tk is self:
                    root.rem_child(child)
            if not any(
                isinstance(w, tk.Toplevel) and w.winfo_exists() for w in root._tk.winfo_children()
            ):
                root.destroy()
