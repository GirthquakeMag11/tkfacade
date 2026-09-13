"""Witness the Tk facts the Dialog foundation turns on, one check per claim.

Run with::

    xvfb-run -a uv run python -m experiments.modality_probe.probe

The dialog phase is ruled to open with a
`Dialog` base class: an owned, encapsulated window, a future carrying
the result, a synchronous calling surface beside an async one. Every
mechanism under that shape is modality machinery the library has never
touched — no `grab_set`, `wait_window`, or `transient` anywhere in
`src/` before this phase — so each check here pins one fact the
design must stand on: whether Tk's wait calls genuinely block their
caller while the event loop keeps pumping (the nested-loop mechanic a
sync dialog needs); how two nested waits unwind (the re-entrancy
stance); what a grab confines and what still reaches the root's
all-bindings (the input observer's stratum); whether a worker
thread's marshalled completions land while the mainloop sits in a
wait (the async core's crossing during a sync dialog); whether Tk's
own file and color dialogs are Tk-drawn under X11, open headless,
pump their caller's events while posted, and how they are honestly
dismissed (the facts the file and color cases need whatever their
rulings say); what `transient`, focus, and a grab's teardown look
like with no window manager (the suite's limits); and what a dialog
window's destruction means to a parked caller — cancellation, Tk's
own dialog completing its wait on destroy.

Real device injection comes from ``xdotool`` (XTEST) where pointer
routing matters, since a grab redirects real pointer events rather
than generated ones. Nothing here imports tkfacade.

The expectations coded below are the behaviour witnessed on Tk 8.6,
x11, under Xvfb with no window manager — see the README. A failure is
a finding, not necessarily a fault; the exit status is the number that
failed.
"""

import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import colorchooser, filedialog

Report = tuple[bool, str]


def xdo(*args: str) -> None:
    """Run one xdotool command and give the server a moment to deliver."""
    subprocess.run(["xdotool", *args], check=True, capture_output=True)


class Bench:
    """A mapped root with a pump, placed for coordinate-addressed clicks."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.geometry("300x200+10+10")
        self.root.update()

    def pump(self, seconds: float) -> None:
        """Process events for ``seconds`` of wall time."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)

    def close(self) -> None:
        self.root.destroy()


def check_wait_window_blocks_while_events_pump() -> Report:
    """``wait_window`` parks its caller in a nested loop that still pumps."""
    bench = Bench()
    marks: list[str] = []
    gate = tk.Toplevel(bench.root)
    gate.geometry("120x80+50+50")
    bench.root.bind("<<Probe>>", lambda e: marks.append("binding"), add="+")
    bench.root.after(150, lambda: (marks.append("after"), bench.root.event_generate("<<Probe>>")))
    bench.root.after(300, gate.destroy)
    marks.append("before")
    bench.root.wait_window(gate)
    marks.append("resumed")
    bench.close()
    ok = marks == ["before", "after", "binding", "resumed"]
    return ok, f"marks in order {marks}"


def check_nested_waits_unwind_last_in_first_out() -> Report:
    """An outer wait cannot return while an inner wait is still parked."""
    bench = Bench()
    order: list[str] = []
    outer = tk.IntVar(master=bench.root)
    inner = tk.IntVar(master=bench.root)

    def start_inner() -> None:
        order.append("inner-start")
        bench.root.wait_variable(inner)
        order.append("inner-done")

    bench.root.after(100, start_inner)
    bench.root.after(200, lambda: (order.append("outer-set"), outer.set(1)))
    bench.root.after(300, lambda: (order.append("inner-set"), inner.set(1)))
    order.append("outer-start")
    bench.root.wait_variable(outer)
    order.append("outer-done")
    bench.close()
    expected = ["outer-start", "inner-start", "outer-set", "inner-set", "inner-done", "outer-done"]
    ok = order == expected
    return ok, f"unwind order {order}"


def check_grab_confines_clicks_and_the_allbinding_sees_keys() -> Report:
    """A grab starves other windows of real clicks; ``bind_all`` still hears keys."""
    bench = Bench()
    other = tk.Toplevel(bench.root)
    other.geometry("140x100+340+10")
    other_hits: list[int] = []
    other.bind("<ButtonPress>", lambda e: other_hits.append(e.num), add="+")
    all_keys: list[str] = []
    bench.root.bind_all("<KeyPress>", lambda e: all_keys.append(e.keysym), add="+")
    dialogish = tk.Toplevel(bench.root)
    dialogish.geometry("120x80+80+80")
    dialog_hits: list[int] = []
    dialogish.bind("<ButtonPress>", lambda e: dialog_hits.append(e.num), add="+")
    bench.root.update()
    dialogish.grab_set()
    bench.root.update()

    xdo("mousemove", "--sync", "400", "50")  # inside `other`
    xdo("click", "1")
    bench.pump(0.2)
    xdo("mousemove", "--sync", "130", "110")  # inside the grab holder
    xdo("click", "1")
    bench.pump(0.2)
    xdo("windowfocus", "--sync", str(dialogish.winfo_id()))
    bench.root.update()
    xdo("key", "a")
    bench.pump(0.2)

    bench.close()
    # the click aimed at `other` is not dropped: Tk redirects it to the
    # grab holder, which therefore hears both clicks
    ok = not other_hits and dialog_hits == [1, 1] and "a" in all_keys
    return ok, (
        f"other window saw {other_hits or 'nothing'}, grab holder saw {dialog_hits} "
        f"(the foreign click redirected to it), all-binding keys {all_keys}"
    )


def check_a_worker_threads_marshalled_completion_lands_mid_wait() -> Report:
    """A thread's ``after(0, ...)`` crossing lands while ``wait_window`` parks.

    The scenario is a real app's: the mainloop is running, a command
    callback opens a sync dialog and parks in ``wait_window``, and a
    worker thread (the async core's seat) marshals the completion with
    the library's own crossing, ``after(0, ...)`` from off-thread. An
    ``update()``-pumped bench cannot ask this — tkinter's thread wall
    raises ``RuntimeError: main thread is not in main loop`` there, by
    design — so this check runs a genuine ``mainloop`` and drives
    everything from callbacks, with a main-side watchdog so a refused
    crossing is a finding rather than a hang.
    """
    bench = Bench()
    marks: list[str] = []
    gate = tk.Toplevel(bench.root)
    gate.geometry("120x80+50+50")

    def work() -> None:
        time.sleep(0.15)
        marks.append("thread-ran")
        try:
            bench.root.after(0, lambda: (marks.append("marshalled"), gate.destroy()))
        except RuntimeError as error:
            marks.append(f"crossing refused: {error}")

    def open_dialog() -> None:
        threading.Thread(target=work, daemon=True).start()
        marks.append("before")
        bench.root.wait_window(gate)
        marks.append("resumed")
        bench.root.quit()

    def watchdog() -> None:
        if gate.winfo_exists():
            marks.append("watchdog-freed")
            gate.destroy()

    bench.root.after(50, open_dialog)
    bench.root.after(2000, watchdog)
    bench.root.mainloop()
    bench.close()
    ok = marks == ["before", "thread-ran", "marshalled", "resumed"]
    return ok, f"marks in order {marks}"


def _child_paths(bench: Bench) -> set[str]:
    """The root's child window paths, straight from Tcl.

    Raw ``winfo children`` through ``splitlist`` rather than tkinter's
    wrapper: the Tk-drawn dialogs are created by Tcl library code, so
    tkinter has no widget object for them and ``winfo_children``
    cannot answer them.
    """
    listed = bench.root.tk.call("winfo", "children", ".")
    return {str(path) for path in bench.root.tk.splitlist(listed)}


def check_the_file_dialog_is_tk_drawn_and_pumps() -> Report:
    """``askopenfilename`` is a Tk window headless, pumps, and its cancel proc ends it.

    Also witnessed: the dialog window *persists* after the call
    returns — Tk keeps ``.__tk_filedialog`` around, withdrawn, for
    reuse — so "no foreign toplevels" is not a truth a suite can
    assert once any file dialog has been shown.
    """
    bench = Bench()
    marks: list[str] = []
    ours = _child_paths(bench)
    facts: dict[str, object] = {}

    def dismiss() -> None:
        foreign = sorted(_child_paths(bench) - ours)
        facts["windows"] = foreign
        facts["classes"] = [str(bench.root.tk.call("winfo", "class", path)) for path in foreign]
        marks.append("pumped")
        bench.root.tk.call("::tk::dialog::file::CancelCmd", ".__tk_filedialog")

    bench.root.after(300, dismiss)
    try:
        answer: object = filedialog.askopenfilename(parent=bench.root)
    except tk.TclError as error:
        answer = f"raised TclError: {error}"
    persisted = ".__tk_filedialog" in _child_paths(bench)
    bench.close()
    ok = facts.get("classes") == ["TkFDialog"] and marks == ["pumped"] and not answer and persisted
    return ok, (
        f"dialog {facts.get('windows')} class {facts.get('classes')}, marks {marks}, "
        f"answer {answer!r}, window persists after return: {persisted}"
    )


def check_the_color_chooser_is_tk_drawn_and_pumps() -> Report:
    """``askcolor`` is a Tk window headless, pumps, and its cancel proc ends it."""
    bench = Bench()
    marks: list[str] = []
    ours = _child_paths(bench)
    facts: dict[str, object] = {}

    def dismiss() -> None:
        foreign = sorted(_child_paths(bench) - ours)
        facts["classes"] = [str(bench.root.tk.call("winfo", "class", path)) for path in foreign]
        marks.append("pumped")
        bench.root.tk.call("::tk::dialog::color::CancelCmd", ".__tk__color")

    bench.root.after(300, dismiss)
    try:
        answer: object = colorchooser.askcolor(parent=bench.root)
    except tk.TclError as error:
        answer = f"raised TclError: {error}"
    bench.close()
    ok = (
        facts.get("classes") == ["TkColorDialog"]
        and marks == ["pumped"]
        and answer
        == (
            None,
            None,
        )
    )
    return ok, f"class {facts.get('classes')}, marks {marks}, answer {answer!r}"


def check_transient_focus_and_grab_teardown_without_a_wm() -> Report:
    """``transient`` reads back, focus lands, and a grab dies with its window."""
    bench = Bench()
    top = tk.Toplevel(bench.root)
    top.geometry("120x80+50+50")
    top.transient(bench.root)
    bench.root.update()
    transient_read = str(top.wm_transient())
    xdo("windowfocus", "--sync", str(top.winfo_id()))
    top.focus_force()
    bench.root.update()
    focused = bench.root.focus_get()
    top.grab_set()
    bench.root.update()
    held = bench.root.grab_current()
    top.destroy()
    bench.root.update()
    released = bench.root.grab_current()
    bench.close()
    ok = transient_read == str(bench.root) and focused is top and held is top and released is None
    return ok, (
        f"transient reads {transient_read!r}, focus landed on {focused}, "
        f"grab held by {held}, after destroy {released}"
    )


def check_destroying_a_waiting_dialog_cancels_it() -> Report:
    """Destroying a posted dialog's window reads as cancel, not a parked caller.

    First witnessed as the opposite — an instrument artifact: a debug
    harness passed Tcl tuple reprs as window paths, its destroy never
    landed, and the still-posted dialog read as "destroy does not
    release the vwait". Re-verified with the destroy actually
    landing: Tk's file dialog completes its wait on destruction and
    the caller returns promptly with the empty answer, so a `Dialog`
    torn down abruptly resolves rather than parking its caller —
    provided the design keeps the same property, a completion bound
    to destruction itself.
    """
    bench = Bench()
    marks: list[str] = []

    def sabotage() -> None:
        bench.root.tk.call("destroy", ".__tk_filedialog")
        marks.append("destroyed")

    bench.root.after(300, sabotage)
    try:
        answer: object = filedialog.askopenfilename(parent=bench.root)
    except tk.TclError as error:
        answer = f"raised TclError: {error}"
    marks.append("returned")
    bench.close()
    ok = marks == ["destroyed", "returned"] and not answer
    return ok, f"marks in order {marks}, answer {answer!r}"


CHECKS = (
    check_wait_window_blocks_while_events_pump,
    check_nested_waits_unwind_last_in_first_out,
    check_grab_confines_clicks_and_the_allbinding_sees_keys,
    check_a_worker_threads_marshalled_completion_lands_mid_wait,
    check_the_file_dialog_is_tk_drawn_and_pumps,
    check_the_color_chooser_is_tk_drawn_and_pumps,
    check_transient_focus_and_grab_teardown_without_a_wm,
    check_destroying_a_waiting_dialog_cancels_it,
)


def main() -> int:
    """Run every check; the exit status is the number that failed."""
    if shutil.which("xdotool") is None:
        print("xdotool is required for device-level injection")
        return 1
    failures = 0
    for check in CHECKS:
        try:
            ok, detail = check()
        except Exception as error:
            ok, detail = False, f"raised {type(error).__name__}: {error}"
        verdict = "pass" if ok else "FAIL"
        print(f"{verdict}  {check.__name__}: {detail}")
        failures += 0 if ok else 1
    return failures


if __name__ == "__main__":
    sys.exit(main())
