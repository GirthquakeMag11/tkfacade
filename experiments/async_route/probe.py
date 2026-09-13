"""Witness the loop-beside-Tk facts the async callback route rests on.

Run with::

    xvfb-run -a uv run python -m experiments.async_route.probe

The async design gate must
decide where the asyncio loop lives, what an off-loop coroutine may
touch, how completion and exceptions route, and what widget death does
to an in-flight coroutine. Those decisions rest on facts this probe
pins: that an asyncio loop on its own thread serves coroutines
scheduled from Tk's thread without the mainloop pumping for it; that a
foreign thread's Tk call is *refused* — ``RuntimeError: main thread is
not in main loop`` — while the main thread is out of Tk's event loop,
where the marshalling ``../callback_doctrine/`` witnessed happens only
while it is in; that ``after()`` from the loop thread is a working
road back while the mainloop genuinely runs; what cancellation
delivers to a coroutine mid-await; that stopping the loop without
cancelling freezes pending tasks with their ``finally`` blocks unrun,
where cancel-then-stop runs them and joins promptly; where a
coroutine's raise surfaces; and what today's observable does with an
off-thread write — watchers on the writing thread when no transport is
attached, and a silent half-landing when one is: the value and its
watchers move, the widget does not.

The last two checks import the library — the facts they pin are about
tkfacade's own observable, not about Python — and every other check
stands on tkinter, asyncio, and threading alone.

Expectations are the behavior witnessed on Tk 8.6.14 (threaded Tcl,
X11), CPython 3.14. A FAIL is a finding: that build does not behave
the way the design's evidence says. Every check prints its verdict;
the exit status is the number that failed.
"""

import asyncio
import sys
import threading
import time
import tkinter as tk
from collections.abc import Callable

Report = tuple[bool, str]

_WAIT = 5.0
"""Seconds any single cross-thread wait is allowed before it is a FAIL."""


def loop_thread(
    handler: Callable[[asyncio.AbstractEventLoop, dict[str, object]], None] | None = None,
) -> tuple[asyncio.AbstractEventLoop, threading.Thread]:
    """Return a running asyncio loop on its own thread, ready to take work.

    Args:
        handler: An exception handler to install before the loop runs,
            for the check that must prove the handler stays silent.
    """
    loop = asyncio.new_event_loop()
    if handler is not None:
        loop.set_exception_handler(handler)
    ready = threading.Event()

    def run() -> None:
        asyncio.set_event_loop(loop)
        loop.call_soon(ready.set)
        loop.run_forever()

    thread = threading.Thread(target=run, name="probe-asyncio", daemon=True)
    thread.start()
    ready.wait(_WAIT)
    return loop, thread


def stop_loop(loop: asyncio.AbstractEventLoop, thread: threading.Thread) -> bool:
    """Stop the loop, join its thread, close the loop; True if all completed."""
    loop.call_soon_threadsafe(loop.stop)
    thread.join(_WAIT)
    if thread.is_alive():
        return False
    loop.close()
    return True


def check_a_loop_thread_runs_beside_the_mainloop() -> Report:
    """A coroutine scheduled from Tk's thread runs and returns with no pumping."""
    root = tk.Tk()
    root.withdraw()
    loop, thread = loop_thread()
    main = threading.get_ident()
    ran_on: list[int] = []

    async def job() -> int:
        ran_on.append(threading.get_ident())
        await asyncio.sleep(0.01)
        return 42

    future = asyncio.run_coroutine_threadsafe(job(), loop)
    scheduled_unfinished = not future.done()
    result = future.result(_WAIT)
    stopped = stop_loop(loop, thread)
    root.destroy()
    ok = result == 42 and scheduled_unfinished and bool(ran_on) and ran_on[0] != main and stopped
    return ok, (
        f"result {result!r}; scheduling returned before completion: {scheduled_unfinished}; "
        f"ran off the Tk thread: {bool(ran_on) and ran_on[0] != main} -- no update() anywhere"
    )


def check_an_off_thread_tk_call_is_refused_while_main_is_out() -> Report:
    """With the main thread out of Tk's loop, a worker's Tk call raises, not queues."""
    root = tk.Tk()
    root.withdraw()
    var = tk.StringVar(root)
    outcome: list[str] = []

    def worker() -> None:
        try:
            var.set("from the worker")
            outcome.append("set landed")
        except RuntimeError as exc:
            outcome.append(str(exc))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(_WAIT)  # the main thread is in this join, not in Tk's loop
    joined = not thread.is_alive()
    root.destroy()
    ok = joined and outcome == ["main thread is not in main loop"]
    return ok, (
        f"the worker's set() raised {outcome!r} -- refused outright, where "
        "../callback_doctrine/ witnessed the same call marshalling while the "
        "mainloop pumps"
    )


def check_after_from_the_loop_lands_on_the_mainloop() -> Report:
    """``after()`` from a coroutine reaches Tk's thread while mainloop truly runs."""
    root = tk.Tk()
    root.withdraw()
    loop, thread = loop_thread()
    main = threading.get_ident()
    inside_mainloop = threading.Event()
    landed: list[int] = []

    async def job() -> None:
        await asyncio.sleep(0)
        inside_mainloop.wait(_WAIT)

        def land() -> None:
            landed.append(threading.get_ident())
            root.quit()

        root.after(0, land)

    future = asyncio.run_coroutine_threadsafe(job(), loop)
    # the flag is set from inside the first dispatch, so the coroutine's
    # after() call can only ever meet a genuinely running mainloop
    root.after(0, inside_mainloop.set)
    root.after(int(_WAIT * 1000), root.quit)  # a hung check must fail, not hang
    root.mainloop()
    future.result(_WAIT)
    stopped = stop_loop(loop, thread)
    root.destroy()
    ok = bool(landed) and landed[0] == main and stopped
    return ok, (
        f"callback ran on the Tk thread: {bool(landed) and landed[0] == main} -- "
        "after() is a working road back, but only under a running mainloop"
    )


def check_cancel_reaches_a_mid_await_coroutine() -> Report:
    """Cancel lands at the await — later, on the loop; the future says so first."""
    loop, thread = loop_thread()
    started = threading.Event()
    unwound = threading.Event()
    story: list[str] = []

    async def job() -> None:
        started.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            story.append("cancelled at the await")
            raise
        finally:
            story.append("finally ran")
            unwound.set()

    future = asyncio.run_coroutine_threadsafe(job(), loop)
    started.wait(_WAIT)
    future.cancel()
    cancelled_before_unwind = future.cancelled() and not unwound.is_set()
    unwound.wait(_WAIT)
    stopped = stop_loop(loop, thread)
    ok = (
        story == ["cancelled at the await", "finally ran"]
        and cancelled_before_unwind
        and future.cancelled()
        and stopped
    )
    return ok, (
        f"the future reported cancelled before the coroutine unwound: "
        f"{cancelled_before_unwind}; then the story arrived on the loop: {story}"
    )


def check_a_stopped_loop_freezes_pending_tasks() -> Report:
    """Stopping without cancelling strands the coroutine, its finally unrun."""
    loop, thread = loop_thread()
    started = threading.Event()
    unwound = threading.Event()
    story: list[str] = []

    async def job() -> None:
        started.set()
        try:
            await asyncio.sleep(30)
        finally:
            story.append("finally ran")
            unwound.set()

    future = asyncio.run_coroutine_threadsafe(job(), loop)
    started.wait(_WAIT)
    loop.call_soon_threadsafe(loop.stop)
    thread.join(_WAIT)
    frozen = (not thread.is_alive()) and not story and not future.done()
    # resume the same loop to prove the task was frozen rather than gone,
    # and to give it an orderly end instead of a destroyed-pending warning
    revive = threading.Thread(target=loop.run_forever, daemon=True)
    revive.start()
    future.cancel()
    unwound.wait(_WAIT)
    resumed = story == ["finally ran"]
    stopped = stop_loop(loop, revive)
    ok = frozen and resumed and stopped
    return ok, (
        f"while stopped: finally unrun and future undone ({frozen}); "
        f"the revived loop delivered the cancel and the finally ran ({resumed})"
    )


def check_cancel_then_stop_runs_the_finally_and_joins() -> Report:
    """The orderly teardown: cancel, wait for the unwind, stop, join promptly."""
    loop, thread = loop_thread()
    started = threading.Event()
    unwound = threading.Event()
    story: list[str] = []

    async def job() -> None:
        started.set()
        try:
            await asyncio.sleep(30)
        finally:
            story.append("finally ran")
            unwound.set()

    future = asyncio.run_coroutine_threadsafe(job(), loop)
    started.wait(_WAIT)
    t0 = time.monotonic()
    future.cancel()
    unwound.wait(_WAIT)
    stopped = stop_loop(loop, thread)
    took = time.monotonic() - t0
    ok = story == ["finally ran"] and stopped and took < 2.0
    return ok, (
        f"cancel, unwind, stop, join took {took:.3f}s -- waiting for the unwind "
        "before the stop is the step the fire-and-forget cancel makes mandatory"
    )


def check_a_raise_parks_on_the_coroutines_future() -> Report:
    """A coroutine's raise lands on its future; the loop handler stays silent."""
    handled: list[str] = []
    loop, thread = loop_thread(lambda _loop, context: handled.append(str(context)))

    async def job() -> None:
        await asyncio.sleep(0)
        raise ValueError("boom")

    future = asyncio.run_coroutine_threadsafe(job(), loop)
    caught: BaseException | None = None
    try:
        future.result(_WAIT)
    except ValueError as exc:
        caught = exc
    stopped = stop_loop(loop, thread)
    ok = isinstance(caught, ValueError) and not handled and stopped
    return ok, (
        f"future.result raised {type(caught).__name__ if caught else None}; "
        f"loop exception handler calls: {len(handled)}"
    )


def check_todays_observable_dispatches_on_the_writing_thread() -> Report:
    """A write from the loop thread runs the watcher there — today's affinity."""
    from tkfacade.observable import ObservableStr

    loop, thread = loop_thread()
    main = threading.get_ident()
    delivered_on: list[int] = []
    observable = ObservableStr("before")
    observable.watch(lambda _value: delivered_on.append(threading.get_ident()))

    async def job() -> None:
        await asyncio.sleep(0)
        observable.value = "after"

    asyncio.run_coroutine_threadsafe(job(), loop).result(_WAIT)
    stopped = stop_loop(loop, thread)
    immediate_on_main = bool(delivered_on) and delivered_on[0] == main
    write_on_loop = len(delivered_on) == 2 and delivered_on[1] != main
    ok = immediate_on_main and write_on_loop and stopped
    return ok, (
        f"watch's immediate call on the registering thread: {immediate_on_main}; "
        f"the off-thread write delivered its watcher on the writing thread: {write_on_loop} "
        "-- the affinity is the caller's, unguarded"
    )


def check_a_transported_off_thread_write_half_lands() -> Report:
    """Today's transported off-thread write splits value from widget, silently."""
    from tkfacade.observable import ObservableStr

    root = tk.Tk()
    root.withdraw()
    loop, thread = loop_thread()
    main = threading.get_ident()
    delivered_on: list[int] = []
    observable = ObservableStr("before")
    transport = observable.transport_for(root)
    observable.watch(lambda _value: delivered_on.append(threading.get_ident()))

    async def job() -> None:
        await asyncio.sleep(0)
        observable.value = "after"

    outcome = "returned"
    try:
        asyncio.run_coroutine_threadsafe(job(), loop).result(_WAIT)
    except RuntimeError as exc:
        outcome = f"raised {exc}"
    value_now = observable.value
    transport_now = str(transport.get())  # read on the interpreter's own thread
    stopped = stop_loop(loop, thread)
    observable.release_transport()
    root.destroy()
    off_thread = len(delivered_on) == 2 and delivered_on[1] != main
    ok = (
        outcome == "returned"
        and value_now == "after"
        and transport_now == "before"
        and off_thread
        and stopped
    )
    return ok, (
        f"the write {outcome}; the value reads {value_now!r} but the transport still "
        f"holds {transport_now!r}, watcher delivered off-thread: {off_thread} -- "
        "tkinter's thread guard refuses the transport push and _push's dead-transport "
        "suppress swallows the refusal, so the write half-lands with no report anywhere"
    )


CHECKS: tuple[tuple[str, Callable[[], Report]], ...] = (
    ("a loop thread runs beside the mainloop", check_a_loop_thread_runs_beside_the_mainloop),
    (
        "an off-thread Tk call is refused, main out",
        check_an_off_thread_tk_call_is_refused_while_main_is_out,
    ),
    (
        "after() from the loop lands on the mainloop",
        check_after_from_the_loop_lands_on_the_mainloop,
    ),
    ("cancel reaches a mid-await coroutine", check_cancel_reaches_a_mid_await_coroutine),
    ("a stopped loop freezes pending tasks", check_a_stopped_loop_freezes_pending_tasks),
    ("cancel-then-stop runs the finally", check_cancel_then_stop_runs_the_finally_and_joins),
    ("a raise parks on the coroutine's future", check_a_raise_parks_on_the_coroutines_future),
    (
        "observable dispatches on the writing thread",
        check_todays_observable_dispatches_on_the_writing_thread,
    ),
    (
        "a transported off-thread write half-lands",
        check_a_transported_off_thread_write_half_lands,
    ),
)


def main() -> int:
    """Run every check, print each verdict, and return the failure count."""
    probe = tk.Tk()
    print(
        f"Tk {probe.tk.call('info', 'patchlevel')}, "
        f"threaded Tcl {probe.tk.call('set', 'tcl_platform(threaded)')}, "
        f"{sys.platform}"
    )
    probe.destroy()
    failures = 0
    for name, check in CHECKS:
        ok, detail = check()
        failures += 0 if ok else 1
        print(f"{name:44s} {'ok  ' if ok else 'FAIL'}  {detail}")
    return failures


if __name__ == "__main__":
    sys.exit(main())
