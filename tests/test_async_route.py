"""The async route: the core, the two doors, and the admissions.

The design is `experiments/async_route/`'s settled section, held here:
coroutines admitted through
`bind` and `watch` run on the root's core, touch no widget, write
observables through the implicit door and cross for answers through
`async_submit`, report raises to the hook, and are reached in flight only by
their handle's cancel. The core's own lifecycle is display-free; the
delivery tests run the *real* mainloop in segments, because the thread
wall (`hazards/tkinter.md`, *Threads*) refuses off-thread crossings whenever
the main thread is merely spinning ``update()`` between sleeps.
"""

import asyncio
import threading
import tkinter as tk
from typing import cast

import pytest

import tkfacade
from conftest import RunMainloop
from tkfacade import Virtual
from tkfacade._core import Core, resolve_core
from tkfacade.window import Root


def test_the_core_runs_submits_and_stops() -> None:
    """A fresh core takes a coroutine, returns its result, and stops clean.

    The lifecycle in one pass: start blocks until the loop takes work, a submission's future round-trips the result, stop is idempotent, and a refused submission raises rather than queueing into nothing — with the refused coroutine closed by submit, so the test ends with no never-awaited warning to swallow. Display-free on purpose: the core is asyncio and threading, and needing no interpreter here is part of what it promises.
    """
    core = Core()
    core.start()

    async def job() -> int:
        await asyncio.sleep(0)
        return 42

    assert core.submit(job()).result(5) == 42
    core.stop()
    core.stop()

    with pytest.raises(RuntimeError, match="not taking work"):
        core.submit(job())


def test_the_core_refuses_to_stop_itself() -> None:
    """stop() from the core's own thread raises instead of joining itself.

    The guard the vendored draft lacked: stop joins the loop thread, so a coroutine calling it would wait for itself forever. The raise parks on the scheduling future per the routing rules, which is also this suite's first proof that a coroutine's raise is retrievable at all.
    """
    core = Core()
    core.start()

    async def suicidal() -> None:
        await asyncio.sleep(0)
        core.stop()

    exc = core.submit(suicidal()).exception(5)
    core.stop()

    assert isinstance(exc, RuntimeError)
    assert "its own thread" in str(exc)


def test_stop_drains_running_tasks_through_their_finally() -> None:
    """stop cancels a lingering task and waits for its finally before joining.

    The witnessed teardown order made flesh: cancellation alone is fire-and-forget toward the coroutine, so a stop that did not wait for the unwind would strand this finally unrun — the probe watched exactly that happen. The assertion sits after stop() returns, which is the claim: by the time the join is over, every finally has run.
    """
    core = Core()
    core.start()
    started = threading.Event()
    story: list[str] = []

    async def lingering() -> None:
        started.set()
        try:
            await asyncio.sleep(30)
        finally:
            story.append("finally ran")

    core.submit(lingering())
    assert started.wait(5)
    core.stop(grace=0.05)

    assert story == ["finally ran"]


@pytest.mark.gui
def test_the_root_builds_its_core_lazily_and_drains_it(root: Root) -> None:
    """resolve_core builds once on first need, and Root.destroy stops it.

    Laziness is asserted from both sides: the slot is None until the registry's first resolve, and the second resolve answers the same core rather than a twin. Destroy is the whole teardown story — the loop thread dead proves the drain-stop-join ran, and the registry answering None proves a dispatch during teardown reports a miss instead of resurrecting a core on a dying root.
    """
    interp = root._tk.tk
    assert root._core is None
    core = resolve_core(interp)
    assert core is not None
    assert core is resolve_core(interp)
    thread = core._thread
    assert thread is not None and thread.is_alive()

    root.destroy()

    assert not thread.is_alive()
    assert resolve_core(interp) is None


@pytest.mark.gui
def test_an_async_observer_runs_on_the_core_and_writes_through_door_one(
    window: tkfacade.Window, run_mainloop: RunMainloop
) -> None:
    """The coroutine gets the event off-thread; its observable write lands on main.

    The route end to end, exactly as designed: the admission (a coroutine function bound as an observer, no refusal), the values crossing in (the frozen payload arrives intact), the core (the coroutine's thread is not the mainloop's), and the implicit door back (the off-thread write marshals its whole settle onto the mainloop — the sync watcher runs there, and the transport variable holds the new text, which is precisely the half that silently failed to land before the marshal existed).
    """
    frame = tkfacade.Frame(window)
    frame.grid(row=0, column=0)
    window.update_idletasks()
    main = threading.get_ident()
    shared = tkfacade.ObservableStr("before")
    transport = shared.transport_for(window._tk)
    facts: dict[str, object] = {}
    done = threading.Event()

    async def observer(event: tkfacade.Event) -> None:
        await asyncio.sleep(0)
        facts["payload"] = dict(event.payload)
        facts["thread"] = threading.get_ident()
        shared.value = "written off-thread"

    def landed(value: str) -> None:
        if value == "written off-thread":
            facts["watcher_thread"] = threading.get_ident()
            done.set()

    shared.watch(landed)
    frame.bind(Virtual("Ping"), observer)
    window._tk.after(0, lambda: frame.emit(Virtual("Ping"), {"n": 1}))
    run_mainloop(window, done)
    shared.release_transport()

    assert facts["payload"] == {"n": 1}
    assert facts["thread"] != main
    assert facts["watcher_thread"] == main
    # cast per the construction invariant: an ObservableStr's transport
    # is the StringVar its _new_var built, and the base get is untyped
    assert cast(tk.StringVar, transport).get() == "written off-thread"


@pytest.mark.gui
def test_async_submit_answers_and_raises_into_the_coroutine(
    root: Root, window: tkfacade.Window, run_mainloop: RunMainloop
) -> None:
    """async_submit returns the mainloop's answer; its raise lands at the await.

    The explicit door's two promises in one crossing: the answer comes back — a widget read performed on the mainloop, delivered into the awaiting coroutine — and the raise comes back through the same channel, catchable with a plain except. The empty hook is the channel-not-hook half of the routing rules: an exception the coroutine handles was reported to nobody else.
    """
    entry = tkfacade.Entry(window, "over the river")
    entry.grid(row=0, column=0)
    hooked: list[BaseException] = []
    root.callback_error_handler = hooked.append
    facts: dict[str, object] = {}
    done = threading.Event()

    def boom() -> None:
        raise ValueError("boom")

    async def crossing(_event: tkfacade.Event) -> None:
        facts["text"] = await entry.async_submit(lambda: entry.text)
        try:
            await entry.async_submit(boom)
        except ValueError as exc:
            facts["caught"] = str(exc)
        done.set()

    entry.bind(Virtual("Cross"), crossing)
    window._tk.after(0, lambda: entry.emit(Virtual("Cross")))
    run_mainloop(window, done)

    assert facts == {"text": "over the river", "caught": "boom"}
    assert hooked == []


@pytest.mark.gui
def test_an_async_observers_raise_reaches_the_hook(
    root: Root, window: tkfacade.Window, run_mainloop: RunMainloop
) -> None:
    """The fire-and-forget raise is retrieved and routed to the Root hook.

    The notification route's whole raise story: the facade retrieves the parked exception from the scheduling future — the loop's own handler never sees it, per the probe — and routes it to the same hook every sync raise already lands in, crossing back to the mainloop through the report seam. One error hook for the library, sync and async alike, which is the no-new-category ruling made observable.
    """
    frame = tkfacade.Frame(window)
    frame.grid(row=0, column=0)
    window.update_idletasks()
    hooked: list[BaseException] = []
    done = threading.Event()

    def hook(exc: BaseException) -> None:
        hooked.append(exc)
        done.set()

    root.callback_error_handler = hook

    async def failing(_event: tkfacade.Event) -> None:
        await asyncio.sleep(0)
        raise ValueError("async boom")

    frame.bind(Virtual("Ping"), failing)
    window._tk.after(0, lambda: frame.emit(Virtual("Ping")))
    run_mainloop(window, done)

    assert len(hooked) == 1
    assert isinstance(hooked[0], ValueError)
    assert str(hooked[0]) == "async boom"


@pytest.mark.gui
def test_cancelling_the_subscription_cancels_work_in_flight(
    root: Root, window: tkfacade.Window, run_mainloop: RunMainloop
) -> None:
    """cancel() stops deliveries and unwinds the running coroutine, silently.

    Death narrows the future; the handle reaches the present. The coroutine is parked thirty seconds deep when cancel() sweeps the subscription's live tasks, and the finally running is the proof the cancellation genuinely arrived at the await rather than merely flipping the future. The empty hook pins cancellation-as-lifecycle: nothing about this ordinary end was reported as an error.
    """
    frame = tkfacade.Frame(window)
    frame.grid(row=0, column=0)
    window.update_idletasks()
    hooked: list[BaseException] = []
    root.callback_error_handler = hooked.append
    started = threading.Event()
    unwound = threading.Event()

    async def lingering(_event: tkfacade.Event) -> None:
        started.set()
        try:
            await asyncio.sleep(30)
        finally:
            unwound.set()

    subscription = frame.bind(Virtual("Ping"), lingering)
    window._tk.after(0, lambda: frame.emit(Virtual("Ping")))
    run_mainloop(window, started)

    subscription.cancel()
    run_mainloop(window, unwound)

    assert unwound.is_set()
    assert hooked == []


@pytest.mark.gui
def test_an_async_watcher_runs_on_the_core(
    window: tkfacade.Window, run_mainloop: RunMainloop
) -> None:
    """A coroutine watcher is scheduled with each settled value, birth included.

    The second admission route: watch accepts the coroutine function the variable era refused, and both the immediate first call and the settled change arrive as scheduled runs on the core — off the mainloop, in order, each carrying the value that scheduled it. The transport is what gives the observable a root to resolve the core through; the transportless miss is pinned in test_observable.py.
    """
    shared = tkfacade.ObservableInt(1)
    shared.transport_for(window._tk)
    main = threading.get_ident()
    seen: list[tuple[int, bool]] = []
    done = threading.Event()

    async def watcher(value: int) -> None:
        await asyncio.sleep(0)
        seen.append((value, threading.get_ident() != main))
        if value == 2:
            done.set()

    shared.watch(watcher)
    window._tk.after(0, lambda: setattr(shared, "value", 2))
    run_mainloop(window, done)
    shared.release_transport()

    assert seen == [(1, True), (2, True)]
