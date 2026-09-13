"""Witness what a menubar facade can be built on, one check per claim.

Run with::

    xvfb-run -a uv run python -m experiments.menu_probe.facade

`probe.py` beside this measures Tk. This measures tkfacade against Tk:
whether the menu facade (`RuledMenu`, so rules are witnessed too)
survives on a window's menubar, where the bar's
menu can be mastered without the window growing a child no wrapper owns,
whether a `BaseWidget` can own a `tk.Menu` at all, whether the bar's
installation can be read back honestly, and what a binding on it
delivers. Each check pins one fact a candidate design turns on.

Unlike `probe.py` this imports tkfacade, because the questions are about
the library meeting Tk rather than about Tk alone.

The expectations coded below are the behaviour witnessed on Tk 8.6.14,
x11, under Xvfb with no window manager. A failure is a finding, not
necessarily a fault. Every check prints its verdict; the exit status is
the number that failed.
"""

import gc
import sys
import tkinter as tk

import tkfacade
from tkfacade.events import Destroyed
from tkfacade.menu import MenuBase, MenuPart, RuledMenu
from tkfacade.widget import BaseWidget
from tkfacade.window import Root

Report = tuple[bool, str]


class BarFacade(RuledMenu):
    """The smallest thing that could wear the menu facade over a window's bar.

    Wears `RuledMenu` where the real `Menubar` wears `MenuBase`
    alone, on purpose: the rule call `Menubar` refuses by absence is one
    of the five kinds the first check witnesses seating in a top row.
    """

    __slots__ = ("_parts", "_tk_menu")

    def __init__(self, window: tkfacade.Window) -> None:
        self._tk_menu = tk.Menu(window._tk, tearoff=False)
        self._parts: list[MenuPart] = []
        window._tk["menu"] = str(self._tk_menu)


class MenuWrapper(BaseWidget):
    """The smallest BaseWidget that owns a tk.Menu."""

    __slots__ = ("_tk",)

    def __init__(self, window: tkfacade.Window) -> None:
        self._tk = tk.Menu(window._tk, tearoff=False)
        self._tk.add_cascade(label="File", menu=tk.Menu(self._tk, tearoff=False))
        super().__init__()
        window._tk["menu"] = str(self._tk)


def bench() -> tuple[Root, tkfacade.Window]:
    """Return a root holding a spare window, so a destroy is never the last."""
    root = Root()
    tkfacade.Window(title="keep", root=root)
    window = tkfacade.Window(title="probe", root=root)
    root._tk.update()
    return root, window


def leaf(widget: object) -> str:
    """Return the last path segment, which is what `children` is keyed by."""
    return str(widget).rsplit(".", 1)[-1]


def installed(window: tkfacade.Window, menu: tk.Menu) -> str:
    """Say whether `menu` is the bar this window is actually showing."""
    interp = window._tk.tk
    path = str(window._tk["menu"])
    if path != str(menu):
        return "not ours"
    if not interp.call("winfo", "exists", path):
        return "dead"
    if str(interp.call("winfo", "class", path)) != "Menu":
        return "not a menu"
    children = interp.splitlist(interp.call("winfo", "children", str(window)))
    rendering = any(str(interp.call(kid, "cget", "-type")) == "menubar" for kid in children)
    return "installed and rendering" if rendering else "installed, not rendering"


# --- does MenuBase survive on a bar? -------------------------------------


def check_every_row_kind_seats_in_the_top_row() -> Report:
    """All five insert_* calls work on a menu serving as a window's bar."""
    root, window = bench()
    bar = BarFacade(window)
    bar.insert_submenu("File")
    bar.insert_command("Save")
    bar.insert_checkbox("Tick", checked=tkfacade.ObservableBool(False))
    bar.insert_separator()
    bar.insert_choices(("A", "B"), chosen=tkfacade.ObservableStr("A"))
    root._tk.update()
    kinds = [type(part).__name__ for part in bar._parts]
    root.destroy()
    expected = ["Submenu", "CommandRow", "CheckboxRow", "MenuPart", "ChoiceRow", "ChoiceRow"]
    return kinds == expected, f"{kinds}"


def check_handles_address_rows_sharing_text() -> Report:
    """Two top-row entries with one label stay distinct, which Tk's own index cannot."""
    root, window = bench()
    bar = BarFacade(window)
    first, second = bar.insert_submenu("Same"), bar.insert_submenu("Same")
    root._tk.update()
    before = (first.index, second.index)
    first.delete()
    after = (first.deleted, second.index)
    root.destroy()
    return (
        before == (0, 1) and after == (True, 0)
    ), f"indices {before}, after deleting the first {after}"


def check_a_top_row_submenu_is_a_menu() -> Report:
    """Submenu is a row and a menu at once, in the top row as anywhere."""
    root, window = bench()
    bar = BarFacade(window)
    sub = bar.insert_submenu("File")
    sub.insert_command("New")
    deeper = sub.insert_submenu("More")
    deeper.insert_command("Deep")
    root._tk.update()
    seated = (len(sub._parts), len(deeper._parts))
    ok = isinstance(sub, MenuBase) and seated == (2, 1)
    root.destroy()
    return (
        ok,
        f"sub is a menu={isinstance(sub, MenuBase)}, seated={seated}",
    )


def check_a_row_command_fires_from_the_bar() -> Report:
    """The row's own callback runs, which is the route a user's choice takes."""
    root, window = bench()
    bar = BarFacade(window)
    fired: list[str] = []
    row = bar.insert_command("Save", command=lambda: fired.append("save"))
    root._tk.update()
    row.invoke()
    root.destroy()
    return fired == ["save"], f"fired {fired}"


# --- where can the menu be mastered? -----------------------------------------


def check_mastering_on_the_window_makes_an_unowned_child() -> Report:
    """A window-mastered bar menu is a child no wrapper answers for."""
    root, window = bench()
    menu = tk.Menu(window._tk, tearoff=False)
    window._tk["menu"] = str(menu)
    root._tk.update()
    is_child = leaf(menu) in window.children
    try:
        window.nametowrapper(leaf(menu))
        owned = True
    except KeyError:
        owned = False
    root.destroy()
    return (is_child and not owned), f"window child={is_child}, a wrapper owns it={owned}"


def check_mastering_on_a_child_keeps_it_off_the_window() -> Report:
    """Mastered on a frame, the menu is not a window child yet still dies with it."""
    root, window = bench()
    holder = tkfacade.Frame(window)
    menu = tk.Menu(holder._tk, tearoff=False)
    menu.add_cascade(label="File", menu=tk.Menu(menu, tearoff=False))
    window._tk["menu"] = str(menu)
    root._tk.update()
    is_child = leaf(menu) in window.children
    window.destroy()
    root._tk.update()
    died = not menu.winfo_exists()
    root.destroy()
    return (not is_child and died), f"window child={is_child}, died with the window={died}"


# --- can a BaseWidget own a menu? --------------------------------------------


def check_a_basewidget_can_own_a_menu() -> Report:
    """Construction, registration and lookup all work for a wrapped tk.Menu."""
    root, window = bench()
    bar = MenuWrapper(window)
    root._tk.update()
    resolved = window.nametowrapper(leaf(bar)) is bar
    every = all(isinstance(window.nametowrapper(name), BaseWidget) for name in window.children)
    root.destroy()
    return (
        resolved and every
    ), f"resolves to itself={resolved}, every window child resolves={every}"


def check_a_wrapped_menu_offers_no_geometry() -> Report:
    """BaseWidget carries no grid/pack/place, so containment does not arise."""
    root, window = bench()
    bar = MenuWrapper(window)
    absent = [name for name in ("grid", "pack", "place") if not hasattr(bar, name)]
    root.destroy()
    return absent == ["grid", "pack", "place"], f"absent: {absent}"


def check_a_wrapped_menu_evicts_itself() -> Report:
    """Destroying the menu takes its registry entry with it."""
    root, window = bench()
    bar = MenuWrapper(window)
    root._tk.update()
    name = leaf(bar)
    bar._tk.destroy()
    root._tk.update()
    gc.collect()
    try:
        window.nametowrapper(name)
        evicted = False
    except KeyError:
        evicted = True
    root.destroy()
    return evicted, f"registry entry gone={evicted}"


# --- can the bar's state be read back? ---------------------------------------


def check_the_install_can_be_verified() -> Report:
    """Three states are distinguishable from Tk, none by the obvious query."""
    root, window = bench()
    mine = tk.Menu(window._tk, tearoff=False)
    mine.add_cascade(label="File", menu=tk.Menu(mine, tearoff=False))
    window._tk["menu"] = str(mine)
    root._tk.update()
    live = installed(window, mine)
    stranger = installed(window, tk.Menu(window._tk, tearoff=False))
    mine.destroy()
    root._tk.update()
    dead = installed(window, mine)
    root.destroy()
    return (live == "installed and rendering" and stranger == "not ours" and dead == "dead"), (
        f"live={live!r}, other={stranger!r}, destroyed={dead!r}"
    )


def check_ismapped_lies_about_a_visible_bar() -> Report:
    """The obvious query answers about the unmapped master, not the bar."""
    root, window = bench()
    mine = tk.Menu(window._tk, tearoff=False)
    mine.add_cascade(label="File", menu=tk.Menu(mine, tearoff=False))
    window._tk["menu"] = str(mine)
    root._tk.update()
    mapped, verified = mine.winfo_ismapped(), installed(window, mine)
    root.destroy()
    return (mapped == 0 and verified == "installed and rendering"), (
        f"winfo_ismapped={mapped} while the bar is {verified}"
    )


# --- what does a binding deliver? --------------------------------------------


def check_a_binding_delivers_the_unreachable_clone() -> Report:
    """A bind on the master hears the clone, and cannot say which widget it was."""
    root, window = bench()
    bar = MenuWrapper(window)
    root._tk.update()
    delivered: list[object] = []
    bar._tk.bind("<Button-3>", lambda event: delivered.append(event.widget))
    interp = window._tk.tk
    children = interp.splitlist(interp.call("winfo", "children", str(window)))
    clone = next(str(kid) for kid in children if "#" in str(kid))
    interp.call("event", "generate", clone, "<Button-3>", "-x", "5", "-y", "5")
    root._tk.update()
    heard = bool(delivered)
    reported = str(delivered[0]) if delivered else ""
    try:
        window._tk.nametowidget(reported)
        resolvable = True
    except KeyError:
        resolvable = False
    root.destroy()
    return (heard and reported == clone and not resolvable), (
        f"heard={heard}, delivered {reported!r}, resolvable={resolvable}"
    )


def check_the_destroy_binding_hears_the_submenu_too() -> Report:
    """One destroy reaches the facade twice, the submenu's included."""
    root, window = bench()
    bar = MenuWrapper(window)
    root._tk.update()
    heard: list[object] = []
    bar.bind(Destroyed(), lambda event: heard.append(event))
    bar._tk.destroy()
    root._tk.update()
    count = len(heard)
    root.destroy()
    return count > 1, f"{count} Destroy events for one menu and its submenu"


CHECKS = (
    ("every row kind seats in the top row", check_every_row_kind_seats_in_the_top_row),
    ("handles address rows sharing text", check_handles_address_rows_sharing_text),
    ("a top-row submenu is a menu", check_a_top_row_submenu_is_a_menu),
    ("a row command fires from the bar", check_a_row_command_fires_from_the_bar),
    (
        "window-mastered leaves an unowned child",
        check_mastering_on_the_window_makes_an_unowned_child,
    ),
    ("child-mastered stays off the window", check_mastering_on_a_child_keeps_it_off_the_window),
    ("a BaseWidget can own a menu", check_a_basewidget_can_own_a_menu),
    ("a wrapped menu offers no geometry", check_a_wrapped_menu_offers_no_geometry),
    ("a wrapped menu evicts itself", check_a_wrapped_menu_evicts_itself),
    ("the install can be verified", check_the_install_can_be_verified),
    ("ismapped lies about a visible bar", check_ismapped_lies_about_a_visible_bar),
    ("a binding delivers the clone's path", check_a_binding_delivers_the_unreachable_clone),
    ("destroy is heard for the submenu too", check_the_destroy_binding_hears_the_submenu_too),
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
