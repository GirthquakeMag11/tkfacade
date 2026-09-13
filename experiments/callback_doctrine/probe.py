"""Witness how Tk delivers callbacks, one check per claim.

Run with::

    xvfb-run -a uv run python -m experiments.callback_doctrine.probe

Three delivery facts must be pinned: what thread a callback runs
on, what a raise inside one does, and what a callback may do to the
library that called it. They rest on facts about Tk itself, and each
check here pins one fact by exercising it: the thread of delivery per
route, the fate of an exception per route, and the reentry cases — a
trace writing its own variable, a handler destroying its own widget, a
callback pumping the loop. Nothing here imports tkfacade; the library's
own delivery primitive (``BaseWidget.submit``) is pinned by the suite in
``tests/test_submit.py`` instead.

The expectations coded below are the behavior witnessed on Tk 8.6.14,
threaded Tcl, under X11 — see the README's findings table. A failure is
a finding, not necessarily a fault: it means that build does not behave
the way the evidence below says, and the findings must be re-read
against it. Every check prints its verdict; the exit status is the
number that failed.
"""

import sys
import threading
import tkinter as tk
from collections.abc import Callable

Report = tuple[bool, str]


def bench() -> tuple[tk.Tk, list[BaseException]]:
    """Return a withdrawn root whose callback-exception reports are captured."""
    root = tk.Tk()
    root.withdraw()
    reports: list[BaseException] = []

    def capture(_exc: object, val: BaseException, _tb: object) -> None:
        reports.append(val)

    root.report_callback_exception = capture  # type: ignore[method-assign]
    return root, reports


def mapped_frame(root: tk.Tk) -> tk.Frame:
    """Return a frame that is actually on screen, so generated events reach it."""
    root.deiconify()
    frame = tk.Frame(root)
    frame.pack()
    root.update()
    return frame


def check_generate_needs_the_x_window_to_exist() -> Report:
    """A generate is dropped until the widget's window exists; winfo_id creates it."""
    root, reports = bench()
    ran: list[str] = []
    fresh = tk.Frame(root)
    fresh.bind("<<Probe>>", lambda _e: ran.append("fresh"))
    fresh.event_generate("<<Probe>>")
    dropped = not ran
    fresh.winfo_id()  # forces creation: no update, no mapping, root withdrawn
    fresh.event_generate("<<Probe>>")
    ok = dropped and ran == ["fresh"] and not reports
    root.destroy()
    return ok, (
        f"before creation the generate {'was dropped' if dropped else 'DELIVERED'}; "
        f"after winfo_id alone it ran {ran} — mapping never entered into it"
    )


def check_event_handler_thread() -> Report:
    """An event binding's handler runs on the interpreter's own thread."""
    root, _ = bench()
    seen: list[int] = []
    widget = mapped_frame(root)
    widget.bind("<<Probe>>", lambda _e: seen.append(threading.get_ident()))
    widget.event_generate("<<Probe>>")
    ok = seen == [threading.get_ident()]
    root.destroy()
    return ok, f"handler threads {seen} vs caller {threading.get_ident()}: synchronous, same thread"


def check_trace_thread_same_thread() -> Report:
    """A write trace fired by a same-thread set() runs on that thread."""
    root, _ = bench()
    seen: list[int] = []
    var = tk.StringVar(root)
    var.trace_add("write", lambda *_: seen.append(threading.get_ident()))
    var.set("value")
    ok = seen == [threading.get_ident()]
    root.destroy()
    return ok, "trace ran synchronously on the setting thread"


def check_trace_thread_from_worker() -> Report:
    """A set() from a worker thread delivers the trace on the mainloop thread."""
    root, _ = bench()
    main_thread = threading.get_ident()
    seen: list[int] = []
    returned = threading.Event()
    var = tk.StringVar(root)
    var.trace_add("write", lambda *_: seen.append(threading.get_ident()))

    def worker() -> None:
        var.set("from-worker")
        returned.set()

    root.after(50, lambda: threading.Thread(target=worker, daemon=True).start())
    root.after(2000, root.quit)
    root.mainloop()
    ok = returned.is_set() and seen == [main_thread]
    detail = (
        "worker's set() blocked while the trace ran on the mainloop thread"
        if ok
        else f"trace threads {seen}, main {main_thread}, setter returned {returned.is_set()}"
    )
    root.destroy()
    return ok, detail


def check_after_callback_thread() -> Report:
    """An after-callback runs on the mainloop thread."""
    root, _ = bench()
    seen: list[int] = []

    def job() -> None:
        seen.append(threading.get_ident())
        root.quit()

    root.after(10, job)
    root.after(2000, root.quit)
    root.mainloop()
    ok = seen == [threading.get_ident()]
    root.destroy()
    return ok, "after-job ran on the mainloop thread"


def check_handler_raise_is_reported_and_loop_survives() -> Report:
    """A raising handler goes to report_callback_exception; the loop keeps running."""
    root, reports = bench()
    widget = mapped_frame(root)

    def bad(_e: tk.Event[tk.Frame]) -> None:
        raise RuntimeError("handler boom")

    widget.bind("<<Probe>>", bad)
    survived: list[bool] = []
    root.after(50, lambda: widget.event_generate("<<Probe>>"))
    root.after(150, lambda: survived.append(True))
    root.after(300, root.quit)
    root.after(2000, root.quit)
    root.mainloop()
    ok = len(reports) == 1 and survived == [True]
    root.destroy()
    return ok, f"reports {len(reports)}, later after fired {survived == [True]}: loop survived"


def check_handler_raise_spares_added_handlers() -> Report:
    """A raise in one add='+' handler does not stop the ones bound after it."""
    root, reports = bench()
    widget = mapped_frame(root)
    ran: list[str] = []

    def first(_e: tk.Event[tk.Frame]) -> None:
        ran.append("first")
        raise RuntimeError("first boom")

    widget.bind("<<Probe>>", first)
    widget.bind("<<Probe>>", lambda _e: ran.append("second"), add="+")
    widget.event_generate("<<Probe>>")
    ok = ran == ["first", "second"] and len(reports) == 1
    root.destroy()
    return ok, f"ran {ran}; the second handler fired after the first raised"


def check_handler_raise_spares_bindtag_chain() -> Report:
    """A raise in the widget-level handler does not stop bind_all's handler."""
    root, reports = bench()
    widget = mapped_frame(root)
    ran: list[str] = []

    def widget_level(_e: tk.Event[tk.Frame]) -> None:
        ran.append("widget")
        raise RuntimeError("widget boom")

    widget.bind("<<Probe>>", widget_level)
    root.bind_all("<<Probe>>", lambda _e: ran.append("all"))
    widget.event_generate("<<Probe>>")
    root.unbind_all("<<Probe>>")
    ok = ran == ["widget", "all"] and len(reports) == 1
    root.destroy()
    return ok, f"ran {ran}; the bindtag chain continued past the raise"


def check_command_raise_is_reported() -> Report:
    """A raising -command callback is reported; invoke() returns normally."""
    root, reports = bench()

    def bad() -> None:
        raise RuntimeError("command boom")

    button = tk.Button(root, command=bad)
    raised = False
    try:
        button.invoke()
    except Exception:
        raised = True
    ok = not raised and len(reports) == 1
    root.destroy()
    return ok, "invoke() returned normally; the raise went to report_callback_exception"


def check_trace_raise_is_swallowed_and_write_lands() -> Report:
    """A raising write trace is reported, the setter returns, the write lands."""
    root, reports = bench()
    var = tk.StringVar(root)

    def bad(*_: str) -> None:
        raise RuntimeError("watcher boom")

    var.trace_add("write", bad)
    raised = False
    try:
        var.set("value")
    except Exception:
        raised = True
    ok = not raised and var.get() == "value" and len(reports) == 1
    detail = (
        "set() returned normally, the value changed, the raise was reported"
        if ok
        else f"raised={raised}, value={var.get()!r}, reports={len(reports)}"
    )
    root.destroy()
    return ok, detail


def check_trace_raise_spares_other_traces() -> Report:
    """A raise in one write trace does not stop the variable's other traces."""
    root, reports = bench()
    var = tk.StringVar(root)
    ran: list[str] = []

    def bad(*_: str) -> None:
        ran.append("bad")
        raise RuntimeError("first watcher boom")

    var.trace_add("write", bad)
    var.trace_add("write", lambda *_: ran.append("second"))
    var.set("value")
    ok = sorted(ran) == ["bad", "second"] and len(reports) == 1
    root.destroy()
    return ok, f"ran {sorted(ran)}; the raise was reported and the other trace fired"


def check_write_inside_a_trace_fires_no_traces() -> Report:
    """A write made inside any write trace fires none of the variable's traces."""
    root, _ = bench()
    var = tk.StringVar(root)
    order: list[str] = []

    def self_writer(*_: str) -> None:
        order.append("writer")
        if order.count("writer") == 1:
            var.set("inner")

    var.trace_add("write", self_writer)
    var.trace_add("write", lambda *_: order.append("sibling"))
    var.set("outer")
    ok = order == ["sibling", "writer"] and var.get() == "inner"
    detail = f"firing order {order}, final value {var.get()!r}: the inner write triggered nothing"
    root.destroy()
    return ok, detail


def check_destroy_from_handler_mid_chain() -> Report:
    """A handler destroying its own widget: the rest of it runs; later handlers do not."""
    root, reports = bench()
    widget = mapped_frame(root)
    ran: list[str] = []

    def first(_e: tk.Event[tk.Frame]) -> None:
        ran.append("first")
        widget.destroy()
        ran.append("first-after-destroy")

    widget.bind("<<Probe>>", first)
    widget.bind("<<Probe>>", lambda _e: ran.append("second"), add="+")
    widget.event_generate("<<Probe>>")
    ok = ran == ["first", "first-after-destroy"] and not reports
    root.destroy()
    return ok, f"ran {ran}, reports {len(reports)}; the add='+' handler after the destroy did not"


def check_second_destroy_is_harmless() -> Report:
    """Destroying an already-destroyed widget raises nothing and fires nothing."""
    root, reports = bench()
    widget = tk.Frame(root)
    destroys: list[int] = []
    widget.bind("<Destroy>", lambda _e: destroys.append(1))
    widget.destroy()
    raised = False
    try:
        widget.destroy()
    except Exception:
        raised = True
    ok = destroys == [1] and not raised and not reports
    root.destroy()
    return ok, f"<Destroy> fired {len(destroys)} time(s); the second destroy() was a no-op"


def check_update_nests_dispatch_inside_a_callback() -> Report:
    """update() inside a callback dispatches other callbacks within its frame."""
    root, _ = bench()
    order: list[str] = []

    def inner() -> None:
        order.append("inner")

    def outer() -> None:
        order.append("outer-start")
        root.after(0, inner)
        root.update()
        order.append("outer-end")
        root.quit()

    root.after(20, outer)
    root.after(2000, root.quit)
    root.mainloop()
    ok = order == ["outer-start", "inner", "outer-end"]
    root.destroy()
    return ok, f"order {order}; the inner callback ran inside the outer one's frame"


CHECKS: tuple[tuple[str, Callable[[], Report]], ...] = (
    ("generate needs the X window to exist", check_generate_needs_the_x_window_to_exist),
    ("event handler on interpreter thread", check_event_handler_thread),
    ("trace on the setting thread", check_trace_thread_same_thread),
    ("worker set() delivers trace on mainloop", check_trace_thread_from_worker),
    ("after-callback on mainloop thread", check_after_callback_thread),
    ("handler raise reported, loop survives", check_handler_raise_is_reported_and_loop_survives),
    ("handler raise spares add='+' handlers", check_handler_raise_spares_added_handlers),
    ("handler raise spares the bindtag chain", check_handler_raise_spares_bindtag_chain),
    ("command raise reported, invoke returns", check_command_raise_is_reported),
    ("trace raise swallowed, write lands", check_trace_raise_is_swallowed_and_write_lands),
    ("trace raise spares other traces", check_trace_raise_spares_other_traces),
    ("write inside a trace fires no traces", check_write_inside_a_trace_fires_no_traces),
    ("destroy mid-chain drops later handlers", check_destroy_from_handler_mid_chain),
    ("second destroy is harmless", check_second_destroy_is_harmless),
    ("update() nests dispatch in a callback", check_update_nests_dispatch_inside_a_callback),
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
