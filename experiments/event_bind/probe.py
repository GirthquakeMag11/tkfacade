"""Witness the binding mechanics the events design rests on, one check per claim.

Run with::

    xvfb-run -a uv run python -m experiments.event_bind.probe

The events design must decide how a binding is revoked, how a handler stops
an event's propagation, and what a user-defined event can carry. Those
decisions rest on Tk and tkinter facts this probe pins: whether
``unbind`` with a funcid is surgical or clears the whole sequence,
what ``"break"`` stops at each level of the chain, whether
``event_generate``'s ``data`` payload is reachable through tkinter's
own binding route or only through a raw Tcl ``%d`` substitution, how
modifier state in a generated event matches modifier-qualified
bindings, and what click counting does with synthetic events. The
delivery-side facts (thread, exceptions, destroy, unmapped drops) are
already pinned by ``../callback_doctrine/``.

Expectations are the behavior witnessed on Tk 8.6.14 (threaded Tcl,
X11), CPython 3.14. A FAIL is a finding: that build does not behave the
way the design's evidence says. Every check prints its verdict; the
exit status is the number that failed.
"""

import sys
import tkinter as tk
from collections.abc import Callable

Report = tuple[bool, str]


def bench() -> tk.Tk:
    """Return a root ready for mapped widgets and generated events."""
    root = tk.Tk()
    root.withdraw()
    return root


def mapped_frame(root: tk.Tk) -> tk.Frame:
    """Return a frame that is actually on screen, so generated events reach it."""
    root.deiconify()
    frame = tk.Frame(root)
    frame.pack()
    root.update()
    return frame


def check_unbind_with_funcid_is_surgical() -> Report:
    """Unbinding one funcid leaves the sequence's other handlers bound and firing."""
    root = bench()
    widget = mapped_frame(root)
    ran: list[str] = []
    first = widget.bind("<<Probe>>", lambda _e: ran.append("first"))
    widget.bind("<<Probe>>", lambda _e: ran.append("second"), add="+")
    widget.unbind("<<Probe>>", first)
    widget.event_generate("<<Probe>>")
    ok = ran == ["second"]
    root.destroy()
    return ok, f"after unbinding the first funcid, ran {ran}"


def check_unbind_deletes_the_funcid_command() -> Report:
    """The unbound funcid's Tcl command is deleted, not left registered."""
    root = bench()
    widget = mapped_frame(root)
    first = widget.bind("<<Probe>>", lambda _e: None)
    second = widget.bind("<<Probe>>", lambda _e: None, add="+")
    widget.unbind("<<Probe>>", first)
    gone = not root.tk.call("info", "commands", first)
    kept = bool(root.tk.call("info", "commands", second))
    ok = gone and kept
    root.destroy()
    return ok, f"unbound command deleted: {gone}; the surviving handler's command kept: {kept}"


def check_break_stops_the_added_handlers() -> Report:
    """A handler returning 'break' stops the add='+' handlers bound after it."""
    root = bench()
    widget = mapped_frame(root)
    ran: list[str] = []

    def first(_e: tk.Event[tk.Frame]) -> str:
        ran.append("first")
        return "break"

    widget.bind("<<Probe>>", first)
    widget.bind("<<Probe>>", lambda _e: ran.append("second"), add="+")
    widget.event_generate("<<Probe>>")
    ok = ran == ["first"]
    root.destroy()
    return ok, f"ran {ran}; 'break' cut the widget's own chain"


def check_break_stops_the_class_default() -> Report:
    """A widget-level 'break' keeps the class binding from inserting the keystroke."""
    root = bench()
    root.deiconify()
    consumed = tk.Entry(root)
    passive = tk.Entry(root)
    consumed.pack()
    passive.pack()
    root.update()

    def eat(_e: tk.Event[tk.Entry]) -> str:
        return "break"

    consumed.bind("<KeyPress-a>", eat)
    for entry in (consumed, passive):
        entry.focus_force()
        root.update()
        entry.event_generate("<KeyPress-a>")
        root.update()
    held = consumed.get()
    typed = passive.get()
    ok = held == "" and typed == "a"
    root.destroy()
    return ok, (
        f"with 'break' the entry holds {held!r}, "
        f"without it {typed!r}: the class default is stoppable"
    )


def check_data_payload_is_invisible_to_tkinter() -> Report:
    """event_generate's data reaches a raw %d binding as a string, tkinter not at all."""
    root = bench()
    widget = mapped_frame(root)
    seen_tkinter: list[object] = []
    seen_raw: list[str] = []
    widget.bind("<<Carry>>", lambda e: seen_tkinter.append(getattr(e, "data", "no attribute")))
    recorder = widget.register(lambda value: seen_raw.append(value))
    root.tk.call("bind", str(widget), "<<Carry>>", f"+{recorder} %d")
    widget.event_generate("<<Carry>>", data="hello")
    ok = seen_tkinter == ["no attribute"] and seen_raw == ["hello"]
    root.destroy()
    return ok, f"tkinter handler saw {seen_tkinter}, raw %d binding saw {seen_raw}"


def check_the_most_specific_binding_fires_alone() -> Report:
    """A modifier-qualified binding beats the plain one for its events — exclusively."""
    root = bench()
    widget = mapped_frame(root)
    plain_states: list[int] = []
    control_ran: list[str] = []
    widget.bind("<Button-1>", lambda e: plain_states.append(int(e.state)))
    widget.bind("<Control-Button-1>", lambda _e: control_ran.append("control"))
    widget.event_generate("<Button-1>", x=1, y=1)
    widget.event_generate("<Button-1>", x=1, y=1, state=0x4)  # ModifierState CONTROL
    ok = plain_states == [0] and control_ran == ["control"]
    root.destroy()
    return ok, (
        f"plain binding saw states {plain_states}, control binding fired {control_ran}: "
        f"the control-click went to the specific binding alone"
    )


# Two facts in one witness. A generated event's state bits do satisfy a
# modifier-qualified binding, so specs with modifiers round-trip through
# event_generate -- and when more than one binding on the same tag
# matches, Tk fires only the most specific one, not all of them. The
# second fact is the surprise: the add='+' mental model says handlers
# stack, but stacking is per-sequence -- across sequences on one widget,
# related specs compete and the loser hears nothing.


def check_generated_clicks_count_up_but_a_double_cannot_be_asked_for() -> Report:
    """Rapid generated singles count into a double; direct double generation is refused."""
    root = bench()
    widget = mapped_frame(root)
    counts: dict[str, int] = {"single": 0, "double": 0}
    widget.bind("<Button-1>", lambda _e: counts.__setitem__("single", counts["single"] + 1))
    widget.bind("<Double-Button-1>", lambda _e: counts.__setitem__("double", counts["double"] + 1))
    widget.event_generate("<Button-1>", x=1, y=1)
    widget.event_generate("<Button-1>", x=1, y=1)
    refused = ""
    try:
        widget.event_generate("<Double-Button-1>", x=1, y=1)
    except tk.TclError as exc:
        refused = str(exc)
    ok = counts == {"single": 1, "double": 1} and "not allowed" in refused
    root.destroy()
    return (
        ok,
        f"two rapid generated singles counted {counts}; asking for a double raised {refused!r}",
    )


# Assumed one way and witnessed the other: Tk's click counter runs on
# event time, and generated events carry the current time, so two
# back-to-back synthetic singles sit inside the double-click window and
# the second is delivered as <Double-Button-1> -- exclusively, by the
# most-specific rule above, which is why the single count stays at one.
# Asking for the double directly is refused ("Double, Triple, or
# Quadruple modifier not allowed"), so the only route to a synthetic
# multi-click is the same route a user takes: repeated singles in time.
# The two generates run in the same burst, microseconds apart, so the
# 500ms window makes this stable rather than timing-flaky.


CHECKS: tuple[tuple[str, Callable[[], Report]], ...] = (
    ("unbind with a funcid is surgical", check_unbind_with_funcid_is_surgical),
    ("unbind deletes the funcid's command", check_unbind_deletes_the_funcid_command),
    ("'break' stops the added handlers", check_break_stops_the_added_handlers),
    ("'break' stops the class default", check_break_stops_the_class_default),
    ("data payload is invisible to tkinter", check_data_payload_is_invisible_to_tkinter),
    ("the most specific binding fires alone", check_the_most_specific_binding_fires_alone),
    (
        "generated clicks count up; no direct double",
        check_generated_clicks_count_up_but_a_double_cannot_be_asked_for,
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
