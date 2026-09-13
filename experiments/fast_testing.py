"""Scratch pad for testing miscellany rapidly.

Run with:  uv run python experiments/fast_testing.py [demo]

A place to hang a widget on a window and look at it. Nothing here is
structurally significant: this file is where you try something and then
throw it away.

Two rules. Decorate a builder with :func:`demo`, and the one defined
*last* is what opens when no name is given -- so adding a function at
the bottom of the file and running it is the whole cycle. Older
experiments stay parked under their own names and open with
``fast_testing.py <name>``.

What the harness hands you:

- A window pre-weighted at ``(0, 0)``. Wrappers place themselves with an
  explicit ``.grid()`` call; its defaults (``row=0, column=0,
  sticky="nsew"``) land in the weighted cell and it returns the wrapper,
  so ``Tree(win).grid()`` fills the window in one line. Raw ``tkinter``
  widgets accept a wrapper as their master directly (``ttk.Frame(win)``);
  :func:`stretch` weights their grids.
- Escape closes everything from whichever window has focus, and so does
  the X button, even when a demo has opened windows of its own.
- Tracebacks from Tk callbacks printed under a banner instead of being
  swallowed mid-loop.
- A clean interpreter every run. :func:`run` tears the old root down
  before building anything, so a crashed experiment cannot poison the
  next one.

The ``from tkfacade import (...)`` block below is deliberately over-broad: it
is a palette, not a dependency list. Leaving unused names in it is the
point, which is what the ``noqa`` directive is protecting.
"""

# ruff: noqa: F401, F811, F841, E402, E731, RUF100
# mypy: ignore-errors
# This file is meant to be full of half-finished code. RUF100 must stay
# in that list: without it ruff deletes the whole directive line as soon
# as none of its codes happen to be firing, and then the next unused
# import you add gets deleted for real. Swap the mypy line for
#   # mypy: disable-error-code="no-untyped-def, no-untyped-call"
# to keep the harness type-checked -- but then no demo may be annotated
# and nothing may be scratched at module level.

import sys
import tkinter as tk
import traceback
from collections.abc import Callable, Iterable
from tkinter import ttk
from types import TracebackType

from tkfacade import (
    Anchor,
    Arrangement,
    ImageWrapper,
    Label,
    StackFrame,
    TabFrame,
    Table,
    TextBox,
    TitleEntry,
    Tree,
    TreeColumnSpec,
    VideoPlayer,
    Window,
    get_root,
)
from tkfacade.widget import GridConfig, Surface, Widget
from tkfacade.window import _root as _root_module

# -- the demo registry ------------------------------------------------------

type Builder = Callable[[Window], None]
"""A demo: fill the playground window and return. :func:`run` does the rest."""

DEMOS: dict[str, Builder] = {}
"""Registered demos, keyed by function name, oldest first."""


def demo[F: Builder](fn: F, /) -> F:
    """Register ``fn`` under its own ``__name__``, newest last.

    Re-registering a name moves it back to the end, so :func:`run` with
    no argument always opens the demo defined last in the file.

    Args:
        fn (F): The builder to register.

    Returns:
        ``fn`` unchanged, so the decorated name stays directly callable.
    """
    # plain reassignment would keep the key's original position, and then
    # reversed() would hand back a demo you thought you had replaced
    DEMOS.pop(fn.__name__, None)
    DEMOS[fn.__name__] = fn
    return fn


# -- the playground window --------------------------------------------------


def window(
    *,
    title: str = "fast testing",
    width: int = 900,
    height: int = 620,
    x_position: int | None = None,
    y_position: int | None = None,
) -> Window:
    """Build the playground window: pre-weighted at ``(0, 0)`` and centred.

    Installs no hooks -- :func:`run` does that, and only for the first
    window, so a second window a demo opens does not steal focus or
    re-bind the kill switch.

    Args:
        title (str): Window title. Defaults to "fast testing".
        width (int): Width in pixels. Defaults to 900.
        height (int): Height in pixels. Defaults to 620.
        x_position (int | None): Left edge in pixels. Defaults to None,
            meaning horizontally centred.
        y_position (int | None): Top edge in pixels. Defaults to None,
            meaning a third of the way down the screen.

    Returns:
        The window, already placed. Reach the raw toplevel with
        ``win._tk`` for anything :class:`Window` does not expose, such
        as ``bind`` or ``after``.
    """
    # Centred, not Window's default +100+100, so the playground never opens
    # under the pointer or a screen corner. Computed up front and passed to
    # the constructor, which places the window in one write rather than
    # opening it at the default and moving it afterwards.
    root = get_root()
    if x_position is None:
        x_position = max(0, (root._tk.winfo_screenwidth() - width) // 2)
    if y_position is None:
        y_position = max(0, (root._tk.winfo_screenheight() - height) // 3)
    win = Window(
        title=title,
        width=width,
        height=height,
        x_position=x_position,
        y_position=y_position,
        root=root,
    )
    win.grid_rowconfigure(0, weight=1)
    win.grid_columnconfigure(0, weight=1)
    return win


def stretch(
    target: tk.Misc | Widget,
    /,
    *,
    rows: Iterable[int] = (0,),
    columns: Iterable[int] = (0,),
    weight: int = 1,
) -> None:
    """Give the named rows and columns of ``target``'s grid a weight.

    The counterpart to the pre-weighted window cell, for containers built
    raw -- such as the bare ``ttk.Frame`` pages :meth:`StackFrame.add`
    hands back. Wrappers work too; they carry the same grid methods.

    Args:
        target (tk.Misc | Widget): A Tk widget or a tkfacade wrapper.
        rows (Iterable[int]): Row indices to weight. Defaults to ``(0,)``.
        columns (Iterable[int]): Column indices to weight. Defaults to
            ``(0,)``.
        weight (int): The weight to give each. Defaults to 1.
    """
    for row in rows:
        target.grid_rowconfigure(row, weight=weight)
    for column in columns:
        target.grid_columnconfigure(column, weight=weight)


def pump(target: tk.Misc | Widget, /) -> None:
    """Run every pending Tk event now, timers included.

    :meth:`Window.update_idletasks` runs only idle tasks, so it never
    fires the ``after(0, ...)`` that defers a :class:`StackFrame`'s first
    ``show``. Call this from builder code to inspect a widget tree before
    the mainloop starts -- never from inside a Tk callback, where it
    re-enters the event loop.

    Args:
        target (tk.Misc | Widget): Any widget; only its interpreter
            matters, and every window shares one.
    """
    widget = target if isinstance(target, tk.Misc) else target._tk
    widget.update()


# -- lifecycle --------------------------------------------------------------

STOP_ON_CALLBACK_ERROR: bool = False
"""Whether a Tk callback exception tears the app down instead of printing.

Flip to True when a binding is failing on every event and the traceback
flood is worse than losing the window.
"""


def reset() -> None:
    """Destroy the live root and every window under it, if there is one.

    Both the teardown between runs and the Escape kill switch. Reads the
    package's module global directly rather than calling :func:`get_root`,
    which *constructs* a ``tk.Tk`` when none is live -- on the normal path
    this runs immediately after the mainloop has already destroyed the
    root, so going through ``get_root`` would build a whole Tcl
    interpreter just to tear it down, and a ``TclError`` raised there
    would replace the exception being unwound. Idempotent, and free after
    the first call.
    """
    # Three things are spelled _root: the package module aliased above, its
    # global read here, and Window._root. No GLOBAL_LOCK: reset only runs on
    # the main thread with no mainloop in flight, and the cascade in
    # BaseWindow.destroy -- the only other writer -- runs inside one.
    live = _root_module._root
    if live is not None and not live.destroyed:
        live.destroy()


def _report_callback_exception(
    exc: type[BaseException], val: BaseException, tb: TracebackType | None
) -> None:
    """Print a Tk callback's traceback under a banner, and keep looping.

    Tk's default prints an uncaught callback error and carries on, which
    is right for a scratch pad -- one broken binding should not cost you
    the window -- but the output is easy to miss among everything else on
    the console. :data:`STOP_ON_CALLBACK_ERROR` opts into quitting.
    """
    print("\n--- exception in a Tk callback ---", file=sys.stderr)
    traceback.print_exception(exc, val, tb)
    if STOP_ON_CALLBACK_ERROR:
        reset()


def _install_hooks(win: Window, /) -> None:
    """Wire up the traceback hook, the kill switch, and the raise-to-front."""
    # Reaches past Root deliberately: Tk looks this up on the interpreter
    # object itself, so a Toplevel is the wrong place to hang it. get_root
    # constructs nothing here -- window() has already built the root.
    get_root()._tk.report_callback_exception = _report_callback_exception

    top = win._tk
    # bind_all, not bind: this registers on the interpreter's "all" bindtag,
    # so Escape kills everything from whichever window happens to have focus.
    # It also shadows Escape for KeyboardState's own bind_all, which is
    # irrelevant when the binding's whole job is to quit.
    top.bind_all("<Escape>", lambda _event: reset())
    # the X button needs the same treatment: BaseWindow.destroy cascades to
    # the root only when the window it closed was the last live toplevel, so
    # closing this one while a demo's second window is open hangs the process
    top.protocol("WM_DELETE_WINDOW", reset)

    # the topmost flip is what actually calls SetWindowPos; lift() alone is
    # unreliable while another process owns the foreground, and focus_force
    # is what makes Escape work without clicking the window first
    top.attributes("-topmost", True)
    top.lift()
    top.focus_force()
    # released once mapped, so it does not stay pinned over the editor. If it
    # ever lands behind, widen this to top.after(200, ...) instead.
    top.after_idle(top.attributes, "-topmost", False)


def run(name: str | None = None, /) -> None:
    """Open a demo's window and block until it closes.

    Args:
        name (str | None): Which registered demo to open. Defaults to
            None, meaning the one registered last.

    Raises:
        LookupError: If nothing is registered, or ``name`` names a demo
            that is not.
    """
    if not DEMOS:
        raise LookupError(
            "No demo is registered; decorate a builder with @demo before calling run."
        )
    key = next(reversed(DEMOS)) if name is None else name
    if key not in DEMOS:
        raise LookupError(
            f"No demo named {key!r} is registered. "
            f"Registered demos, newest last: {', '.join(DEMOS)}."
        )
    builder = DEMOS[key]

    # Order is load-bearing. reset() first: get_root replaces only a
    # *destroyed* root, so a leftover live one would be reused, carrying
    # whatever the last run left on it into this one. Hooks after window(),
    # which is what causes the interpreter to exist. The builder before the
    # mainloop, so a StackFrame's deferred first show lands on a complete
    # tree. And reset() in finally, so a builder that raises leaves no live
    # interpreter to poison the next run.
    reset()
    try:
        win = window(title=f"fast testing: {key}")
        _install_hooks(win)
        builder(win)
        win.run_mainloop()
    finally:
        reset()


# -- experiments: everything below is yours, the last @demo wins ------------


@demo
def tree_demo(win: Window) -> None:
    """A parked experiment: open it with ``fast_testing.py tree_demo``."""
    tree = Tree(
        win,
        columns=[TreeColumnSpec(name="id"), TreeColumnSpec(name="label")],
    ).grid()
    for number, label in enumerate(("first", "second", "third"), start=1):
        # values=, not **kwargs: insert owns text/image/parent/index/tags,
        # so a column named like one of those would collide
        tree.insert(values={"id": number, "label": label})


@demo
def scratch(win: Window) -> None:
    """Whatever is being tried right now. Overwrite this freely."""
    box = TextBox(win, "Escape closes everything, from any window.\n").grid()

    # ttk takes the wrapper as its master directly. Row 1 has no weight, so
    # the bar takes its natural height and the box, gridded into the weighted
    # cell at (0, 0), gets all the rest.
    bar = ttk.Frame(win, padding=4)
    bar.grid(row=1, column=0, sticky="ew")

    def append() -> None:
        box.text = box.text + "clicked\n"

    def explode() -> None:
        raise RuntimeError("This is what a callback exception looks like.")

    ttk.Button(bar, text="append", command=append).grid(row=0, column=0)
    ttk.Button(bar, text="raise", command=explode).grid(row=0, column=1, padx=6)


@demo
def title_entry_variants(win: Window) -> None:
    """The TitleEntry design range, laid out as a form. Resize to judge."""
    form = ttk.Frame(win, padding=12)
    form.grid(row=0, column=0, sticky="nsew")
    stretch(form, rows=())

    plain = TitleEntry(form, title="Username", text="captainpatchwork")
    password = TitleEntry(form, title="Password", text="hunter2", mask="*")
    frozen = TitleEntry(form, title="Licence key (read-only)", text="TKF-1234-5678", read_only=True)
    centred = TitleEntry(form, title="Centered content", text="middle", justify="center")
    for row, widget in enumerate((plain, password, frozen, centred)):
        widget.grid(row=row, column=0, sticky="ew", pady=(0, 8))

    # the two side-by-side arrangements: resizing shows the entry taking every
    # spare pixel while the title keeps its natural width
    beside = TitleEntry(form, title="Label left", text="entry right", arrangement="left-right")
    reversed_ = TitleEntry(form, title="Label right", text="entry left", arrangement="right-left")
    beside.grid(row=4, column=0, sticky="ew", pady=(0, 8))
    reversed_.grid(row=5, column=0, sticky="ew", pady=(0, 8))

    # two entries sharing one title variable: retitling one retitles both
    shared = tk.StringVar(form, "Shared title")
    twin_a = TitleEntry(form, title_variable=shared, text="left twin")
    twin_b = TitleEntry(form, title_variable=shared, text="right twin")
    twin_a.grid(row=6, column=0, sticky="ew", pady=(0, 8))
    twin_b.grid(row=7, column=0, sticky="ew")
    shared.set("Shared title (edit either header via .title.set)")


@demo
def title_entry_live(win: Window) -> None:
    """One TitleEntry driven through its whole API from a button bar."""
    body = ttk.Frame(win, padding=12)
    body.grid(row=0, column=0, sticky="nsew")
    stretch(body, rows=())

    subject = TitleEntry(body, title="Subject", text="type here")
    subject.grid(row=0, column=0, sticky="ew", pady=(0, 8))

    echo = TitleEntry(body, title="Echo (read-only, traced)", read_only=True)
    echo.grid(row=1, column=0, sticky="ew", pady=(0, 8))
    subject.text_variable.trace_add("write", lambda *_: setattr(echo, "text", subject.text))

    bar = ttk.Frame(body)
    bar.grid(row=2, column=0, sticky="ew")

    def toggle_lock() -> None:
        if subject.disabled:
            subject.enable()
            subject.title.set("Subject")
        else:
            subject.disable()
            subject.title.set("Subject (locked)")

    def write_while_locked() -> None:
        # lands even when disabled: the write goes through the variable
        subject.text = "programmatic write"

    def toggle_mask() -> None:
        subject.mask = "" if subject.mask else "*"

    def cycle_title_anchor() -> None:
        # while stacked the label is as wide as the entry, so this is what
        # moves a one-line title -- .title.justify would do nothing visible.
        # Side by side the label's cell is its own width and nothing moves.
        order: dict[str, Anchor] = {"w": "center", "center": "e", "e": "w"}
        subject.title.anchor = order.get(subject.title.anchor, "w")

    def cycle_arrangement() -> None:
        order: dict[str, Arrangement] = {
            "top-bottom": "left-right",
            "left-right": "bottom-top",
            "bottom-top": "right-left",
            "right-left": "top-bottom",
        }
        subject.arrangement = order[subject.arrangement]
        subject.title.set(f"Subject ({subject.arrangement})")

    for column, (label, command) in enumerate(
        (
            ("lock/unlock", toggle_lock),
            ("write text", write_while_locked),
            ("mask", toggle_mask),
            ("select all", subject.select_all),
            ("title anchor", cycle_title_anchor),
            ("arrangement", cycle_arrangement),
        )
    ):
        ttk.Button(bar, text=label, command=command).grid(row=0, column=column, padx=(0, 6))


# -- entry point ------------------------------------------------------------

if __name__ == "__main__":
    requested = sys.argv[1] if len(sys.argv) > 1 else None
    # validated here rather than by catching run()'s LookupError, which would
    # also catch one raised from inside a demo and misreport it as a typo
    if requested is not None and requested not in DEMOS:
        print(
            f"No demo named {requested!r} is registered. "
            f"Registered demos, newest last: {', '.join(DEMOS) or '(none)'}.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    run(requested)
