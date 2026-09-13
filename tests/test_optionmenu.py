""":class:`~tkfacade.OptionMenu`: choosing, worn as a menubutton's label.

The same contract every :class:`~tkfacade.ChoiceSet` wearer holds — one
value from a set, in a shared observable, under the family's one domain
rule — presented the way ttk's own option menu presents it: a
:class:`~tkfacade.Menubutton` seeded with choice rows, its text the
chosen value. What is tested here is what the wrapper adds: the label
tracking every route a choice can take, the seeding order, and the
refusals firing before the button exists.
"""

import pytest

import tkfacade

pytestmark = pytest.mark.gui

SIZES = ("Small", "Medium", "Large")


def test_construction_options_round_trip(window: tkfacade.Window) -> None:
    """options, chosen, direction, and enabled land, and the label shows the choice.

    In one pass, plus the widget's defining claim: the label is the chosen value from birth, painted by the watch's immediate first call — an empty button for nothing chosen rather than a placeholder the value never was.
    """
    picker = tkfacade.OptionMenu(window, SIZES, chosen="Medium", direction="right")

    assert picker.options == SIZES
    assert picker.chosen == "Medium"
    assert picker.text == "Medium"
    assert picker.direction == "right"
    assert picker.enabled is True

    bare = tkfacade.OptionMenu(window, SIZES, enabled=False)

    assert bare.enabled is False
    assert bare.chosen == tkfacade.NOTHING_CHOSEN
    assert bare.text == ""


def test_the_label_tracks_every_route_a_choice_takes(window: tkfacade.Window) -> None:
    """A row's choose, the chosen setter, and a raw observable write all repaint.

    The label rides the observable, not the domain: the bypass route the whole family documents moves the text too, and no row claims an unlisted value. Three write routes are driven because each is the others' regression — a textvariable-free label that repainted only on choose() would pass the first leg alone.
    """
    picker = tkfacade.OptionMenu(window, SIZES)

    picker.rows[0].choose()
    assert (picker.chosen, picker.text) == ("Small", "Small")

    picker.chosen = "Large"
    assert picker.text == "Large"

    picker.chosen_observable.value = "XL"
    assert picker.text == "XL"
    assert not any(row.chosen for row in picker.rows)


def test_the_domain_is_the_one_the_family_enforces(window: tkfacade.Window) -> None:
    """Nonsense raises at construction and at ``chosen``, in the shared words."""
    with pytest.raises(ValueError, match="not one of the options"):
        tkfacade.OptionMenu(window, SIZES, chosen="XL")

    picker = tkfacade.OptionMenu(window, SIZES)

    with pytest.raises(ValueError, match="not one of the options"):
        picker.chosen = "XL"


def test_an_empty_set_is_refused_before_anything_is_built(window: tkfacade.Window) -> None:
    """No options is no option menu, and nothing half-built is left behind.

    The refusal must fire before Menubutton.__init__ runs, because that is where the wrapper registers: validated after, a raise would leave a registered, unreachable button — the half-built-registrant fault a known issue recorded against ImageDisplay. The child comparison is the observable half of that claim.
    """
    children_before = tuple(window.children)

    with pytest.raises(ValueError, match="at least one option"):
        tkfacade.OptionMenu(window, ())

    assert tuple(window.children) == children_before


def test_the_face_is_worn_and_the_observable_shares(window: tkfacade.Window) -> None:
    """An option menu is a ChoiceSet, and its observable feeds a sibling.

    The unification claim, asserted rather than narrated: one shared ObservableStr is the whole of what the presentations have in common, so handing the option menu's own observable to a choice box makes a pick in one the value of both.
    """
    picker = tkfacade.OptionMenu(window, SIZES, chosen="Small")

    assert isinstance(picker, tkfacade.ChoiceSet)
    assert isinstance(picker, tkfacade.Menubutton)

    box = tkfacade.ChoiceBox(window, SIZES, chosen=picker.chosen_observable)
    picker.rows[2].choose()

    assert box.chosen == "Large"


def test_a_rows_command_fires_and_swaps(window: tkfacade.Window) -> None:
    """The seeded rows carry the family's command machinery."""
    runs: list[str] = []
    picker = tkfacade.OptionMenu(window, SIZES, command=lambda: runs.append("first"))
    small = picker.rows[0]

    small.invoke()
    assert (picker.chosen, runs) == ("Small", ["first"])

    small.command = None
    small.invoke()
    assert runs == ["first"]


def test_the_menu_stays_extendable_behind_the_choices(window: tkfacade.Window) -> None:
    """The seeded rows come first; inherited inserts append after them.

    The posture the class body states: an option menu is still a menubutton, its menu reachable and extendable as tkinter's own is. The indices pin the seeding order — choices first, additions after — with the separator's bare seat holding position 3.
    """
    picker = tkfacade.OptionMenu(window, SIZES)
    picker.insert_separator()
    extra = picker.insert_command("Refresh sizes")

    assert [row.index for row in picker.rows] == [0, 1, 2]
    assert extra.index == 4
