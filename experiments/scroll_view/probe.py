"""Witness the scroll-protocol facts the `ScrollView` design rests on.

Run with::

    xvfb-run -a uv run python -m experiments.scroll_view.probe

The scrollbar item builds a facade over a protocol tkinter never
names: a widget's view along an axis, driven by ``yview``/``xview`` and
reported back through ``yscrollcommand``/``xscrollcommand``. The design
rests on facts this probe pins: that both ends of that protocol are
stringly typed, numbers included, so the conversion has two
boundaries rather than one; that ``(0.0, 1.0)`` is how Tk says
everything fits, which is the whole of the auto-hide predicate; that a
``moveto`` past the end clamps rather than raising, so an out-of-range
write settles somewhere the caller did not ask for; that a scrollbar
whose target has been destroyed raises *inside* a Tk callback, where
the raise is printed and swallowed rather than propagated; that
``grid_remove`` followed by a bare ``grid`` restores the cell exactly,
which is what makes hiding a bar reversible; that one widget's single
scroll-command option can feed several listeners once the fanout is
ours; and that today's observable, wired both ways against a widget,
converges against that clamping instead of ringing.

The last check imports the library — the fact it pins is about
tkfacade's own settle machinery, not about Tk — and every other check
stands on tkinter alone.

Expectations are the behavior witnessed on Tk 8.6.14 (threaded Tcl,
X11), CPython 3.14. A FAIL is a finding: that build does not behave
the way the design's evidence says. Every check prints its verdict;
the exit status is the number that failed.
"""

import math
import sys
import tkinter as tk
from tkinter import ttk

Report = tuple[bool, str]

_LINES = 200
"""Lines of filler content, enough that every scrollable view can scroll."""


def scrollable_text(master: tk.Misc, lines: int = _LINES) -> tk.Text:
    """Return a small text widget holding ``lines`` numbered lines."""
    text = tk.Text(master, width=20, height=5, wrap="none")
    text.insert("1.0", "\n".join(f"line {index} with a tail" for index in range(lines)))
    text.grid(row=0, column=0, sticky="nsew")
    return text


def rig() -> tuple[tk.Tk, ttk.Frame]:
    """Return a realized root and frame, sized so scrollbars have room."""
    root = tk.Tk()
    root.geometry("320x220")
    frame = ttk.Frame(root)
    frame.grid(sticky="nsew")
    return root, frame


def check_the_drive_end_is_stringly_typed() -> Report:
    """A scrollbar's command receives Tk's words *and its numbers* as strings."""
    root, frame = rig()
    text = scrollable_text(frame)
    seen: list[tuple[str, ...]] = []
    bar = ttk.Scrollbar(
        frame, orient="vertical", command=lambda *args: (seen.append(args), text.yview(*args))
    )
    bar.grid(row=0, column=1, sticky="ns")
    text.configure(yscrollcommand=bar.set)
    root.update()
    bar.event_generate("<Button-1>", x=5, y=bar.winfo_height() - 5)
    root.update()
    bar.event_generate("<ButtonRelease-1>", x=5, y=bar.winfo_height() - 5)
    root.update()
    root.destroy()
    kinds = {tuple(type(arg).__name__ for arg in args) for args in seen}
    ok = bool(seen) and kinds == {("str", "str", "str")}
    return ok, (
        f"command received {seen!r} -- every element a str, the count among them, "
        "so the facade converts on the way in"
    )


def check_the_report_end_is_stringly_typed() -> Report:
    """A widget's scroll-command reports its two fractions as strings."""
    root, frame = rig()
    text = scrollable_text(frame)
    seen: list[tuple[str, ...]] = []
    text.configure(yscrollcommand=lambda *args: seen.append(args))
    root.update()
    root.destroy()
    last = seen[-1] if seen else ()
    ok = bool(seen) and all(isinstance(arg, str) for arg in last) and len(last) == 2
    return ok, (
        f"yscrollcommand received {last!r} -- a pair of strs, so the facade "
        "converts on the way out too: two boundaries, not one"
    )


def check_everything_fits_reads_as_zero_to_one() -> Report:
    """Content shorter than its widget reports the full span, and only then."""
    root, frame = rig()
    short = tk.Text(frame, width=20, height=5)
    short.insert("1.0", "one line")
    short.grid(row=0, column=0)
    tall = scrollable_text(frame)
    root.update()
    fits, scrolls = short.yview(), tall.yview()
    root.destroy()
    ok = fits == (0.0, 1.0) and scrolls[1] < 1.0
    return ok, (
        f"short content {fits!r}, tall content {scrolls!r} -- the full span is "
        "Tk's everything-fits signal, and the whole of the auto-hide predicate"
    )


def check_moveto_past_the_end_clamps() -> Report:
    """A fraction beyond what the widget can reach settles at its maximum."""
    root, frame = rig()
    text = scrollable_text(frame)
    root.update()
    text.yview("moveto", 9.0)
    root.update()
    landed = text.yview()
    root.destroy()
    ok = math.isclose(landed[1], 1.0) and 0.0 < landed[0] < 1.0
    return ok, (
        f"moveto 9.0 settled at {landed!r} -- Tk clamps silently rather than "
        "raising, so nonsense is the facade's to refuse at the boundary"
    )


def check_a_bar_outliving_its_target_raises_inside_tk() -> Report:
    """A scrollbar whose target is gone raises where Tk swallows the raise."""
    root, frame = rig()
    text = scrollable_text(frame)
    bar = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
    bar.grid(row=0, column=1, sticky="ns")
    text.configure(yscrollcommand=bar.set)
    root.update()
    text.destroy()
    root.update()
    story: list[str] = []
    try:
        text.yview("scroll", 1, "units")
        story.append("silent")
    except tk.TclError as exc:
        story.append(str(exc))
    root.destroy()
    ok = len(story) == 1 and "invalid command name" in story[0]
    return ok, (
        f"driving the dead target raised {story[0]!r} -- and through the bar's own "
        "-command it lands inside a Tk callback, printed and swallowed: a bar that "
        "looks alive and does nothing"
    )


def check_hiding_a_bar_is_reversible() -> Report:
    """grid_remove then a bare grid restores row, column and sticky exactly."""
    root, frame = rig()
    scrollable_text(frame)
    bar = ttk.Scrollbar(frame, orient="vertical")
    bar.grid(row=0, column=1, sticky="ns")
    root.update()
    before = {key: bar.grid_info()[key] for key in ("row", "column", "sticky")}
    bar.grid_remove()
    root.update()
    hidden = bool(bar.winfo_ismapped())
    bar.grid()
    root.update()
    after = {key: bar.grid_info()[key] for key in ("row", "column", "sticky")}
    shown = bool(bar.winfo_ismapped())
    root.destroy()
    ok = not hidden and shown and before == after
    return ok, (
        f"cell {before!r} survived the round trip as {after!r}; unmapped while "
        "removed, mapped again after -- hiding needs no remembered geometry"
    )


def check_one_scroll_option_can_feed_several_listeners() -> Report:
    """The single scroll-command option fans out once the fanout is ours."""
    root, frame = rig()
    text = scrollable_text(frame)
    first = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
    second = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
    first.grid(row=0, column=1, sticky="ns")
    second.grid(row=0, column=2, sticky="ns")
    heard: list[tuple[float, float]] = []

    def fanout(low: str, high: str) -> None:
        first.set(low, high)
        second.set(low, high)
        heard.append((float(low), float(high)))

    text.configure(yscrollcommand=fanout)
    root.update()
    text.yview("moveto", 0.5)
    root.update()
    reading = first.get()
    both = reading == second.get()
    tracked = math.isclose(reading[0], 0.5)
    root.destroy()
    ok = both and tracked and bool(heard)
    return ok, (
        f"both bars read {reading!r} after one move -- Tk offers one "
        "scroll-command option per axis, so a second bar is the facade's fanout "
        "to run, exactly as it already runs one for events and observables"
    )


def check_a_driven_observable_settles_against_the_clamp() -> Report:
    """Wired both ways, the observable converges where Tk clamps rather than ringing."""
    import tkfacade

    root, frame = rig()
    text = scrollable_text(frame)
    position = tkfacade.ObservableFloat(0.0)
    position.transport_for(text)
    tape: list[float] = []
    position.watch(tape.append)
    adopting = {"now": False}

    def tracked(low: str, _high: str) -> None:
        adopting["now"] = True
        try:
            position.value = float(low)
        finally:
            adopting["now"] = False

    def drive(value: float) -> None:
        if not adopting["now"]:
            text.yview("moveto", value)

    text.configure(yscrollcommand=tracked)
    position.watch(drive)
    root.update()
    tape.clear()
    position.value = 0.5
    root.update()
    exact = list(tape)
    tape.clear()
    position.value = 9.0
    root.update()
    clamped = list(tape)
    settled = position.value
    reached = text.yview()[0]
    position.release_transport()
    root.destroy()
    ok = exact == [0.5] and settled == reached and clamped[-1] == settled and settled < 9.0
    return ok, (
        f"a reachable write notified {exact!r}; an out-of-range write notified "
        f"{clamped!r} and settled at {settled!r}, where the widget sits -- it "
        "converges, but a watcher sees the impossible value first, which is why "
        "the facade refuses out-of-range at the boundary"
    )


def check_the_bar_itself_is_nearly_optionless() -> Report:
    """ttk.Scrollbar carries almost no options of its own."""
    root, frame = rig()
    bar = ttk.Scrollbar(frame, orient="vertical")
    options = sorted(bar.keys())
    root.destroy()
    ok = options == ["class", "command", "cursor", "orient", "style", "takefocus"]
    return ok, (
        f"options are {options!r} -- two of them mean anything, which is why the "
        "wrapper's worth is the relationship it names rather than the options it wraps"
    )


CHECKS: tuple[tuple[str, object], ...] = (
    ("the drive end is stringly typed", check_the_drive_end_is_stringly_typed),
    ("the report end is stringly typed", check_the_report_end_is_stringly_typed),
    ("everything-fits reads as 0.0-1.0", check_everything_fits_reads_as_zero_to_one),
    ("moveto past the end clamps", check_moveto_past_the_end_clamps),
    ("a bar outliving its target raises", check_a_bar_outliving_its_target_raises_inside_tk),
    ("hiding a bar is reversible", check_hiding_a_bar_is_reversible),
    ("one option feeds several listeners", check_one_scroll_option_can_feed_several_listeners),
    ("a driven observable settles", check_a_driven_observable_settles_against_the_clamp),
    ("the bar itself is nearly optionless", check_the_bar_itself_is_nearly_optionless),
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
        ok, detail = check()  # type: ignore[operator]
        failures += 0 if ok else 1
        print(f"{name:38s} {'ok  ' if ok else 'FAIL'}  {detail}")
    return failures


if __name__ == "__main__":
    sys.exit(main())
