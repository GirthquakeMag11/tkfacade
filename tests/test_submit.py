"""``BaseWidget.submit``: the future's fate under every ordering.

The contract is that the returned future always resolves somehow —
result, exception, or cancellation — whatever happens to the widget or
the future in between. Every test drives a real mainloop pass via the
``pump`` fixture and carries the ``gui`` marker.
"""

import tkinter as tk

import pytest

import tkfacade
from conftest import Pump
from tkfacade.widget import Widget

pytestmark = pytest.mark.gui


class _Cell(Widget):
    """A minimal wrapper over a frame, for submitting against."""

    def __init__(self, parent: tkfacade.Window, /) -> None:
        """Create the frame inside ``parent``."""
        self._tk = tk.Frame(self._as_master(parent))


def test_submit_resolves_on_the_next_pass(window: tkfacade.Window, pump: Pump) -> None:
    """A submitted job runs once the loop turns, and the future carries its result.

    The happy path, pinned so the two failure-ordering tests below cannot pass by breaking scheduling outright. not-done-before-the-pump is the other half of the docstring's "nothing executes until the mainloop processes the event"; result(timeout=0) proves resolution needs no further passes.
    """
    future = window.submit(lambda: 41 + 1)

    assert not future.done()
    pump(window)

    assert future.result(timeout=0) == 42


def test_a_pending_submit_cancels_when_its_widget_dies(window: tkfacade.Window, pump: Pump) -> None:
    """A job pending on a destroyed widget cancels its future instead of hanging.

    The scheduled pass dies with the widget — its Tcl command is deleted on destroy — so before the fix the future stayed PENDING forever and a worker blocked in result() hung on exactly the cross-thread hand-off submit exists for. Cancellation is the observable that unblocks every waiter. The job body records itself so the test also pins that death means the job never half-ran, and the pump afterwards gives a lingering timer its chance to misfire into the dead command.
    """
    cell = _Cell(window)
    ran: list[str] = []
    future = cell.submit(ran.append, "never")

    cell._tk.destroy()
    pump(window)

    assert future.cancelled()
    assert ran == []


def test_a_cancelled_submit_never_runs_and_never_raises_in_the_loop(
    window: tkfacade.Window, pump: Pump
) -> None:
    """``cancel()`` before the pass keeps the job from running, with a quiet loop.

    The job used to call set_result on a future the caller had cancelled, raising InvalidStateError into Tk's callback-exception handler — a stderr traceback in the GUI loop for a routine cancel. The handler is captured because that traceback is the defect: an implementation that skipped the job but still touched the future would pass the first two assertions and fail only the last.
    """
    raised: list[str] = []
    root = tkfacade.get_root()
    ran: list[str] = []
    future = window.submit(ran.append, "never")

    assert future.cancel() is True

    def record(exc: type[BaseException], val: BaseException, _tb: object) -> None:
        raised.append(f"{exc.__name__}: {val}")

    original = root._tk.report_callback_exception
    root._tk.report_callback_exception = record
    pump(window)
    root._tk.report_callback_exception = original

    assert future.cancelled()
    assert ran == []
    assert raised == []


def test_a_base_exception_still_resolves_the_future(window: tkfacade.Window, pump: Pump) -> None:
    """A ``KeyboardInterrupt`` in the job lands on the future and reaches Tk's handler.

    The job ran under `except Exception`, so an interrupt skipped both resolution paths and left the future RUNNING — unresolvable and, once running, uncancellable, deadlocking any waiter in result(). Both halves of the new contract are pinned: the future carries the interrupt (exception(timeout=0) proves resolution took no further passes) and the re-raise still delivers it to Tk's callback handler, because swallowing a KeyboardInterrupt inside a GUI loop would hide the one signal a user sends by hand.
    """
    raised: list[str] = []
    root = tkfacade.get_root()

    def interrupt() -> None:
        raise KeyboardInterrupt

    def record(exc: type[BaseException], val: BaseException, _tb: object) -> None:
        raised.append(exc.__name__)

    future = window.submit(interrupt)
    original = root._tk.report_callback_exception
    root._tk.report_callback_exception = record
    pump(window)
    root._tk.report_callback_exception = original

    assert isinstance(future.exception(timeout=0), KeyboardInterrupt)
    assert raised == ["KeyboardInterrupt"]


def test_submit_survives_destruction_between_bind_and_schedule(
    window: tkfacade.Window, pump: Pump
) -> None:
    """A widget dying between the watch bind and the timer leaves a quiet, cancelled future.

    submit's contract allows foreign-thread calls, and tkinter marshals the watch bind and the after() as two separate Tcl calls the mainloop may interleave a destruction between. In that gap on_destroy used to read the timer cell before it was bound and throw NameError into the callback stream after cancelling the future. The destroying bind makes the gap deterministic instead of racing 400 threads at it; the empty raised list is the fix, and the cancelled future pins that the quiet path still tells the caller the whole story.
    """
    cell = _Cell(window)
    raised: list[str] = []
    root = tkfacade.get_root()
    real_bind = cell._tk.bind

    def destroying_bind(*args: object, **kwargs: object) -> object:
        token = real_bind(*args, **kwargs)  # type: ignore[call-overload]
        cell._tk.destroy()
        return token

    cell._tk.bind = destroying_bind  # type: ignore[assignment, method-assign]

    def record(exc: type[BaseException], val: BaseException, _tb: object) -> None:
        raised.append(exc.__name__)

    original = root._tk.report_callback_exception
    root._tk.report_callback_exception = record
    future = cell.submit(lambda: "never")
    pump(window)
    root._tk.report_callback_exception = original

    assert future.cancelled()
    assert raised == []
