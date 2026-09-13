""":class:`~tkfacade.Menubar`: a window's top row of menus.

The suite leans on the things that separate a bar from every other
menu in the library. It refuses a command and a separator — a command
in a top row is indistinguishable from a menu, and a rule draws
nothing at all while still taking a position — and refusing each by
absence rather than by a raise is the whole reason
:class:`~tkfacade.MenuBase` splits from
:class:`~tkfacade.CommandMenu` and :class:`~tkfacade.RuledMenu`. And it
is a wrapper a caller cannot construct, reached only through the window
that built it — the same ownership shape `TreeRow` and `TreeColumn`
have, where a facade component's lifetime is held by its parent.

Everything the bar inherits from `MenuBase` is covered against a
menubutton in `test_menubutton.py`; what is repeated here is only what
the top row could plausibly break, since an inherited half is the half
that breaks quietly.
"""

import pytest

import tkfacade
from conftest import Pump
from tkfacade.window import Root

pytestmark = pytest.mark.gui


def test_a_window_built_without_one_has_no_bar(window: tkfacade.Window) -> None:
    """A bar reserves a strip of the window, so none is built unasked."""
    assert window.menubar is None


def test_a_window_built_with_one_has_an_empty_untorn_bar(root: Root) -> None:
    """The bar exists, holds nothing, and carries no phantom tear-off row."""
    window = tkfacade.Window(title="editor", menubar=True, root=root)
    bar = window.menubar

    assert bar is not None
    assert bar._parts == []
    # index("end") answers None for a truly empty menu and 0 for one
    # carrying only Tk's tear-off, so this distinguishes the two
    assert bar._tk_menu.index("end") is None


def test_the_bar_takes_no_separator_but_a_submenu_from_it_does(root: Root) -> None:
    """The one call the top row cannot honour is the one it does not offer.

    The refusal is structural, not a raise: `Menubar` wears `MenuBase` where `Menubutton` and `Submenu` wear `RuledMenu`. Asserting the absence rather than a `TclError` is the point — Tk accepts a separator in a menubar and silently draws nothing, so a wrapper that offered the call and raised would be promising an interface it refuses, which is what the deleted `Radiobutton` did. The submenu half of the test is what stops the refusal from spreading further than the top row.
    """
    window = tkfacade.Window(title="editor", menubar=True, root=root)
    bar = window.menubar
    assert bar is not None

    assert not hasattr(bar, "insert_separator")

    file = bar.insert_submenu("File")
    file.insert_command("New")
    file.insert_separator()

    assert type(file._parts[1]) is tkfacade.MenuPart


def test_two_top_row_menus_may_carry_the_same_text(root: Root) -> None:
    """Handles keep two menus distinct where Tk's own index cannot."""
    window = tkfacade.Window(title="editor", menubar=True, root=root)
    bar = window.menubar
    assert bar is not None

    first = bar.insert_submenu("Tools")
    second = bar.insert_submenu("Tools")

    assert first is not second
    assert first.text == second.text == "Tools"
    assert (first.index, second.index) == (0, 1)


def test_a_handle_survives_deletion_of_the_menus_left_of_it(root: Root) -> None:
    """An index held from creation would be stale; the handle is not."""
    window = tkfacade.Window(title="editor", menubar=True, root=root)
    bar = window.menubar
    assert bar is not None
    first = bar.insert_submenu("File")
    second = bar.insert_submenu("Edit")

    assert second.index == 1
    first.delete()

    assert first.deleted
    assert second.index == 0
    assert second.text == "Edit"


def test_the_bar_takes_no_command_but_a_submenu_from_it_does(root: Root) -> None:
    """A top-row command is indistinguishable from a menu, so the bar lacks the call.

    A command in a menubar's top row is drawn exactly like a menu, so the ruling blocks the affordance by absence: the bar wears MenuBase, and insert_command lives on CommandMenu beneath RuledMenu, where a menubutton and a submenu still have it. Asserting the absence rather than a TclError is the point — Tk seats a command in a menubar and draws it like a menu, so a wrapper that offered the call and raised would be promising an interface it refuses. The submenu half of the test is what stops the refusal from spreading further than the top row.
    """
    window = tkfacade.Window(title="editor", menubar=True, root=root)
    bar = window.menubar
    assert bar is not None

    assert not hasattr(bar, "insert_command")

    file = bar.insert_submenu("File")
    file.insert_command("New")

    assert type(file._parts[0]) is tkfacade.CommandRow


def test_the_window_shows_the_bars_own_menu(root: Root, pump: Pump) -> None:
    """The toplevel's menu option names the menu this bar wraps.

    Only the install is asserted, not that a strip is drawn. Tk does not show the menu it is given -- it clones it -- so the master answers `winfo_ismapped()` 0 while the bar is plainly on screen, and the clone carries a path `nametowidget` cannot resolve. Measuring the strip from the outside would work here and fail on macOS and Windows, where the menubar is native and no clone exists; that the strip appears at all is a fact about Tk, pinned in `experiments/menu_probe/`, not a fact about this wrapper.
    """
    window = tkfacade.Window(title="editor", width=400, height=300, menubar=True, root=root)
    bar = window.menubar
    assert bar is not None
    bar.insert_submenu("File")
    pump(window)

    assert str(window._tk["menu"]) == str(bar._tk_menu)


def test_the_bar_is_reachable_through_the_registry_and_leaves_it(root: Root) -> None:
    """It registers like any wrapper and evicts itself when its menu dies."""
    tkfacade.Window(title="spare", root=root)
    window = tkfacade.Window(title="editor", menubar=True, root=root)
    bar = window.menubar
    assert bar is not None
    name = str(bar).rsplit(".", 1)[-1]

    assert window.nametowrapper(name) is bar

    window.destroy()

    assert not bar._tk.winfo_exists()
    with pytest.raises(KeyError):
        window.nametowrapper(name)


def test_a_destroyed_bar_leaves_a_shared_observable_working(root: Root) -> None:
    """Tearing a window down does not take an observable a survivor still uses.

    Two windows are needed because the release has to be observed from something that outlives the bar. What this pins is the outcome, not the mechanism: removing the guard in `_give_back_transports` does not fail it, because `release_transport` documents extra releases as harmless, so the guard is tidiness about a count rather than the thing keeping the survivor working. The release firing at all is what matters, and it does not fire without the window subscription this test exercises.
    """
    tkfacade.Window(title="spare", root=root)
    doomed = tkfacade.Window(title="doomed", menubar=True, root=root)
    survivor = tkfacade.Window(title="survivor", root=root)
    shared = tkfacade.ObservableBool(False)
    bar = doomed.menubar
    assert bar is not None
    view = bar.insert_submenu("View")
    view.insert_checkbox("Wrap", checked=shared)
    box = tkfacade.Checkbutton(survivor, "Wrap", checked=shared)

    doomed.destroy()
    shared.value = True

    assert box.checked is True


def test_nothing_lays_the_bar_out(root: Root) -> None:
    """A menu is a toplevel in Tk's eyes, so containment does not arise."""
    window = tkfacade.Window(title="editor", menubar=True, root=root)
    bar = window.menubar

    assert bar is not None
    assert not hasattr(bar, "grid")
    assert not hasattr(bar, "pack")
    assert not hasattr(bar, "place")
