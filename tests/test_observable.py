"""The observable contract: settled truth, the transport, and the hook.

The pure value semantics — the settle dispatch, the equal-write drop,
the immediate first call, fights and their divergence report — need no
interpreter and run anywhere; the transport half rides the ``window``
fixture under the ``gui`` marker. The machinery's evidence is
``experiments/observable_settle/``; these tests hold the production
class to the same witnessed behavior, plus the pieces the prototype
deliberately left undecided: divergence routed through the callback
error hook, the coroutine refusal, and the rider-counted transport
lifecycle.
"""

import tkinter as tk
from typing import cast

import pytest

import tkfacade
from tkfacade import DivergenceError, ObservableFloat, ObservableInt, ObservableStr
from tkfacade.window import Root


def test_the_value_is_read_and_assigned_through_one_property() -> None:
    """Assigning ``value`` changes what it answers; no root is required.

    The architecture ruling made observable state plain Python: this runs with no tk.Tk anywhere in the process, which is the property the declarative endgame stands on (state defined before any UI exists). The one-property surface is the spelling choice the design left open, pinned here so a second accessor cannot drift in beside it.
    """
    name = ObservableStr("Ada")
    assert name.value == "Ada"
    name.value = "Grace"
    assert name.value == "Grace"


def test_an_equal_write_notifies_nobody() -> None:
    """Assigning the value already held calls no watcher.

    The equal-write drop is load-bearing twice over: it is the notification contract's "no watcher runs for nothing" and it is the whole of the transport's echo suppression. The single recorded call is watch()'s immediate one — asserted exactly, so an equal write sneaking a second delivery fails by count rather than by content.
    """
    name = ObservableStr("Ada")
    calls: list[str] = []
    name.watch(calls.append)
    name.value = "Ada"
    assert calls == ["Ada"]


def test_watch_calls_the_new_watcher_immediately() -> None:
    """A watcher receives the current value at registration, before any change.

    The ruled first-call semantic: a watcher is never stale, its birth included, which is what lets a bound label render now rather than on the next change. The subscription's liveness is asserted beside it because the immediate call happens after the handle is built — a watcher raising at birth must not return a half-made handle.
    """
    volume = ObservableFloat(75.0)
    calls: list[float] = []
    subscription = volume.watch(calls.append)
    assert calls == pytest.approx([75.0])
    assert subscription.active


def test_a_writeback_settles_every_sibling_registered_after_it() -> None:
    """A sibling registered after the clamper never sees the unclamped value."""
    volume = ObservableInt(0)

    def clamper(value: int) -> None:
        if value > 100:
            volume.value = 100

    volume.watch(clamper)
    recorder: list[int] = []
    volume.watch(recorder.append)
    volume.value = 150
    assert volume.value == 100
    assert recorder == [0, 100]


def test_a_writeback_re_notifies_the_sibling_registered_before_it() -> None:
    """A sibling registered before the clamper sees both values, settled last.

    The settled-truth guarantee in both registration orders: whoever runs after the correction is called with the corrected value and never the stale one; whoever ran before it is called again. Which intermediates a watcher sees depends on order — witnessed and kept as the semantic — while the settled value reaching everyone does not. The leading 0 in each recording is the immediate first call.
    """
    volume = ObservableInt(0)
    recorder: list[int] = []
    volume.watch(recorder.append)

    def clamper(value: int) -> None:
        if value > 100:
            volume.value = 100

    volume.watch(clamper)
    volume.value = 150
    assert volume.value == 100
    assert recorder == [0, 150, 100]


def test_a_two_state_fight_converges_without_the_cap(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Two watchers overwriting each other's values settle; nothing is reported.

    The discovered convergence property, held: per-watcher last-seen bookkeeping means a fighter only reacts to values it has not seen, so an oscillation over repeating values settles on its own. Silence on stderr is the assertion because an unattached observable reports divergences there — a report would mean the dedupe regressed and the cap caught what used to converge.
    """
    flag = ObservableStr("start")

    def ping(value: str) -> None:
        if value == "pong":
            flag.value = "ping"

    def pong(value: str) -> None:
        if value == "ping":
            flag.value = "pong"

    flag.watch(ping)
    flag.watch(pong)
    flag.value = "ping"
    assert capsys.readouterr().err == ""


def test_a_fresh_value_fight_is_reported_and_the_last_value_kept(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A watcher minting new values is cut off, reported once, and the value stands.

    The divergence ruling's unattached half: with no transport there is no interpreter to route through, so the report goes to stderr — and the ruled "keep the last value" leaves the counter where the cap caught it (1 through the setter plus eight rounds of the settle loop). The incrementer sits out the initial value deliberately: watch() calls a new watcher immediately, so a fighter with no guard starts a first fight at registration and the one write under test would be the second — the report is counted, not merely spotted, to pin exactly one. The attached half, routed through the Root hook, is the gui test below.
    """
    counter = ObservableInt(0)

    def incrementer(value: int) -> None:
        if value:
            counter.value = value + 1

    counter.watch(incrementer)
    counter.value = 1
    stderr = capsys.readouterr().err
    assert stderr.count("did not settle") == 1
    assert counter.value == 9


def test_a_raising_watcher_is_reported_and_its_sibling_still_runs(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A watcher's raise goes to the report; the next watcher runs regardless.

    Fire-and-forget, kept by the library's own dispatch: raw Tk traces already spare sibling traces, and the fanout must not do worse. The sibling's two calls pin that delivery went on both at the raise's own dispatch and at registration time.
    """
    name = ObservableStr("Ada")

    def bad(_value: str) -> None:
        raise RuntimeError("watcher boom")

    name.watch(bad)
    recorder: list[str] = []
    name.watch(recorder.append)
    name.value = "Grace"
    assert recorder == ["Ada", "Grace"]
    assert "watcher boom" in capsys.readouterr().err


def test_an_unattached_async_watcher_reports_the_missing_core(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A coroutine watcher on a transportless observable is a reported miss.

    The async route's admission replaced the old loud refusal: a coroutine watcher is accepted and scheduled on the host root's core — but an observable with no transport has no root to resolve a core through, so the immediate first call becomes a reported miss instead of a silent never-awaited coroutine. Reported through the observable's own seam, which lands on stderr precisely because there is no interpreter to route through; the delivery half of the admission is pinned in tests/test_async_route.py, where a core exists.
    """
    name = ObservableStr("Ada")

    async def watcher(_value: str) -> None:
        pass

    subscription = name.watch(watcher)

    assert subscription.active
    assert "no core to run the async watcher" in capsys.readouterr().err


def test_cancel_stops_delivery_and_is_idempotent() -> None:
    """A cancelled subscription never delivers again; cancelling twice is fine."""
    name = ObservableStr("Ada")
    calls: list[str] = []
    subscription = name.watch(calls.append)
    subscription.cancel()
    subscription.cancel()
    name.value = "Grace"
    assert calls == ["Ada"]
    assert not subscription.active


def test_a_watcher_cancelled_mid_dispatch_is_not_called() -> None:
    """A cancellation made inside a watcher takes effect within the same dispatch.

    Cancellation's two contracts. Idempotence is the handle's own promise. The mid-dispatch case pins that active is consulted at each delivery rather than snapshotted per write: the recorder legitimately sees "Grace" (it ran before the canceller that round) and must never see "Hopper". A snapshot-per-write dispatch would deliver both and fail.
    """
    name = ObservableStr("Ada")
    calls: list[str] = []
    second = name.watch(calls.append)

    def canceller(value: str) -> None:
        if value == "Grace":
            second.cancel()

    name.watch(canceller)
    # registration order: recorder first, canceller second -- so on the
    # settle loop's next round the recorder is already cancelled
    name.value = "Grace"
    name.value = "Hopper"
    assert calls == ["Ada", "Grace"]


def test_nan_settles_as_itself() -> None:
    """Assigning NaN over NaN is an equal write; nothing loops, nothing reports.

    NaN is the one value Python holds unequal to itself, which would turn the equal-write drop into an infinite echo between transport and dispatch: every push would read back as a fresh value. ObservableFloat counts NaN as itself, so the second assignment is dropped — two calls, the immediate one and the first NaN, and the settle loop terminated rather than running to the cap (a divergence report would have printed and the count would exceed two).
    """
    level = ObservableFloat(0.0)
    calls: list[float] = []
    level.watch(calls.append)
    level.value = float("nan")
    level.value = float("nan")
    assert len(calls) == 2


@pytest.mark.gui
def test_the_transport_round_trips_both_directions(window: tkfacade.Window) -> None:
    """A value assignment lands in the variable; a variable write comes back, once.

    The two-way sync with the echo silent: each change is delivered exactly once whichever side wrote it, pinned by the calls list being one entry per distinct value. An unsuppressed echo would double the Python-side write ("Grace" twice, once from the setter's dispatch and once from the transport trace); a missed inbound would drop "Hopper". The test passes the window's underlying widget the way wrappers will: transport_for takes a real tk.Misc on the target interpreter.
    """
    name = ObservableStr("Ada")
    calls: list[str] = []
    name.watch(calls.append)
    var = cast(tk.StringVar, name.transport_for(window._tk))
    assert var.get() == "Ada"

    name.value = "Grace"
    assert var.get() == "Grace"

    var.set("Hopper")
    assert name.value == "Hopper"
    assert calls == ["Ada", "Grace", "Hopper"]


@pytest.mark.gui
def test_a_widget_write_a_watcher_clamps_lands_back_in_the_variable(
    window: tkfacade.Window,
) -> None:
    """A transport write the clamper corrects ends with the variable corrected.

    The case raw traces witnessedly cannot deliver (hazards/tkinter.md, Variables): a write made inside a trace fires no traces, so over raw Tk the widget would keep showing 150 while the value said 100. The library's dispatch pushes the clamp back through the transport, so whatever rides the variable — eventually an Entry or a Scale — shows the settled truth.
    """
    volume = ObservableInt(0)

    def clamper(value: int) -> None:
        if value > 100:
            volume.value = 100

    volume.watch(clamper)
    var = cast(tk.IntVar, volume.transport_for(window._tk))
    var.set(150)
    assert volume.value == 100
    assert var.get() == 100


@pytest.mark.gui
def test_unreadable_transport_text_keeps_the_last_good_value(
    window: tkfacade.Window,
) -> None:
    """Text a float cannot read is ignored; the value and watchers stand pat.

    The guarded inbound read the design owes to the unreadable-variable hazard: the widget route can put arbitrary text in a typed variable and the trace fires before any read fails, so the sync must survive the read raising and keep the last good value — silently, since the half-typed state is transient keystroke noise, not an error the application can act on. The raw Tcl set is the exact widget route the hazard names.
    """
    level = ObservableFloat(1.5)
    calls: list[float] = []
    level.watch(calls.append)
    var = level.transport_for(window._tk)
    window._tk.tk.call("set", str(var), "abc")
    assert level.value == pytest.approx(1.5)
    assert calls == pytest.approx([1.5])


@pytest.mark.gui
def test_the_transport_is_shared_counted_and_dropped_at_zero(
    window: tkfacade.Window,
) -> None:
    """Two acquisitions share one variable; the trace survives one release, not two.

    The rider-counted lifecycle from the design: one transport serves every widget on the interpreter, and the drop at zero is what keeps a tk.Variable from pinning a dead interpreter for process life (hazards/tkinter.md, Variables). trace_info is the observable ground truth for attachment — a dropped transport is traceless and inert — and the re-acquisition seeding "Ada" proves a fresh variable starts from the Python-held value rather than whatever the old one last held.
    """
    name = ObservableStr("Ada")
    first = name.transport_for(window._tk)
    second = name.transport_for(window._tk)
    assert first is second

    name.release_transport()
    assert first.trace_info()

    name.release_transport()
    assert not first.trace_info()

    reacquired = cast(tk.StringVar, name.transport_for(window._tk))
    assert reacquired is not first
    assert reacquired.get() == "Ada"


@pytest.mark.gui
def test_an_attached_divergence_reaches_the_callback_error_hook(
    window: tkfacade.Window, root: Root
) -> None:
    """With a transport attached, the divergence report lands in the Root hook.

    The divergence ruling's attached half: the report rides an after_idle raise down Tk's own swallow path, so it arrives wherever the application routed callback errors — the hook — rather than inventing a parallel error channel. The update() pump is what delivers the idle job; the fire-and-forget shape means the report never raced the setter. The kept value matches the unattached twin above.
    """
    caught: list[BaseException] = []
    root.callback_error_handler = caught.append
    counter = ObservableInt(0)
    counter.transport_for(window._tk)

    def incrementer(value: int) -> None:
        if value:
            counter.value = value + 1

    counter.watch(incrementer)
    counter.value = 1
    window._tk.update()

    assert len(caught) == 1
    assert isinstance(caught[0], DivergenceError)
    assert counter.value == 9


@pytest.mark.gui
def test_an_attached_watcher_raise_reaches_the_callback_error_hook(
    window: tkfacade.Window, root: Root
) -> None:
    """A watcher's raise on an attached observable routes to the Root hook.

    One raise, one report, the exception instance itself: watcher raises use the same routing as divergences, so an application's error handling is one hook however the callback failed. The raise here happens at watch()'s immediate call, pinning that registration-time delivery is guarded by the same reporting as dispatch-time delivery.
    """
    caught: list[BaseException] = []
    root.callback_error_handler = caught.append
    name = ObservableStr("Ada")
    name.transport_for(window._tk)
    boom = RuntimeError("watcher boom")

    def bad(_value: str) -> None:
        raise boom

    name.watch(bad)
    window._tk.update()

    assert caught == [boom]
