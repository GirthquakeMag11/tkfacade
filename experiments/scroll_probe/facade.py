"""Witness what the scroll machinery bears when its assumptions move.

Run with::

    xvfb-run -a uv run python -m experiments.scroll_probe.facade

`probe.py` beside this measures Tk. This measures tkfacade against Tk:
whether placement is nothing but the gutter cells (a bar re-gridded
into the left cell keeps driving and tracking), whether auto-hide's
reversibility holds in a cell it was never tested in, and whether
`AbstractScrollable` transfers to a canvas viewport once someone
maintains the scrollregion Tk will not. Each check pins one fact the
scrollbar-home decision turns on.

Unlike `probe.py` this imports tkfacade, because the questions are
about the library meeting Tk rather than about Tk alone.

The expectations coded below are the behaviour witnessed on Tk 8.6.14,
x11, under Xvfb with no window manager. A failure is a finding, not
necessarily a fault. Every check prints its verdict; the exit status
is the number that failed.
"""

import sys
import tkinter as tk
from tkinter import ttk

import tkfacade
from tkfacade.scroll import AbstractScrollable
from tkfacade.window import Root

Report = tuple[bool, str]

_FILLER = "\n".join(f"line {index} with a tail" for index in range(200))


def bench() -> tuple[Root, tkfacade.Window]:
    """Return a root holding a spare window, so a destroy is never the last."""
    root = Root()
    tkfacade.Window(title="keep", root=root)
    window = tkfacade.Window(title="probe", root=root)
    root._tk.update()
    return root, window


def relocate_left(box: tkfacade.TextBox) -> ttk.Scrollbar:
    """Move ``box``'s vertical bar into the left gutter, by hand.

    The three coupled facts placement is made of: the bar's cell, the
    content's cell, and where the stretch weight sits.
    """
    bar = box._scroll_bars["vertical"]
    box._scroll_target.grid(row=0, column=1, sticky="nsew")
    bar.grid(row=0, column=0, sticky="ns")
    box._tk.columnconfigure(0, weight=0)
    box._tk.columnconfigure(1, weight=1)
    return bar


class CanvasView(AbstractScrollable):
    """The smallest AbstractScrollable over a canvas-window viewport.

    The canvas is the scroll target; the inner frame is the content,
    with the scrollregion re-declared on its every ``<Configure>`` —
    the maintenance `probe.py` witnessed Tk demanding.
    """

    __slots__ = ("_canvas", "_inner")

    def __init__(self, window: tkfacade.Window) -> None:
        self._tk = ttk.Frame(window._tk)
        # ringless, or the resting view starts past zero and the edge
        # predicates lie (`probe.py`, the highlight-ring check)
        self._canvas = tk.Canvas(self._tk, width=200, height=100, highlightthickness=0)
        self._inner = ttk.Frame(self._canvas)
        self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._inner.bind(
            "<Configure>",
            lambda _event: self._canvas.configure(scrollregion=self._canvas.bbox("all")),
        )
        self._build_gutters(self._canvas, vertical=True, horizontal=False)
        super().__init__()

    def fill(self, count: int) -> None:
        """Grid ``count`` labels into the content, one per row."""
        for index in range(count):
            tk.Label(self._inner, text=f"row {index}").grid(row=index, column=0)


def check_a_relocated_bar_keeps_driving_and_tracking() -> Report:
    """The gutter cells are all that placement is; the wiring never notices."""
    root, window = bench()
    box = tkfacade.TextBox(window)
    box.grid(row=0, column=0)
    box._scroll_target.insert("1.0", _FILLER)  # type: ignore[attr-defined]
    root._tk.update()
    bar = relocate_left(box)
    root._tk.update()
    box.scroll_to(y=0.5)
    root._tk.update()
    tracks = abs(bar.get()[0] - box.y_offset) < 0.001 and box.y_offset > 0.0
    root._tk.call(str(bar.cget("command")), "moveto", "0.25")
    root._tk.update()
    drives = abs(box.y_offset - 0.25) < 0.05
    placed = bar.grid_info()["column"] == 0
    root.destroy()
    return (tracks and drives and placed), f"tracks={tracks}, drives={drives}, in column 0={placed}"


def check_auto_hide_round_trips_in_the_left_gutter() -> Report:
    """grid_remove keeps the relocated cell, so auto-hide is placement-blind."""
    root, window = bench()
    box = tkfacade.TextBox(window, vertical_scrollbar=tkfacade.ScrollbarSpec(auto_hide=True))
    box.grid(row=0, column=0)
    box._scroll_target.insert("1.0", _FILLER)  # type: ignore[attr-defined]
    root._tk.update()
    bar = relocate_left(box)
    root._tk.update()
    shown_before = bool(bar.winfo_manager())
    box._scroll_target.delete("1.0", "end")  # type: ignore[attr-defined]
    root._tk.update()
    hidden = not bar.winfo_manager()
    box._scroll_target.insert("1.0", _FILLER)  # type: ignore[attr-defined]
    root._tk.update()
    returned = bool(bar.winfo_manager()) and bar.grid_info()["column"] == 0
    root.destroy()
    return (
        shown_before and hidden and returned
    ), f"shown={shown_before}, hid={hidden}, returned to column 0={returned}"


def check_the_machinery_transfers_to_a_canvas_viewport() -> Report:
    """AbstractScrollable scrolls a frame of widgets, given a maintained region."""
    root, window = bench()
    view = CanvasView(window)
    view.grid(row=0, column=0)
    view.fill(30)
    root._tk.update()
    scrollable = view.can_scroll_down and not view.can_scroll_up
    view.scroll_to(y=0.5)
    root._tk.update()
    offset = view.y_offset
    bar = view._scroll_bars["vertical"]
    tracks = abs(bar.get()[0] - offset) < 0.001
    root.destroy()
    return (
        scrollable and offset > 0.0 and tracks
    ), f"scrollable={scrollable}, moved to {offset:.2f}, bar tracks={tracks}"


CHECKS = (
    ("a relocated bar drives and tracks", check_a_relocated_bar_keeps_driving_and_tracking),
    ("auto-hide round-trips in the left gutter", check_auto_hide_round_trips_in_the_left_gutter),
    ("the machinery scrolls a canvas viewport", check_the_machinery_transfers_to_a_canvas_viewport),
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
