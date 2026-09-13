"""Witness what Tk's scroll machinery couples, one check per claim.

Run with::

    xvfb-run -a uv run python -m experiments.scroll_probe.probe

The scrollbar-placement item is paused on a
prior question: where does scrollbar management belong — the spec as it
stands, a container facade in the menubar's mold, a standalone bar, or
a viewport that scrolls anything. Each check here pins one fact that
choice turns on: what the protocol actually couples (callables or
widgets), who may own whom across lifetimes, which widgets speak it at
all, what the canvas-window viewport mechanism really does, and how
the wheel reaches a widget with no bar in sight. Nothing here imports
tkfacade; `facade.py` beside this measures the library against these
facts. `experiments/scroll_view/` (2026-08-21) holds the protocol
facts already witnessed — stringly ends, one command per axis, clamp
and quantise, the everything-fits pair — and none are re-measured.

The expectations coded below are the behaviour witnessed on Tk 8.6.14,
x11, under Xvfb with no window manager — see the README. A failure is
a finding, not necessarily a fault: the wheel is a per-platform story,
so several of these should be expected to fail off x11, and that
failure is the measurement. Every check prints its verdict; the exit
status is the number that failed.
"""

import sys
import tkinter as tk
from tkinter import ttk

Report = tuple[bool, str]

_LINES = 200
"""Lines of filler, enough that every scrollable view can scroll."""


def bench(geometry: str = "320x220") -> tk.Tk:
    """Return a mapped root of a known size."""
    root = tk.Tk()
    root.geometry(geometry)
    root.update()
    return root


def filled_text(master: tk.Misc, lines: int = _LINES) -> tk.Text:
    """Return a small text widget holding ``lines`` numbered lines."""
    text = tk.Text(master, width=20, height=5, wrap="none")
    text.insert("1.0", "\n".join(f"line {index} with a tail" for index in range(lines)))
    return text


def stacked_labels(master: tk.Misc, count: int, start: int = 0) -> None:
    """Grid ``count`` labels into ``master``, one per row, from ``start``."""
    for index in range(start, start + count):
        tk.Label(master, text=f"row {index}").grid(row=index, column=0)


def drive(root: tk.Tk, bar: ttk.Scrollbar, *words: str) -> None:
    """Invoke ``bar``'s command the way a drag would, in Tk's own words."""
    root.tk.call(str(bar.cget("command")), *words)


# --- wiring and ownership ----------------------------------------------------


def check_a_bar_drives_across_containers() -> Report:
    """The protocol couples callables, so parentage never enters into it."""
    root = bench()
    inner = ttk.Frame(ttk.Frame(root))
    inner.master.grid()
    inner.grid()
    text = filled_text(inner)
    text.grid()
    bar = ttk.Scrollbar(root, orient="vertical", command=text.yview)
    bar.grid(row=0, column=1)
    text.configure(yscrollcommand=bar.set)
    root.update()
    drive(root, bar, "moveto", "0.5")
    root.update()
    driven = abs(text.yview()[0] - 0.5) < 0.05
    tracked = abs(bar.get()[0] - text.yview()[0]) < 0.001
    root.destroy()
    return (driven and tracked), f"driven to {0.5}={driven}, bar tracks={tracked}"


def check_one_bar_drives_two_targets() -> Report:
    """The drive end fans out freely, since the command is any callable."""
    root = bench()
    first, second = filled_text(root), filled_text(root)
    first.grid(row=0, column=0)
    second.grid(row=0, column=1)

    def both(*words: str) -> None:
        first.yview(*words)
        second.yview(*words)

    bar = ttk.Scrollbar(root, orient="vertical", command=both)
    bar.grid(row=0, column=2)
    root.update()
    drive(root, bar, "moveto", "0.25")
    root.update()
    positions = (first.yview()[0], second.yview()[0])
    together = abs(positions[0] - positions[1]) < 0.001 and positions[0] > 0.0
    root.destroy()
    return together, f"positions {positions}"


def check_a_target_outliving_its_bar_reports_into_a_swallowed_raise() -> Report:
    """A destroyed bar's ``set`` raises on the next report, and Tk eats it.

    The converse of scroll_view's bar-outlives-target check: here the
    widget keeps calling a `-yscrollcommand` whose bar is gone.
    """
    root = bench()
    heard: list[str] = []
    root.report_callback_exception = lambda kind, error, _tb: heard.append(  # type: ignore[method-assign]
        f"{kind.__name__}: {error}"
    )
    text = filled_text(root)
    text.grid()
    bar = ttk.Scrollbar(root, orient="vertical", command=text.yview)
    bar.grid(row=0, column=1)
    text.configure(yscrollcommand=bar.set)
    root.update()
    bar.destroy()
    text.yview("moveto", "0.5")
    root.update()
    swallowed = bool(heard) and "invalid command name" in heard[0]
    still_running = bool(text.winfo_exists())
    root.destroy()
    return (swallowed and still_running), f"heard {heard[:1]}, widget lives={still_running}"


# --- the scrollable population -----------------------------------------------


def check_which_widgets_speak_the_protocol_and_on_which_axes() -> Report:
    """Text, Listbox, Treeview and Canvas speak both axes; the entries x alone."""
    root = bench()

    def axes(widget: tk.Misc) -> str:
        spoken = ""
        for letter, option in (("x", "xscrollcommand"), ("y", "yscrollcommand")):
            try:
                widget.configure(**{option: lambda *_words: None})  # type: ignore[call-arg]
                spoken += letter
            except tk.TclError:
                pass
        return spoken

    roster = {
        "Text": axes(tk.Text(root)),
        "Listbox": axes(tk.Listbox(root)),
        "Treeview": axes(ttk.Treeview(root)),
        "Canvas": axes(tk.Canvas(root)),
        "Entry": axes(tk.Entry(root)),
        "TEntry": axes(ttk.Entry(root)),
        "Spinbox": axes(tk.Spinbox(root)),
        "TCombobox": axes(ttk.Combobox(root)),
    }
    expected = {
        "Text": "xy",
        "Listbox": "xy",
        "Treeview": "xy",
        "Canvas": "xy",
        "Entry": "x",
        "TEntry": "x",
        "Spinbox": "x",
        "TCombobox": "x",
    }
    root.destroy()
    return roster == expected, f"{roster}"


# --- the viewport mechanism --------------------------------------------------


def check_an_embedded_frame_scrolls_once_a_region_is_declared() -> Report:
    """``create_window`` plus a scrollregion makes a frame's content scroll."""
    root = bench()
    canvas = tk.Canvas(root, width=200, height=100)
    canvas.grid()
    frame = ttk.Frame(canvas)
    stacked_labels(frame, 30)
    canvas.create_window((0, 0), window=frame, anchor="nw")
    root.update()
    canvas.configure(scrollregion=canvas.bbox("all"))
    before = canvas.yview()
    canvas.yview("moveto", "0.5")
    root.update()
    after = canvas.yview()
    scrolls = before[1] - before[0] < 1.0 and abs(after[0] - 0.5) < 0.05
    moved = canvas.canvasy(0) > 0
    root.destroy()
    return (scrolls and moved), f"span {before}, at {after[0]:.2f}, content moved={moved}"


def check_without_a_region_the_canvas_reports_everything_fits() -> Report:
    """No scrollregion means ``(0.0, 1.0)`` however tall the content is.

    The everything-fits pair is the whole auto-hide predicate
    (`hazards/tkinter.md`, *Scrolling*), so on a bare canvas that predicate
    lies for exactly the widget a viewport is built on.
    """
    root = bench()
    canvas = tk.Canvas(root, width=200, height=100)
    canvas.grid()
    frame = ttk.Frame(canvas)
    stacked_labels(frame, 30)
    canvas.create_window((0, 0), window=frame, anchor="nw")
    root.update()
    span = canvas.yview()
    lies = span == (0.0, 1.0)
    tall = frame.winfo_height() > canvas.winfo_height()
    root.destroy()
    return (lies and tall), f"reports {span} over content taller={tall}"


def check_a_configure_synced_region_stays_truthful_through_growth() -> Report:
    """Re-declaring the region on the frame's ``<Configure>`` tracks growth."""
    root = bench()
    canvas = tk.Canvas(root, width=200, height=100)
    canvas.grid()
    frame = ttk.Frame(canvas)
    frame.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
    stacked_labels(frame, 10)
    canvas.create_window((0, 0), window=frame, anchor="nw")
    root.update()
    before = canvas.yview()
    stacked_labels(frame, 30, start=10)
    root.update()
    after = canvas.yview()
    tightened = after[1] - after[0] < before[1] - before[0] < 1.0
    root.destroy()
    return tightened, f"span {before} then {after}"


def check_the_highlight_ring_skews_the_viewport_off_zero() -> Report:
    """A default canvas never reports exactly 0.0 at its top.

    The 1px highlight ring sits inside the scrolled coordinate space,
    so the resting view starts fractionally past zero — an "at the
    top" predicate comparing against 0.0 answers False forever.
    Zeroing ``highlightthickness`` restores the exact edge.
    """
    root = bench()
    spans = []
    for extra in ({}, {"highlightthickness": 0}):
        canvas = tk.Canvas(root, width=200, height=100, **extra)  # type: ignore[arg-type]
        canvas.grid()
        frame = ttk.Frame(canvas)
        stacked_labels(frame, 30)
        canvas.create_window((0, 0), window=frame, anchor="nw")
        root.update()
        canvas.configure(scrollregion=canvas.bbox("all"))
        root.update()
        spans.append(canvas.yview()[0])
    root.destroy()
    skewed, exact = spans
    # a fraction is never below 0.0, so not-above is the exact edge
    at_edge = not exact > 0.0
    return (skewed > 0.0 and at_edge), f"default rests at {skewed:.5f}, ringless at {exact}"


def check_events_inside_the_viewport_bypass_the_canvas() -> Report:
    """A wheel turn over an embedded child never reaches the canvas's binding.

    The child's bindtags are itself, its class, the toplevel and
    ``all`` — the canvas is not among them, so a canvas-level wheel
    binding hears nothing over its own content. The toplevel does.
    """
    root = bench()
    canvas = tk.Canvas(root, width=200, height=100)
    canvas.grid()
    frame = ttk.Frame(canvas)
    label = tk.Label(frame, text="content")
    label.grid()
    canvas.create_window((0, 0), window=frame, anchor="nw")
    root.update()
    heard: list[str] = []
    canvas.bind("<Button-4>", lambda _e: heard.append("canvas"))
    root.bind("<Button-4>", lambda _e: heard.append("toplevel"))
    label.event_generate("<Button-4>")
    root.update()
    root.destroy()
    return heard == ["toplevel"], f"heard {heard}"


# --- the wheel ---------------------------------------------------------------


def check_a_wheel_turn_is_delivered_per_widget_not_per_focus() -> Report:
    """Wheel buttons land where they are aimed; focus attracts nothing."""
    root = bench()
    first, second = filled_text(root), filled_text(root)
    first.grid(row=0, column=0)
    second.grid(row=0, column=1)
    root.update()
    first.focus_force()
    root.update()
    heard: list[str] = []
    first.bind("<Button-4>", lambda _e: heard.append("focused"))
    second.bind("<Button-4>", lambda _e: heard.append("aimed"))
    second.event_generate("<Button-4>")
    root.update()
    pointed = str(root.winfo_containing(*_center(second))) == str(second)
    root.destroy()
    return (heard == ["aimed"] and pointed), f"heard {heard}, containing answers aimed={pointed}"


def check_mousewheel_binds_on_x11_and_carries_its_delta() -> Report:
    """``<MouseWheel>`` is bindable here and a generated one delivers delta.

    Real x11 devices deliver `Button-4/5` instead — the split the
    library's `Wheel` spec documents — but the sequence itself is
    legal, so portable code binding both routes raises nowhere.
    """
    root = bench()
    deltas: list[int] = []
    text = filled_text(root)
    text.grid()
    text.bind("<MouseWheel>", lambda event: deltas.append(event.delta))
    root.update()
    text.event_generate("<MouseWheel>", delta=-120)
    root.update()
    root.destroy()
    return deltas == [-120], f"deltas {deltas}"


def check_which_classes_scroll_on_wheel_with_no_bar_at_all() -> Report:
    """Text, Listbox, Treeview and the combobox ship wheel class bindings; Canvas none."""
    root = bench()
    roster = {
        name: bool(str(root.bind_class(name, "<Button-4>")))
        for name in ("Text", "Listbox", "Treeview", "TCombobox", "Canvas", "Entry")
    }
    expected = {
        "Text": True,
        "Listbox": True,
        "Treeview": True,
        "TCombobox": True,
        "Canvas": False,
        "Entry": False,
    }
    root.destroy()
    return roster == expected, f"{roster}"


def _center(widget: tk.Misc) -> tuple[int, int]:
    """The widget's centre in root coordinates, for pointer queries."""
    return (
        widget.winfo_rootx() + widget.winfo_width() // 2,
        widget.winfo_rooty() + widget.winfo_height() // 2,
    )


CHECKS = (
    ("a bar drives across containers", check_a_bar_drives_across_containers),
    ("one bar drives two targets", check_one_bar_drives_two_targets),
    (
        "a target outliving its bar is swallowed",
        check_a_target_outliving_its_bar_reports_into_a_swallowed_raise,
    ),
    (
        "who speaks the protocol, and which axes",
        check_which_widgets_speak_the_protocol_and_on_which_axes,
    ),
    (
        "an embedded frame scrolls with a region",
        check_an_embedded_frame_scrolls_once_a_region_is_declared,
    ),
    (
        "no region reads as everything-fits",
        check_without_a_region_the_canvas_reports_everything_fits,
    ),
    (
        "a synced region survives growth",
        check_a_configure_synced_region_stays_truthful_through_growth,
    ),
    ("the highlight ring skews the edge", check_the_highlight_ring_skews_the_viewport_off_zero),
    ("viewport events bypass the canvas", check_events_inside_the_viewport_bypass_the_canvas),
    (
        "the wheel is per-widget, not per-focus",
        check_a_wheel_turn_is_delivered_per_widget_not_per_focus,
    ),
    ("MouseWheel binds and carries delta", check_mousewheel_binds_on_x11_and_carries_its_delta),
    ("who scrolls on wheel with no bar", check_which_classes_scroll_on_wheel_with_no_bar_at_all),
)


def main() -> int:
    """Run every check, print each verdict, and return the failure count."""
    probe = tk.Tk()
    print(
        f"Tk {probe.tk.call('info', 'patchlevel')}, "
        f"windowingsystem {probe.tk.call('tk', 'windowingsystem')}, "
        f"{sys.platform}"
    )
    probe.destroy()
    failures = 0
    for name, check in CHECKS:
        try:
            ok, detail = check()
        except Exception as error:  # a raise is itself a finding about this build
            ok, detail = False, f"raised {type(error).__name__}: {error}"
        failures += 0 if ok else 1
        print(f"{name:42s} {'ok  ' if ok else 'FAIL'}  {detail}")
    return failures


if __name__ == "__main__":
    sys.exit(main())
