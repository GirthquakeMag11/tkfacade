"""Re-create the tkinter hazards that carried no other witness, one check per claim.

Run with::

    xvfb-run -a uv run python -m experiments.hazards_probe.probe

A few entries in ``hazards/tkinter.md`` were written before the repo kept a
re-runnable probe for the behaviour they describe. Each check here tries to
make Tk do exactly what one such entry says it does, so the entry can be
recreated rather than merely asserted. A check that passes means the entry
holds on this build; a check that fails is a finding — the entry either never
held or has gone stale, and is a candidate for removal. Nothing here imports
tkfacade, and every check prints its verdict; the exit status is the number
that failed.
"""

import sys
import tkinter as tk
from tkinter import ttk

Report = tuple[bool, str]


def bench() -> tk.Tk:
    """Return a mapped root ready for widget and geometry reads."""
    root = tk.Tk()
    root.update()
    return root


def check_a_path_is_reissued_and_counters_restart() -> Report:
    """A `name=` path is reissued to a successor; generated names restart per master."""
    root = bench()

    first = ttk.Frame(root, name="fixed")
    first_path = str(first)
    first.destroy()
    second = ttk.Frame(root, name="fixed")
    reissued = str(second) == first_path

    generated_first = ttk.Frame(root)
    generated_second = ttk.Frame(root)
    distinct = str(generated_first) != str(generated_second)

    inner = ttk.Frame(root)
    child_name = ttk.Frame(inner).winfo_name()
    inner.destroy()
    inner_again = ttk.Frame(root)
    child_again = ttk.Frame(inner_again).winfo_name()
    restarted = child_again == child_name

    root.destroy()
    ok = reissued and distinct and restarted
    return ok, (
        f"reissued={reissued} ({first_path!r}), generated distinct={distinct}, "
        f"counter restarted={restarted}"
    )


def check_boolean_queries_answer_int_not_bool() -> Report:
    """`winfo_ismapped` answers an `int`, so `is True` is False on a mapped widget."""
    root = bench()
    frame = ttk.Frame(root)
    frame.pack()
    root.update()
    mapped = frame.winfo_ismapped()
    root.destroy()
    ok = isinstance(mapped, int) and not isinstance(mapped, bool) and (mapped is True) is False
    return ok, (
        f"winfo_ismapped()={mapped!r} ({type(mapped).__name__}), "
        f"is True={mapped is True}, is False={mapped is False}"
    )


def check_classic_pane_methods_are_present_but_refused() -> Report:
    """`ttk.PanedWindow` exposes classic methods the Tcl command refuses."""
    root = bench()
    paned = ttk.PanedWindow(root)
    present = isinstance(paned, tk.PanedWindow) and hasattr(paned, "paneconfigure")
    refused = False
    if present:
        try:
            paned.tk.call(str(paned), "paneconfigure")
        except tk.TclError as error:
            refused = "bad command" in str(error)
    root.destroy()
    return (present and refused), f"present={present}, refused={refused}"


def check_insert_refuses_one_past_the_last_pane() -> Report:
    """`insert` at one past the last pane raises rather than appending."""
    root = bench()
    paned = ttk.PanedWindow(root)
    for _ in range(3):
        paned.add(ttk.Label(root, text="x"))
    refused = False
    try:
        paned.insert(3, ttk.Label(root, text="y"))
    except tk.TclError as error:
        refused = "out of bounds" in str(error)
    root.destroy()
    return refused, f"insert(3) refused={refused}"


CHECKS = (
    ("a path is reissued and counters restart", check_a_path_is_reissued_and_counters_restart),
    ("boolean queries answer int, not bool", check_boolean_queries_answer_int_not_bool),
    (
        "classic pane methods are present but refused",
        check_classic_pane_methods_are_present_but_refused,
    ),
    ("insert refuses one past the last pane", check_insert_refuses_one_past_the_last_pane),
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
        except Exception as error:
            ok, detail = False, f"raised {type(error).__name__}: {error}"
        failures += 0 if ok else 1
        print(f"{name:46s} {'ok  ' if ok else 'FAIL'}  {detail}")
    return failures


if __name__ == "__main__":
    sys.exit(main())
