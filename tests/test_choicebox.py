""":class:`~tkfacade.ChoiceBox`: one value chosen from a set.

The chooser half of ttk's combobox, and deliberately not a text input.
What is under test is the domain Tk declines to enforce — a readonly
combobox accepts any value the program hands it — plus the shared
observable the menu's choice rows already speak, which is the
vocabulary a radiobutton group will inherit.
"""

import pytest

import tkfacade

pytestmark = pytest.mark.gui

COLOURS = ("red", "green", "blue")


def test_construction_options_round_trip(window: tkfacade.Window) -> None:
    """The options, the choice, and the enabled state land and read back live.

    The state surface read live from Tk. The enabled reading goes through the state flags rather than the option, because this widget's on state is ttk's `readonly` — the state that refuses the keyboard while leaving the dropdown live, which is what makes it a chooser at all.
    """
    box = tkfacade.ChoiceBox(window, COLOURS, chosen="green", visible_rows=4)

    assert box.options == COLOURS
    assert box.chosen == "green"
    assert box.visible_rows == 4
    assert box.enabled is True

    box.enabled = False

    assert box.enabled is False
    assert box._tk.instate(["disabled"])


def test_nothing_chosen_is_a_real_state(window: tkfacade.Window) -> None:
    """A box starts with no choice made, and that is not an error.

    A form's box before anyone has answered it, which Tk models as no row selected in the list. Returning to it has to be legal too, or a caller could clear every other field and not this one — so the no-choice value passes the domain check that every other non-option fails.
    """
    box = tkfacade.ChoiceBox(window, COLOURS)

    assert box.chosen == tkfacade.NOTHING_CHOSEN
    assert box.chosen == ""

    box.chosen = "red"
    assert box.chosen == "red"
    box.chosen = tkfacade.NOTHING_CHOSEN
    assert box.chosen == ""


def test_a_value_outside_the_options_is_refused(window: tkfacade.Window) -> None:
    """The domain Tk will not enforce is enforced here, at both doors.

    The whole reason this is a wrapper rather than a re-export. Witnessed on ttk: a readonly combobox with these three values accepts `set("puce")` and displays it as though it were an option, with `current()` reporting -1 to nobody. So the constraint is the facade's or it is nobody's, and it is applied at both doors a plain string comes in by. The unchanged choice proves the raise landed first.
    """
    with pytest.raises(ValueError, match="not one of the options"):
        tkfacade.ChoiceBox(window, COLOURS, chosen="puce")

    box = tkfacade.ChoiceBox(window, COLOURS, chosen="red")
    with pytest.raises(ValueError, match="not one of the options"):
        box.chosen = "puce"

    assert box.chosen == "red"


def test_the_shared_observable_carries_the_choice(window: tkfacade.Window) -> None:
    """The choice is an ObservableStr, watchable and shared.

    Both directions, and the vocabulary this widget deliberately did not coin: one shared ObservableStr holding whichever value is chosen is exactly what the menu's choice rows already use, and what a radiobutton group should use when it is designed. The widget's own display is read through Tk rather than through the wrapper, so an observable that agreed with itself but not with the screen would fail here.
    """
    shared = tkfacade.ObservableStr("blue")
    box = tkfacade.ChoiceBox(window, COLOURS, chosen=shared)
    seen: list[str] = []
    shared.watch(seen.append)

    box.chosen = "red"
    window._tk.update()

    assert shared.value == "red"
    assert str(box._tk.get()) == "red"

    shared.value = "green"
    window._tk.update()

    assert box.chosen == "green"
    assert seen == ["blue", "red", "green"]


def test_the_observable_route_bypasses_the_domain_check(window: tkfacade.Window) -> None:
    """Driving the shared observable reaches the widget unchecked, as documented.

    The seam pinned rather than left to be closed by accident. A shared observable belongs to whatever else holds it, so the box cannot police writes it never sees — the same escape the progress bars and the scales document, and the reason the check lives on the property rather than pretending to live on the value.
    """
    shared = tkfacade.ObservableStr("red")
    box = tkfacade.ChoiceBox(window, COLOURS, chosen=shared)

    shared.value = "puce"
    window._tk.update()

    assert box.chosen == "puce"


def test_replacing_the_options_leaves_the_choice_alone(window: tkfacade.Window) -> None:
    """A reloaded list does not clear or refuse a choice that is now absent.

    The rule the class docstring states, and the reason for it: reloading a set of options is ordinary, and refusing it because the old choice is gone would make the ordinary case raise. So the stale choice survives, shown with nothing selected — Tk's own current() == -1, which is the same state a fresh box is in. The raise at the end proves the *new* domain took effect: the old options are gone for checking as well as for choosing.
    """
    box = tkfacade.ChoiceBox(window, COLOURS, chosen="green")

    box.options = ("cyan", "magenta")

    assert box.options == ("cyan", "magenta")
    assert box.chosen == "green"
    assert box._tk.current() == -1

    with pytest.raises(ValueError, match="not one of the options"):
        box.chosen = "red"


def test_destroying_the_box_gives_back_the_transport(window: tkfacade.Window) -> None:
    """A destroyed box stops riding its shared observable.

    The teardown half: the transport ride goes back so a shared observable never pins a dead interpreter through a widget that took one and never gave it back (`hazards/tkinter.md`, *Variables*). The attachment is captured rather than asserted in place, since asserting it narrows the attribute and mypy then calls the later reading unreachable.
    """
    shared = tkfacade.ObservableStr("red")
    box = tkfacade.ChoiceBox(window, COLOURS, chosen=shared)
    attached = shared._var is not None

    box.destroy()
    window._tk.update()

    assert attached
    assert shared._var is None
