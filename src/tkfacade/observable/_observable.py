"""The observable value: Python-held state, watched consistently, driving Tk.

The design and its evidence are ``experiments/observable_settle/``. The
value lives in Python — an observable exists before any root and
outlives interpreter churn — and a ``tk.Variable`` attaches per
interpreter as the transport widgets ride, acquired and released
through :meth:`Observable.transport_for` and
:meth:`Observable.release_transport` so that no dead interpreter is
ever pinned (`hazards/tkinter.md`, *Variables*).
"""

import concurrent.futures
import inspect
import threading
import tkinter as tk
from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from contextlib import suppress
from math import isnan
from typing import Any, Final, cast

from .._core import launch, resolve_core
from .._report import report
from .._subscription import Subscription

_SETTLE_CAP: Final = 8
"""Dispatch rounds allowed before a fight is declared divergent."""


class DivergenceError(RuntimeError):
    """Watchers kept minting fresh values past the settle cap.

    Reported through the callback error hook rather than raised to the
    setter — a notification cannot veto or signal failure to the
    operation that triggered it — with the observable left holding the
    last value the cap caught.
    """


class _Watch[T]:
    """One registration: the watcher, what it last saw, whether it counts."""

    __slots__ = ("active", "is_async", "seen", "tasks", "watcher")

    def __init__(self, watcher: Callable[[T], object], seen: T) -> None:
        self.watcher: Callable[[T], object] = watcher
        self.seen: T = seen
        self.active: bool = True
        self.is_async: bool = inspect.iscoroutinefunction(watcher)
        self.tasks: set[concurrent.futures.Future[Any]] = set()


class Observable[T](ABC):
    """A watchable value with the settled-truth guarantee.

    The value is plain Python state, readable and assignable through
    :attr:`value` with no root required. Watchers registered through
    :meth:`watch` are called with the value current at their turn and
    re-called until every one of them has seen the value a write
    settled at — a watcher writing back is visible to every sibling
    before the dust settles, a write equal to the value held notifies
    nobody, and a fight minting fresh values is cut off at the settle
    cap and reported as :class:`DivergenceError` through the callback
    error hook, the last value kept. A raising watcher is reported the
    same way and its siblings still run.

    The settle machinery runs on the interpreter's thread. A write from
    any other thread, on an observable with a transport attached, is
    marshalled onto the mainloop: the whole settle — compare, push,
    dispatch — crosses to the interpreter's thread, so watchers and the
    transport see one single-threaded truth, and the writer observing
    its own write is subject to that crossing. The marshal needs the
    mainloop running; while it is not, the write raises rather than
    half-landing. An observable with no transport has no mainloop to
    speak of, and its dispatch stays on whatever thread writes it —
    the caller's affinity to honor.

    The four concrete kinds cover Tk's native value types; the seam
    arbitrary types enter through later is a converting subclass of
    this base.
    """

    __slots__ = (
        "_dispatching",
        "_host",
        "_main_ident",
        "_riders",
        "_trace",
        "_value",
        "_var",
        "_watches",
    )

    def __init__(self, value: T, /) -> None:
        """Hold ``value``; no interpreter is touched or required.

        Args:
            value (T): The initial value.
        """
        self._value: T = value
        self._watches: list[_Watch[T]] = []
        self._dispatching: bool = False
        self._var: tk.Variable | None = None
        self._host: tk.Misc | None = None
        self._trace: str = ""
        self._riders: int = 0
        self._main_ident: int = 0

    def __repr__(self) -> str:
        """Return the kind, the value, and how many watchers stand."""
        standing = sum(1 for entry in self._watches if entry.active)
        return f"<{type(self).__name__} value={self._value!r} watchers={standing}>"

    @abstractmethod
    def _new_var(self, master: tk.Misc) -> tk.Variable:
        """Create this kind's Tk variable on ``master``, seeded with the value."""

    @abstractmethod
    def _read(self, var: tk.Variable) -> T:
        """Read the transport's current value as this kind's type.

        Raises:
            tkinter.TclError: If the variable holds what the type
                cannot read — the widget route can put arbitrary text
                in any variable (`hazards/tkinter.md`, *Variables*).
        """

    def _same(self, a: T, b: T) -> bool:
        """Return whether two values count as one, for the equal-write drop."""
        return bool(a == b)

    def _dispatch(self) -> None:
        """Notify watchers until the value settles; report a divergence.

        Re-entrant calls return at once: a write landing mid-dispatch —
        a watcher's write-back, or the transport echoing one — is
        picked up by the running loop's next round, which is what makes
        every watcher end on the settled value.
        """
        if self._dispatching:
            return
        self._dispatching = True
        try:
            for _ in range(_SETTLE_CAP):
                settled = True
                for entry in list(self._watches):
                    if not entry.active or self._same(entry.seen, self._value):
                        continue
                    entry.seen = self._value
                    settled = False
                    if entry.is_async:
                        self._launch_watcher(entry)
                        continue
                    try:
                        entry.watcher(self._value)
                    except Exception as exc:
                        self._report(exc)
                if settled:
                    return
            self._report(
                DivergenceError(
                    f"{self!r} did not settle within {_SETTLE_CAP} rounds; keeping {self._value!r}"
                )
            )
        finally:
            self._dispatching = False

    def _launch_watcher(self, entry: _Watch[T]) -> None:
        """Schedule an async watcher on the host root's core, fire-and-forget.

        The raise, if one lands, is reported through the observable's
        own seam; cancellation stays silent lifecycle. With no core to
        resolve — no transport attached, or the root tearing down —
        the miss is reported rather than swallowed.
        """
        host = self._host
        core = None if host is None else resolve_core(host.tk)
        if core is None:
            self._report(
                RuntimeError(
                    f"no core to run the async watcher of {self!r}: an async "
                    "watcher needs the observable attached to a root's "
                    "interpreter by a transport"
                )
            )
            return
        # cast sanctioned by the registration invariant: is_async
        # pinned iscoroutinefunction at watch time
        coro = cast(Coroutine[Any, Any, object], entry.watcher(self._value))
        launch(core, coro, entry.tasks, self._report)

    def _push(self) -> None:
        """Land the value in the transport, quietly surviving a dead one.

        TclError alone: the thread wall's RuntimeError no longer
        belongs here — an off-thread write marshals before it ever
        reaches this, and suppressing the wall was the half-landing
        the marshal replaced.
        """
        if self._var is not None:
            with suppress(tk.TclError):
                self._var.set(self._value)

    def _on_transport_write(self, *_: str) -> None:
        """Adopt a widget-side write; drop echoes and unreadable text."""
        var = self._var
        if var is None:
            return
        try:
            incoming = self._read(var)
        except tk.TclError, ValueError:
            return
        if self._same(incoming, self._value):
            return
        self._value = incoming
        self._dispatch()

    def _report(self, exc: BaseException) -> None:
        """Route ``exc`` per :func:`tkfacade._report.report`.

        An attached observable reports through its transport's
        interpreter — the callback error hook, when a tkfacade root owns
        it — and an unattached one to stderr, having no interpreter to
        route through.
        """
        report(self._host, exc, f"a watcher of {self!r}")

    def _transport_dead(self) -> bool:
        """Return whether the attached transport's interpreter is gone."""
        try:
            assert self._var is not None
            self._var.trace_info()
        except tk.TclError, RuntimeError:
            return True
        return False

    def _drop_transport(self) -> None:
        """Forget the transport, removing the trace where one still can be."""
        if self._var is not None:
            with suppress(tk.TclError, RuntimeError):
                self._var.trace_remove("write", self._trace)
        self._var = None
        self._host = None
        self._trace = ""
        self._riders = 0
        self._main_ident = 0

    @property
    def value(self) -> T:
        """The value held; assigning notifies watchers and the transport.

        An assignment equal to the value held does nothing at all — no
        watcher runs and no transport write lands — which is also what
        keeps the transport's echo of a push silent.
        """
        return self._value

    @value.setter
    def value(self, candidate: T) -> None:
        host = self._host
        if host is not None and threading.get_ident() != self._main_ident:
            host.after(0, lambda: setattr(self, "value", candidate))
            return
        if self._same(candidate, self._value):
            return
        self._value = candidate
        self._push()
        self._dispatch()

    def watch(self, watcher: Callable[[T], object], /) -> Subscription:
        """Register ``watcher`` and call it immediately with the value held.

        The immediate call extends the settled-truth guarantee to the
        subscribe moment: a watcher is never stale, its birth included.
        A raise inside it is reported, not propagated, like any watcher
        raise.

        A coroutine function watches asynchronously: each settled change
        schedules a run on the root's core with that value — the
        immediate first call included — fire-and-forget, with raises
        reported through the same seam and cancellation silent. Runs can
        overlap when the value moves again mid-flight, and the route
        needs the observable attached to a root's interpreter by a
        transport. Returns are ignored in both forms.

        Args:
            watcher (Callable[[T], object]): Called — or scheduled on
                the core, for a coroutine function — with the new
                value on every settled change, starting now.

        Returns:
            The registration's :class:`~tkfacade.Subscription`;
            cancelling it also cancels the watcher's coroutine runs
            still in flight.
        """
        entry = _Watch(watcher, self._value)
        self._watches.append(entry)

        def cancel() -> None:
            entry.active = False
            for task in tuple(entry.tasks):
                task.cancel()
            with suppress(ValueError):
                self._watches.remove(entry)

        subscription = Subscription(cancel)
        if entry.is_async:
            self._launch_watcher(entry)
            return subscription
        try:
            entry.watcher(self._value)
        except Exception as exc:
            self._report(exc)
        return subscription

    def transport_for(self, master: tk.Misc, /) -> tk.Variable:
        """Return the Tk variable driving widgets on ``master``'s interpreter.

        Plumbing for widget wrappers, which pass their own underlying
        widget and hand the variable to Tk's ``-variable`` options; a
        caller watching or driving the value never needs it. One
        transport serves every widget on the interpreter, acquisitions
        counted: each ``transport_for`` is owed one
        :meth:`release_transport`, and the transport is dropped at
        zero so a `tk.Variable` never pins a dead interpreter
        (`hazards/tkinter.md`, *Variables*). A transport bound to a dead
        interpreter is replaced on the next acquisition — interpreter
        churn is survived — but only one live interpreter is served at
        a time.

        Args:
            master (tk.Misc): A widget on the target interpreter; also
                the host divergence and watcher-raise reports route
                through.

        Returns:
            The transport variable, seeded with the value held.

        Raises:
            RuntimeError: If the transport is bound to another live
                interpreter.
        """
        if self._var is not None:
            if self._host is not None and self._host.tk is master.tk:
                self._riders += 1
                return self._var
            if not self._transport_dead():
                raise RuntimeError(
                    "this observable's transport is bound to another live "
                    "interpreter; release it there first"
                )
            self._drop_transport()
        var = self._new_var(master)
        self._var = var
        self._host = master
        # the attaching thread is the interpreter's own; the off-thread write marshals on it
        self._main_ident = threading.get_ident()
        self._trace = var.trace_add("write", self._on_transport_write)
        self._riders = 1
        return var

    def release_transport(self) -> None:
        """Give back one :meth:`transport_for` acquisition.

        The transport is dropped when the last acquisition is given
        back; extra releases are harmless. Widget wrappers release from
        their own teardown, so a dying widget never leaves the count
        stuck.
        """
        self._riders -= 1
        if self._riders <= 0 and self._var is not None:
            self._drop_transport()


class ObservableStr(Observable[str]):
    """An observable ``str``, transported as a ``tk.StringVar``."""

    __slots__ = ()

    def _new_var(self, master: tk.Misc) -> tk.Variable:
        return tk.StringVar(master, self._value)

    def _read(self, var: tk.Variable) -> str:
        # cast: _read receives exactly the variable _new_var built
        return cast(tk.StringVar, var).get()


class ObservableBool(Observable[bool]):
    """An observable ``bool``, transported as a ``tk.BooleanVar``."""

    __slots__ = ()

    def _new_var(self, master: tk.Misc) -> tk.Variable:
        return tk.BooleanVar(master, self._value)

    def _read(self, var: tk.Variable) -> bool:
        return cast(tk.BooleanVar, var).get()


class ObservableInt(Observable[int]):
    """An observable ``int``, transported as a ``tk.IntVar``."""

    __slots__ = ()

    def _new_var(self, master: tk.Misc) -> tk.Variable:
        return tk.IntVar(master, self._value)

    def _read(self, var: tk.Variable) -> int:
        return cast(tk.IntVar, var).get()


class ObservableFloat(Observable[float]):
    """An observable ``float``, transported as a ``tk.DoubleVar``.

    NaN counts as itself: assigning NaN over NaN is an equal write, so
    the one value Python holds unequal to itself cannot echo forever
    between the transport and the dispatch.
    """

    __slots__ = ()

    def _new_var(self, master: tk.Misc) -> tk.Variable:
        return tk.DoubleVar(master, self._value)

    def _read(self, var: tk.Variable) -> float:
        return cast(tk.DoubleVar, var).get()

    def _same(self, a: float, b: float) -> bool:
        return a == b or (isnan(a) and isnan(b))
