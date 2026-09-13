""":class:`~tkfacade.Menubutton`: a button that reveals actions, and its menu.

The suite leans hardest on the two things the design exists for, because
they are exactly what row-by-text addressing cannot do: two rows of one
menu carrying the same words, and a handle that still names its own row
after rows above it are deleted. Both have a test of their own below, and
both fail against any facade that addresses entries by their labels.
"""

import asyncio
import threading
import tkinter as tk

import pytest

import tkfacade
from conftest import RunMainloop

pytestmark = pytest.mark.gui


def test_a_new_menubutton_has_an_empty_untorn_menu(window: tkfacade.Window) -> None:
    """It builds its own menu, and Tk's phantom tear-off row is not in it."""
    picker = tkfacade.Menubutton(window, "File")

    assert picker._parts == []
    # index("end") answers None for a truly empty menu, and 0 for one
    # carrying only the tear-off -- the hazard this guards against
    assert picker._tk_menu.index("end") is None
    assert str(picker._tk.cget("menu")) == str(picker._tk_menu)


def test_two_rows_of_one_menu_may_carry_the_same_text(window: tkfacade.Window) -> None:
    """The restriction text-addressing forces, which handles remove.

    Tk allows duplicate labels and answers ``index`` for the first of
    them only, so a facade addressing rows by text has to forbid this.
    """
    picker = tkfacade.Menubutton(window, "File")

    first = picker.insert_command("Open")
    second = picker.insert_command("Open")

    assert first is not second
    assert first.text == second.text == "Open"
    assert (first.index, second.index) == (0, 1)


def test_a_handle_survives_deletion_of_the_rows_above_it(window: tkfacade.Window) -> None:
    """An index held from creation would be stale; the handle is not."""
    picker = tkfacade.Menubutton(window, "File")
    first = picker.insert_command("alpha")
    second = picker.insert_command("beta")
    third = picker.insert_command("gamma")

    first.delete()

    assert first.deleted
    assert second.index == 0 and second.text == "beta"
    assert third.index == 1 and third.text == "gamma"
    assert len(picker._parts) == 2


def test_renaming_a_row_does_not_move_it(window: tkfacade.Window) -> None:
    """Text is drawn, not addressed, so renaming changes only what is drawn."""
    picker = tkfacade.Menubutton(window, "File")
    row = picker.insert_command("before")
    picker.insert_command("after")

    row.text = "after"

    assert row.index == 0
    assert row.text == "after"


def test_deleting_twice_is_not_an_error(window: tkfacade.Window) -> None:
    """A caller may drop a row without asking whether something else did."""
    picker = tkfacade.Menubutton(window, "File")
    row = picker.insert_command("go")

    row.delete()
    row.delete()

    assert row.deleted
    assert picker._parts == []


def test_a_deleted_row_refuses_to_name_a_position(window: tkfacade.Window) -> None:
    """Reading the index of a gone row raises rather than guessing."""
    picker = tkfacade.Menubutton(window, "File")
    row = picker.insert_command("go")
    row.delete()

    with pytest.raises(LookupError):
        _ = row.index


def test_a_command_row_runs_what_it_was_given(window: tkfacade.Window) -> None:
    """Invoking does what choosing does, and the command can be swapped."""
    picker = tkfacade.Menubutton(window, "File")
    runs: list[str] = []
    row = picker.insert_command("go", command=lambda: runs.append("first"))

    row.invoke()
    assert runs == ["first"]

    row.command = lambda: runs.append("second")
    row.invoke()
    assert runs == ["first", "second"]


def test_a_checkbox_row_carries_a_shared_observable(window: tkfacade.Window) -> None:
    """One tick can be a menu row and a checkbutton at once."""
    picker = tkfacade.Menubutton(window, "View")
    shared = tkfacade.ObservableBool(False)
    row = picker.insert_checkbox("Word wrap", checked=shared)
    box = tkfacade.Checkbutton(window, "Word wrap", checked=shared)

    row.checked = True

    assert shared.value is True
    assert box.checked is True

    box.checked = False

    assert row.checked is False


def test_a_choice_set_keeps_exactly_one_chosen(window: tkfacade.Window) -> None:
    """The set shares one observable, which is what makes it a set."""
    picker = tkfacade.Menubutton(window, "Theme")
    theme = tkfacade.ObservableStr("Dark")
    light, dark = picker.insert_choices(("Light", "Dark"), chosen=theme).rows

    assert (light.chosen, dark.chosen) == (False, True)

    light.choose()

    assert (light.chosen, dark.chosen) == (True, False)
    assert theme.value == "Light"

    theme.value = "Dark"

    assert (light.chosen, dark.chosen) == (False, True)


def test_the_answered_set_speaks_as_the_choice_family_does(window: tkfacade.Window) -> None:
    """insert_choices answers a set with the family's face on it.

    ``chosen`` reads and writes the value with the domain enforced, the
    observable is reachable back off the set, and a deleted row's value
    drops out of the domain.

    The set-level object the deleted Radiobutton's design implied and never named, answered here at last: the menu's choice rows arrive as a ChoiceSet like every other presentation, so the domain check the menu never had now guards its chosen too. The box built from the set's own observable is the sharing insert_choices used to demand up front — adopt-or-make plus a reachable observable replaces the required parameter without losing the shared-value story. The deletion tail pins options as a live read off the seated rows.
    """
    picker = tkfacade.Menubutton(window, "Theme")
    chosen = picker.insert_choices(("Light", "Dark"), chosen="Dark")

    assert isinstance(chosen, tkfacade.ChoiceSet)
    assert chosen.options == ("Light", "Dark")
    assert chosen.chosen == "Dark"

    chosen.chosen = "Light"

    assert chosen.rows[0].chosen is True

    with pytest.raises(ValueError, match="not one of the options"):
        chosen.chosen = "Grey"

    shared = chosen.chosen_observable
    box = tkfacade.ChoiceBox(window, ("Light", "Dark"), chosen=shared)

    assert box.chosen == "Light"

    chosen.rows[1].delete()
    remaining: tuple[str, ...] = chosen.options

    assert remaining == ("Light",)
    assert chosen.rows[1].deleted


def test_a_choice_set_of_nothing_is_refused(window: tkfacade.Window) -> None:
    """A set with no options is not a set."""
    picker = tkfacade.Menubutton(window, "Theme")

    with pytest.raises(ValueError, match="at least one option"):
        picker.insert_choices((), chosen=tkfacade.ObservableStr(""))

    assert picker._parts == []


def test_submenus_nest_to_any_depth(window: tkfacade.Window) -> None:
    """The same call at every level, and each is a row and a menu at once."""
    picker = tkfacade.Menubutton(window, "File")
    outer = picker.insert_submenu("Export")
    inner = outer.insert_submenu("Image")
    inner.insert_command("PNG")

    assert len(picker._parts) == len(outer._parts) == len(inner._parts) == 1
    # the row half: a submenu renames and disables itself
    outer.text = "Send to"
    outer.enabled = False

    assert outer.text == "Send to"
    assert outer.enabled is False
    assert inner.index == 0


def test_a_rule_holds_a_place_and_carries_nothing(window: tkfacade.Window) -> None:
    """A separator is a rule, not a row: nothing comes back for it.

    The seat it takes is a bare :class:`~tkfacade.MenuPart` held
    internally, so the rows around it still count it in their indices.
    """
    picker = tkfacade.Menubutton(window, "File")
    picker.insert_command("New")
    assert picker.insert_separator() is None  # type: ignore[func-returns-value]
    below = picker.insert_command("Quit")

    seat = picker._parts[1]
    assert type(seat) is tkfacade.MenuPart
    assert not isinstance(seat, tkfacade.CommandRow)
    assert seat.index == 1 and below.index == 2

    seat.delete()

    assert below.index == 1


def test_rows_can_be_put_at_a_position(window: tkfacade.Window) -> None:
    """Insertion counts positions the way a caller does, end included."""
    picker = tkfacade.Menubutton(window, "File")
    second = picker.insert_command("second")
    first = picker.insert_command("first", index=0)
    last = picker.insert_command("third", index=2)

    assert (first.index, second.index, last.index) == (0, 1, 2)
    assert (first.text, second.text, last.text) == ("first", "second", "third")


def test_a_position_outside_the_menu_is_refused(window: tkfacade.Window) -> None:
    """Refused before anything reaches Tk, so the menu is left as it was."""
    picker = tkfacade.Menubutton(window, "File")
    picker.insert_command("only")

    with pytest.raises(IndexError):
        picker.insert_command("nowhere", index=5)

    assert len(picker._parts) == 1


def test_clearing_empties_the_menu(window: tkfacade.Window) -> None:
    """Every entry goes, and the handles all report themselves gone."""
    picker = tkfacade.Menubutton(window, "File")
    rows = [picker.insert_command("one"), picker.insert_command("two")]
    picker.insert_separator()

    picker.clear()

    assert picker._parts == []
    assert all(row.deleted for row in rows)


def test_the_direction_round_trips_and_refuses_nonsense(window: tkfacade.Window) -> None:
    """Where the menu appears is a live property with Tk's own guard."""
    picker = tkfacade.Menubutton(window, "File")

    assert picker.direction == "below"

    picker.direction = "right"
    assert picker.direction == "right"

    with pytest.raises(tk.TclError, match="must be above, below"):
        picker.direction = "sideways"  # type: ignore[assignment]


def test_the_button_face_round_trips(window: tkfacade.Window) -> None:
    """Text and enabled read live, and enabled goes through state flags."""
    picker = tkfacade.Menubutton(window, "File", enabled=False)

    assert picker.text == "File"
    assert picker.enabled is False

    picker.text = "Edit"
    picker.enabled = True

    assert picker.text == "Edit"
    assert picker.enabled is True


def test_a_row_can_be_disabled_without_losing_anything(window: tkfacade.Window) -> None:
    """Enabled is Tk's state option on the entry, read live."""
    picker = tkfacade.Menubutton(window, "File")
    row = picker.insert_command("go", enabled=False)

    assert row.enabled is False

    row.enabled = True

    assert row.enabled is True


def test_the_menu_dies_with_its_button(window: tkfacade.Window) -> None:
    """The menu is a child of the button, so nothing outlives it."""
    picker = tkfacade.Menubutton(window, "File")
    picker.insert_command("go")
    menu = picker._tk_menu

    picker.destroy()

    assert not menu.winfo_exists()


def test_every_commanded_row_kind_holds_and_swaps_its_command(
    window: tkfacade.Window,
) -> None:
    """The command is held by the row, not swallowed by Tk at seating.

    Checkbox and choice rows used to forget their command at creation;
    every :class:`~tkfacade.CommandRow` kind now reads it back and swaps
    it, and the swap reaches the next invoke without re-seating.
    """
    picker = tkfacade.Menubutton(window, "File")
    runs: list[str] = []
    tick = picker.insert_checkbox("Tick", command=lambda: runs.append("tick"))
    (only,) = picker.insert_choices(
        ("only",), chosen=tkfacade.ObservableStr("only"), command=lambda: runs.append("choice")
    ).rows

    assert tick.command is not None and only.command is not None

    tick.invoke()
    only.invoke()
    assert runs == ["tick", "choice"]

    tick.command = lambda: runs.append("swapped")
    only.command = None
    tick.invoke()
    only.invoke()

    assert runs == ["tick", "choice", "swapped"]


def test_a_coroutine_command_runs_on_the_core(
    window: tkfacade.Window, run_mainloop: RunMainloop
) -> None:
    """A coroutine function as a row's command is scheduled off-thread.

    The same dual-kind command — a plain callable or a coroutine
    function — as the button family, through the same dispatch: a menu
    row's command may be a coroutine function, run on the root's core
    rather than the mainloop.
    """
    main = threading.get_ident()
    ran_on: list[int] = []
    done = threading.Event()

    async def command() -> None:
        await asyncio.sleep(0)
        ran_on.append(threading.get_ident())
        done.set()

    picker = tkfacade.Menubutton(window, "File")
    row = picker.insert_command("Fetch", command=command)
    picker.grid(row=0, column=0)
    window._tk.after(0, row.invoke)
    run_mainloop(window, done)

    assert len(ran_on) == 1
    assert ran_on[0] != main
