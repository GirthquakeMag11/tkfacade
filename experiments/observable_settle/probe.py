"""Prove the observable's settle-dispatch and Tk-transport sync, one check per claim.

Run with::

    xvfb-run -a uv run python -m experiments.observable_settle.probe

The observability design (ruled 2026-08-20:
Python-held value, Tk variable as attachable transport) rests on
machinery the callback delivery rules demand but Tk does not provide:
library-dispatched notification where no watcher ends holding a
superseded value, write-back visible to every sibling, an echo-proof
two-way sync with a ``tk.Variable``, and survival of the interpreter
the transport belongs to. :class:`PrototypeObservable` below is the
minimal reference of that machinery — deliberately naive everywhere the
design is not yet ruled — and each check witnesses one claim about it,
or one Tk fact the transport must live with.

Expectations are the behavior witnessed on Tk 8.6.14 (threaded Tcl,
X11 and win32 agree per ``../callback_doctrine/``); the pure-Python
checks have no platform to vary with. A FAIL is a finding. Every check
prints its verdict; the exit status is the number that failed.
"""

import sys
import tkinter as tk
from collections.abc import Callable

Report = tuple[bool, str]

SETTLE_CAP = 8
"""Rounds of re-notification allowed before a fight is declared divergent."""


class PrototypeObservable:
    """A Python-held observable value with an attachable Tk transport.

    The reference for the design's machinery, not the design: watchers
    are called with the then-current value until every one of them has
    seen the value the write settled at (per-watcher last-seen
    bookkeeping); a write equal to the current value is dropped, which
    is also what makes the transport echo silent; a write arriving
    mid-dispatch defers to the running settle loop instead of nesting.
    Divergent fights stop at :data:`SETTLE_CAP` rounds and are recorded
    in :attr:`divergences` — what *should* happen then is a design
    ruling this prototype deliberately does not take.
    """

    def __init__(self, value: str) -> None:
        self._value = value
        self._watchers: list[Callable[[str], None]] = []
        self._seen: dict[int, str | None] = {}
        self._dispatching = False
        self._var: tk.StringVar | None = None
        self._trace: str = ""
        self.divergences: list[int] = []

    def get(self) -> str:
        return self._value

    def set(self, value: str) -> None:
        if value == self._value:
            return
        self._value = value
        self._push_transport()
        if not self._dispatching:
            self._dispatch()

    def watch(self, watcher: Callable[[str], None]) -> None:
        self._watchers.append(watcher)
        self._seen[id(watcher)] = None

    def attach(self, master: tk.Misc) -> tk.StringVar:
        self._var = tk.StringVar(master, self._value)
        self._trace = self._var.trace_add("write", self._on_transport_write)
        return self._var

    def detach(self) -> None:
        if self._var is not None:
            self._var.trace_remove("write", self._trace)
            self._var = None

    def _push_transport(self) -> None:
        if self._var is not None:
            self._var.set(self._value)

    def _on_transport_write(self, *_: str) -> None:
        assert self._var is not None
        incoming = self._var.get()
        if incoming == self._value:
            return  # the echo of our own push, or a no-change write
        self._value = incoming
        if not self._dispatching:
            self._dispatch()

    def _dispatch(self) -> None:
        self._dispatching = True
        try:
            for _round in range(SETTLE_CAP):
                settled = True
                for watcher in list(self._watchers):
                    if self._seen[id(watcher)] != self._value:
                        self._seen[id(watcher)] = self._value
                        watcher(self._value)
                        settled = False
                if settled:
                    return
            self.divergences.append(SETTLE_CAP)
        finally:
            self._dispatching = False


def check_writeback_settles_every_watcher() -> Report:
    """A clamping watcher's write-back settles every sibling; later ones coalesce."""
    volume = PrototypeObservable("0")
    calls: dict[str, list[str]] = {"clamper": [], "recorder": []}

    def clamper(value: str) -> None:
        calls["clamper"].append(value)
        if int(value) > 100:
            volume.set("100")

    volume.watch(clamper)
    volume.watch(lambda v: calls["recorder"].append(v))
    volume.set("150")
    ok = (
        volume.get() == "100"
        and calls["recorder"] == ["100"]
        and calls["clamper"] == ["150", "100"]
        and not volume.divergences
    )
    return (
        ok,
        f"value {volume.get()!r}, clamper saw {calls['clamper']}, recorder saw {calls['recorder']}",
    )


# Witnessed on the first discovery run and kept as the semantic: a watcher
# is called with the value current at its turn, so a sibling registered
# after the corrector never sees the uncorrected value at all -- natural
# coalescing -- while one registered before it sees both (the next check).
# Which intermediates a watcher sees depends on registration order; the
# settled value reaching everyone does not.


def check_registration_order_does_not_matter() -> Report:
    """The recorder ends on the settled value whichever side of the clamper it joined."""
    volume = PrototypeObservable("0")
    recorder: list[str] = []
    volume.watch(lambda v: recorder.append(v))

    def clamper(value: str) -> None:
        if int(value) > 100:
            volume.set("100")

    volume.watch(clamper)
    volume.set("150")
    ok = volume.get() == "100" and recorder[-1] == "100"
    return ok, f"recorder-before-clamper saw {recorder}; last is the settled value"


def check_a_two_state_fight_converges() -> Report:
    """Two watchers overwriting each other's values settle without hitting the cap."""
    flag = PrototypeObservable("start")
    last_seen: dict[str, str] = {}

    def ping(value: str) -> None:
        last_seen["ping"] = value
        if value == "pong":
            flag.set("ping")

    def pong(value: str) -> None:
        last_seen["pong"] = value
        if value == "ping":
            flag.set("pong")

    flag.watch(ping)
    flag.watch(pong)
    flag.set("ping")
    consistent = last_seen["ping"] == last_seen["pong"] == flag.get()
    ok = not flag.divergences and consistent
    return ok, (
        f"no divergence recorded, value {flag.get()!r}, both watchers current: {consistent}"
    )


# Discovered on the first run rather than designed: the per-watcher
# last-seen bookkeeping defuses this fight. Each fighter only reacts to a
# value it has not seen, the oscillation revisits seen values, and both
# settle -- so the dedupe that exists for consistency also converges every
# fight whose values repeat. Only a fight minting fresh values each round
# can diverge, which is the next check.


def check_a_fresh_value_fight_stops_at_the_cap() -> Report:
    """A watcher minting a new value every round is stopped at the cap, lagging."""
    counter = PrototypeObservable("0")
    seen: list[str] = []

    def incrementer(value: str) -> None:
        seen.append(value)
        counter.set(str(int(value) + 1))

    counter.watch(incrementer)
    counter.set("1")
    lagging = seen[-1] != counter.get()
    ok = counter.divergences == [SETTLE_CAP] and counter.get() == "9" and lagging
    return ok, (
        f"divergence recorded at cap {SETTLE_CAP}, value {counter.get()!r}, "
        f"fighter last saw {seen[-1]!r}: at a true divergence the stop leaves it lagging"
    )


# The honest half of the fight story: a genuinely divergent watcher --
# one that answers every value with a fresh one -- consumes a round per
# value and is cut off at the cap, at which point the value it wrote last
# has not been delivered back to it. Consistency at the cap is
# unattainable by definition (the fight never settles), which is exactly
# why what-to-do-at-the-cap is a design ruling and not a mechanism: the
# prototype records the divergence and stops, taking no policy of its own.


def check_equal_write_notifies_nobody() -> Report:
    """Writing the value already held calls no watcher."""
    name = PrototypeObservable("Ada")
    calls: list[str] = []
    name.watch(calls.append)
    name.set("Ada")
    ok = calls == []
    return ok, f"watcher calls {calls}"


def check_python_write_reaches_tk_once() -> Report:
    """A Python-side set lands in the transport variable without an echo dispatch."""
    root = tk.Tk()
    root.withdraw()
    name = PrototypeObservable("Ada")
    calls: list[str] = []
    name.watch(calls.append)
    var = name.attach(root)
    name.set("Grace")
    ok = var.get() == "Grace" and calls == ["Grace"]
    root.destroy()
    return ok, f"variable holds {var.get()!r}, watcher saw {calls} (once, no echo)"


def check_tk_write_reaches_python_once() -> Report:
    """A widget-side write to the variable updates the value and notifies once."""
    root = tk.Tk()
    root.withdraw()
    name = PrototypeObservable("Ada")
    calls: list[str] = []
    name.watch(calls.append)
    var = name.attach(root)
    var.set("Grace")
    ok = name.get() == "Grace" and calls == ["Grace"]
    root.destroy()
    return ok, f"value {name.get()!r}, watcher saw {calls}"


def check_widget_write_clamped_lands_back_in_tk() -> Report:
    """A widget-side write a watcher clamps ends with the transport holding the clamp."""
    root = tk.Tk()
    root.withdraw()
    volume = PrototypeObservable("0")

    def clamper(value: str) -> None:
        if value.isdigit() and int(value) > 100:
            volume.set("100")

    volume.watch(clamper)
    var = volume.attach(root)
    var.set("150")
    ok = volume.get() == "100" and var.get() == "100"
    root.destroy()
    return ok, f"value {volume.get()!r}, transport variable holds {var.get()!r}"


def check_detach_is_clean_and_reattach_works() -> Report:
    """After detach the variable is inert and traceless; a re-attach picks up."""
    root = tk.Tk()
    root.withdraw()
    name = PrototypeObservable("Ada")
    var = name.attach(root)
    name.detach()
    traceless = var.trace_info() == []
    var.set("stray")
    unaffected = name.get() == "Ada"
    second = name.attach(root)
    seeded = second.get() == "Ada"
    name.set("Grace")
    ok = traceless and unaffected and seeded and second.get() == "Grace"
    root.destroy()
    return ok, (
        f"traces after detach {var.trace_info()}, stray write ignored {unaffected}, "
        f"re-attach seeded {seeded} and tracks"
    )


def check_value_survives_its_interpreter() -> Report:
    """The Python value outlives root destruction and the interpreter's collection."""
    import gc

    root = tk.Tk()
    root.withdraw()
    name = PrototypeObservable("Ada")
    name.attach(root)
    name.set("Grace")
    root.destroy()
    ghost_write_ok = ""
    try:
        name.set("Hopper")  # tcl variables are interpreter-level: destroy() kills
        ghost_write_ok = "landed"  # widgets, not the interp, so this still works
    except Exception as exc:
        ghost_write_ok = type(exc).__name__
    after_destroy = name.get()
    del root
    gc.collect()
    collected = ""
    try:
        name.set("Lovelace")
    except Exception as exc:
        collected = type(exc).__name__
    ok = (
        after_destroy == "Hopper"
        and ghost_write_ok == "landed"
        and name.get() == "Lovelace"
        and collected == ""
    )
    return ok, (
        f"after destroy(): set() {ghost_write_ok}, value {after_destroy!r}; "
        f"after the Tk object is collected: set() -> {collected or 'no error'}, "
        f"value {name.get()!r}"
    )


def check_a_trace_can_fire_on_an_unreadable_variable() -> Report:
    """The widget route can put text in a DoubleVar; the trace fires, get() raises."""
    root = tk.Tk()
    root.withdraw()
    var = tk.DoubleVar(root, 1.5)
    fired: list[str] = []
    outcome: list[str] = []

    def on_write(*_: str) -> None:
        fired.append("fired")
        try:
            var.get()
        except tk.TclError:
            outcome.append("get raised")
        else:
            outcome.append("get worked")

    var.trace_add("write", on_write)
    root.tk.call("set", str(var), "abc")  # what an Entry does: raw string, no coercion
    ok = fired == ["fired"] and outcome == ["get raised"]
    root.destroy()
    return (
        ok,
        f"trace {fired}, typed read {outcome}: the variable held text a DoubleVar cannot read",
    )


CHECKS: tuple[tuple[str, Callable[[], Report]], ...] = (
    ("write-back settles every watcher", check_writeback_settles_every_watcher),
    ("registration order does not matter", check_registration_order_does_not_matter),
    ("a two-state fight converges", check_a_two_state_fight_converges),
    ("a fresh-value fight stops at the cap", check_a_fresh_value_fight_stops_at_the_cap),
    ("an equal write notifies nobody", check_equal_write_notifies_nobody),
    ("python write reaches tk once, no echo", check_python_write_reaches_tk_once),
    ("tk write reaches python once", check_tk_write_reaches_python_once),
    ("widget write clamped lands back in tk", check_widget_write_clamped_lands_back_in_tk),
    ("detach is clean and re-attach works", check_detach_is_clean_and_reattach_works),
    ("the value survives its interpreter", check_value_survives_its_interpreter),
    (
        "a trace can fire on an unreadable variable",
        check_a_trace_can_fire_on_an_unreadable_variable,
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
        print(f"{name:46s} {'ok  ' if ok else 'FAIL'}  {detail}")
    return failures


if __name__ == "__main__":
    sys.exit(main())
