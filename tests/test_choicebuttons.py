""":class:`~tkfacade.ChoiceButtons`: choosing, presented as a bank of buttons.

The same contract :class:`~tkfacade.ChoiceBox` holds — one value from a
set, in a shared observable, the worn :class:`~tkfacade.ChoiceSet` —
drawn as the set itself: one themed radiobutton per option, handed back
as handles. What is tested here is what the bank adds — its members,
their commands, its one transport ride, its axis — plus the shared
domain rule, asserted once against the family's wording rather than
re-derived.
"""

import asyncio
import threading

import pytest

import tkfacade
from conftest import RunMainloop

pytestmark = pytest.mark.gui

SIZES = ("Small", "Medium", "Large")


def test_construction_options_round_trip(window: tkfacade.Window) -> None:
    """options, chosen, orient, and enabled land at construction and read back."""
    bank = tkfacade.ChoiceButtons(window, SIZES, chosen="Medium", orient="horizontal")

    assert bank.options == SIZES
    assert bank.chosen == "Medium"
    assert bank.orient == "horizontal"
    assert bank.enabled is True

    off = tkfacade.ChoiceButtons(window, SIZES, enabled=False)

    assert off.enabled is False
    assert off.chosen == tkfacade.NOTHING_CHOSEN


def test_an_empty_bank_is_refused_before_anything_is_built(window: tkfacade.Window) -> None:
    """A set with no options is not a set, and nothing half-built is left.

    The same refusal, in the same words, as the menu's insert_choices — the set is the unit in every presentation, and unlike the choice box there is no later options assignment that could fill an empty bank. The children comparison is the no-half-built check: the raise fires before the frame exists, so the window's child list is untouched.
    """
    children_before = tuple(window.children)

    with pytest.raises(ValueError, match="at least one option"):
        tkfacade.ChoiceButtons(window, ())

    assert tuple(window.children) == children_before


def test_the_domain_is_the_one_the_family_enforces(window: tkfacade.Window) -> None:
    """A nonsense value raises at construction and at ``chosen`` alike.

    One rule for the whole family, not re-derived here: check_option is what ChoiceBox and ChoiceSpinner already enforce, so the assertion is that this presentation reaches the same rule, message included. The tail is the documented escape — a write straight to the observable bypasses the check, and Tk draws no button chosen, the same shape a stale choice has in the box.
    """
    with pytest.raises(ValueError, match="not one of the options"):
        tkfacade.ChoiceButtons(window, SIZES, chosen="XL")

    bank = tkfacade.ChoiceButtons(window, SIZES)

    with pytest.raises(ValueError, match="not one of the options"):
        bank.chosen = "XL"

    bank.chosen_observable.value = "XL"

    assert bank.chosen == "XL"
    assert not any(button.chosen for button in bank.buttons)


def test_the_shared_observable_carries_the_choice(window: tkfacade.Window) -> None:
    """Choosing writes the observable, and driving it moves the bank.

    Both directions, through the vocabulary the family reserved for exactly this widget: one shared ObservableStr, adopted rather than made when given, with choose() the member-side write the menu's choice rows already offer. Both routes are driven because each is the other's regression: a bank that only read the observable would pass the second half, one that only wrote it the first.
    """
    shared = tkfacade.ObservableStr("Small")
    bank = tkfacade.ChoiceButtons(window, SIZES, chosen=shared)
    small, medium, large = bank.buttons

    assert (small.chosen, medium.chosen, large.chosen) == (True, False, False)

    large.choose()

    assert shared.value == "Large"
    assert (small.chosen, medium.chosen, large.chosen) == (False, False, True)

    shared.value = "Medium"

    assert bank.chosen == "Medium"
    assert medium.chosen is True


def test_member_handles_carry_their_own_faces(window: tkfacade.Window) -> None:
    """text, enabled, and value are each button's own; text may leave value.

    The handle surface mirrors ChoiceRow name for name, and the text/value split is what the menu set cannot do at construction: renaming what is drawn moves nothing, because the value is the identity. The bank-level enabled reads all-and-writes-all — one disabled member answers False for the bank, and the bank's True brings it back with the rest — which is asserted here rather than documented only.
    """
    bank = tkfacade.ChoiceButtons(window, SIZES)
    small = bank.buttons[0]

    assert small.value == small.text == "Small"

    small.text = "Petite"
    small.enabled = False

    assert small.text == "Petite"
    assert small.value == "Small"
    assert small.enabled is False
    assert bank.enabled is False
    assert bank.options == SIZES

    bank.enabled = True

    assert small.enabled is True


def test_a_members_command_runs_holds_and_swaps(window: tkfacade.Window) -> None:
    """Invoking chooses and runs the command, which swaps by assignment.

    The constructor's one command is copied into every member, exactly as insert_choices copies it into every row, and each member's is independently swappable afterwards — the last assertion pins that a swap on one member left its sibling's in place. invoke() drives the real ttk route, so the command fires as a click would, after the variable write.
    """
    runs: list[str] = []
    bank = tkfacade.ChoiceButtons(window, SIZES, command=lambda: runs.append("first"))
    small = bank.buttons[0]

    small.invoke()

    assert bank.chosen == "Small"
    assert runs == ["first"]

    small.command = lambda: runs.append("second")
    small.invoke()

    assert runs == ["first", "second"]
    assert bank.buttons[1].command is not None


def test_a_coroutine_command_runs_on_the_core(
    window: tkfacade.Window, run_mainloop: RunMainloop
) -> None:
    """A coroutine function as a button's command is scheduled off-thread.

    The dual-kind command (a plain callable or a coroutine function), through the same dispatch the button family and the menu rows use: a coroutine function runs on the root's core, off the mainloop, fire-and-forget.
    """
    main = threading.get_ident()
    ran_on: list[int] = []
    done = threading.Event()

    async def command() -> None:
        await asyncio.sleep(0)
        ran_on.append(threading.get_ident())
        done.set()

    bank = tkfacade.ChoiceButtons(window, SIZES, command=command)
    bank.grid(row=0, column=0)
    window._tk.after(0, bank.buttons[0].invoke)
    run_mainloop(window, done)

    assert len(ran_on) == 1
    assert ran_on[0] != main


def test_destroying_the_bank_gives_back_its_one_transport(window: tkfacade.Window) -> None:
    """A destroyed bank stops riding its shared observable, exactly once.

    The teardown half, with the bank's one wrinkle: N buttons share one transport acquisition — every Radiobutton is handed the same variable — so one release settles the whole account. The observable dropping its transport proves the count balanced; a per-button acquisition with a single release would leave it pinned.
    """
    shared = tkfacade.ObservableStr("Small")
    bank = tkfacade.ChoiceButtons(window, SIZES, chosen=shared)
    attached = shared._var is not None

    bank.destroy()
    window._tk.update()

    assert attached
    assert shared._var is None


def test_the_axis_relays_the_bank(window: tkfacade.Window) -> None:
    """orient re-grids every button along the new axis.

    The axis is pure layout — TRadiobutton has no Horizontal./Vertical. style halves — so what is asserted is the grid itself, read from the buttons' own info. The whole layout is rewritten on assignment because grid merges: stale cells from the old axis must be forgotten, and the zeroed row list is what proves they were.
    """
    bank = tkfacade.ChoiceButtons(window, SIZES, orient="vertical")
    rows = [int(button._tk_button.grid_info()["row"]) for button in bank.buttons]

    assert rows == [0, 1, 2]

    bank.orient = "horizontal"
    columns = [int(button._tk_button.grid_info()["column"]) for button in bank.buttons]
    rows = [int(button._tk_button.grid_info()["row"]) for button in bank.buttons]

    assert columns == [0, 1, 2]
    assert rows == [0, 0, 0]
