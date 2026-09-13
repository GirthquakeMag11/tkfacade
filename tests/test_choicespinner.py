""":class:`~tkfacade.ChoiceSpinner`: choosing, presented as a step-through.

The same contract :class:`~tkfacade.ChoiceBox` holds — one value from a
set, in a shared observable — reached by arrows instead of a dropdown.
What is tested here is the stepping and the shared domain rule, since
the two presentations enforce one rule rather than two copies of it.
"""

import pytest

import tkfacade

pytestmark = pytest.mark.gui

SIZES = ("Small", "Medium", "Large")


def test_stepping_walks_the_options_and_stops_at_the_ends(window: tkfacade.Window) -> None:
    """Each step moves one option, and the ends hold.

    The movement contract: one option per step, and both ends hold rather than wrapping or overshooting. The extra press at the top is what makes it a claim about stopping, and stepping below the first option is the other end of the same claim.
    """
    spinner = tkfacade.ChoiceSpinner(window, SIZES, chosen="Small")
    spinner.grid(row=0, column=0)
    window._tk.update()

    spinner.step_up()
    window._tk.update()
    stepped = spinner.chosen

    spinner.step_up()
    spinner.step_up()
    window._tk.update()
    at_the_end = spinner.chosen

    spinner.chosen = "Small"
    spinner.step_down()
    window._tk.update()

    assert stepped == "Medium"
    assert at_the_end == "Large"
    assert spinner.chosen == "Small"


def test_wrapping_cycles_through_the_options(window: tkfacade.Window) -> None:
    """With wraps set, stepping past an end lands on the other.

    A small set is exactly where wrapping earns its place — three sizes are quicker to cycle than to walk back through — which is why the option exists here at all. Asserted in both directions so a wrap implemented one way round fails.
    """
    spinner = tkfacade.ChoiceSpinner(window, SIZES, chosen="Large", wraps=True)
    spinner.grid(row=0, column=0)
    window._tk.update()

    spinner.step_up()
    window._tk.update()
    over_the_top = spinner.chosen

    spinner.step_down()
    window._tk.update()

    assert over_the_top == "Small"
    assert spinner.chosen == "Large"
    assert spinner.wraps is True


def test_the_domain_is_the_one_the_choice_box_enforces(window: tkfacade.Window) -> None:
    """A value outside the options is refused, at both doors.

    One rule, not two copies of it: this raises through the same function the choice box raises through, which is the point of the two living in one package. Witnessed on ttk, a spinbox accepts any value handed to it whether listed or not — set('Enormous') displays it and the next step silently jumps to the first option — so the domain is the facade's to keep here exactly as it is there.
    """
    with pytest.raises(ValueError, match="not one of the options"):
        tkfacade.ChoiceSpinner(window, SIZES, chosen="Enormous")

    spinner = tkfacade.ChoiceSpinner(window, SIZES, chosen="Medium")
    with pytest.raises(ValueError, match="not one of the options"):
        spinner.chosen = "Enormous"

    assert spinner.chosen == "Medium"


def test_nothing_chosen_is_a_real_state(window: tkfacade.Window) -> None:
    """A spinner starts with no choice made, and stepping leaves it.

    The form-before-anyone-answered-it state the choice box also starts in, and the one behaviour the two presentations cannot share: a dropdown simply shows nothing selected, while a spinner has to land somewhere on the first press. Asserting membership rather than a particular option keeps this a claim about leaving the empty state rather than about which end Tk starts from.
    """
    spinner = tkfacade.ChoiceSpinner(window, SIZES)
    spinner.grid(row=0, column=0)
    window._tk.update()
    at_first = spinner.chosen

    spinner.step_up()
    window._tk.update()

    assert at_first == tkfacade.NOTHING_CHOSEN
    assert spinner.chosen in SIZES


def test_the_command_runs_for_a_step_and_not_for_a_write(window: tkfacade.Window) -> None:
    """Tk fires the command for the arrows only.

    The user-only channel, the same one the numeric spinboxes get and for the same reason: ttk fires a spinbox's command for a step and for nothing else. Both write routes are exercised before the step, since the property and the shared observable reach the widget by different paths and either could have fired it.
    """
    ran: list[str] = []
    spinner = tkfacade.ChoiceSpinner(
        window, SIZES, chosen="Small", command=lambda: ran.append("stepped")
    )
    spinner.grid(row=0, column=0)
    window._tk.update()

    spinner.chosen = "Large"
    spinner.chosen_observable.value = "Medium"
    window._tk.update()
    after_writes = list(ran)

    spinner.step_up()
    window._tk.update()

    assert after_writes == []
    assert ran == ["stepped"]


def test_the_choice_survives_a_replaced_option_set(window: tkfacade.Window) -> None:
    """A reloaded list does not clear or refuse a choice that is now absent.

    The rule the choice box states, holding here too because the two share it: reloading a set of options is ordinary and must not raise because the old choice is gone, so the stale choice survives. The raise at the end proves the new domain took effect — the old options are gone for checking as well as for stepping.
    """
    spinner = tkfacade.ChoiceSpinner(window, SIZES, chosen="Medium")

    spinner.options = ("Tall", "Grande")

    assert spinner.options == ("Tall", "Grande")
    assert spinner.chosen == "Medium"

    with pytest.raises(ValueError, match="not one of the options"):
        spinner.chosen = "Small"


def test_destroying_the_spinner_gives_back_its_transport(window: tkfacade.Window) -> None:
    """A destroyed spinner stops riding its shared observable.

    The teardown half: the transport ride goes back so a shared observable never pins a dead interpreter through a widget that took one and never gave it back (`hazards/tkinter.md`, *Variables*).
    """
    shared = tkfacade.ObservableStr("Small")
    spinner = tkfacade.ChoiceSpinner(window, SIZES, chosen=shared)
    attached = shared._var is not None

    spinner.destroy()
    window._tk.update()

    assert attached
    assert shared._var is None
