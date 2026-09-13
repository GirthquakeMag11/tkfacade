""":class:`~tkfacade.Combobox`: a text input that suggests.

The editable half of ttk's combobox. What is under test is the half
that is *not* Entry's — the suggestions constraining nothing, the
selection event, the rows — plus the one clause of the inherited text
contract this widget answers differently, which is the whole reason it
is a separate class from :class:`~tkfacade.ChoiceBox`.
"""

import pytest

import tkfacade

pytestmark = pytest.mark.gui

COLOURS = ("red", "green", "blue")


def test_it_is_an_entry_and_answers_the_inherited_contract(window: tkfacade.Window) -> None:
    """Everything Entry offers works, the widget underneath being one.

    The reuse this widget exists to prove: ttk.Combobox is a ttk.Entry, so every member our Entry defines operates on it unchanged and the subclass adds a dropdown rather than reimplementing an input. Tested whole, inherited members included — the inherited half is the half that breaks quietly when a base changes underneath.
    """
    box = tkfacade.Combobox(window, "written", suggestions=COLOURS)

    assert box.text == "written"
    assert box.is_empty is False
    box.text = "typed over"
    assert box.text == "typed over"
    box.select_all()
    assert box.selection == "typed over"
    assert box.copy_selection() == "typed over"
    box.select_none()
    assert box.selection == ""


def test_the_suggestions_constrain_nothing(window: tkfacade.Window) -> None:
    """A value outside the suggestions is accepted, because they only suggest.

    The distinction that splits this widget from ChoiceBox, asserted rather than described: the list offers, it does not bind. Replacing the list leaves the content alone for the same reason — it never had to be among them, so there is nothing for the replacement to invalidate.
    """
    box = tkfacade.Combobox(window, suggestions=COLOURS)

    box.text = "puce"

    assert box.text == "puce"
    assert box.suggestions == COLOURS

    box.suggestions = ("cyan", "magenta")

    assert box.text == "puce"
    assert box.suggestions == ("cyan", "magenta")


def test_a_dropdown_with_no_rows_is_refused(window: tkfacade.Window) -> None:
    """visible_rows below one is rejected at both doors.

    The refusal of what Tk would take and act on wrongly: a height of zero builds a dropdown that opens onto nothing, with no error and no way for a user to pick. Both doors a value comes in by are closed, and the untouched reading proves the raise landed before the write.
    """
    with pytest.raises(ValueError, match="at least 1"):
        tkfacade.Combobox(window, visible_rows=0)

    box = tkfacade.Combobox(window, suggestions=COLOURS)
    with pytest.raises(ValueError, match="at least 1"):
        box.visible_rows = 0

    assert box.visible_rows == 10


def test_disabling_locks_out_the_dropdown_as_well_as_the_keyboard(
    window: tkfacade.Window,
) -> None:
    """disable() turns the widget off, not merely read-only.

    The exemption the class body records, pinned so it cannot drift. Entry's read-only mode is ttk's `readonly` state, and on a combobox that state leaves the dropdown live — a "read-only" combobox would still have its value changed by the user, which is the larger of the two promises the text contract makes. So this widget uses ttk's `disabled` instead and gives up focus traversal, which is the clause it cannot keep. The assignment while off pins the half it does keep: the program still writes.
    """
    box = tkfacade.Combobox(window, "start", suggestions=COLOURS)
    box.grid(row=0, column=0)
    window._tk.update()

    box.disable()
    window._tk.update()

    assert box.disabled is True
    assert box._tk.instate(["disabled"])
    assert not box._tk.instate(["readonly"])

    box.text = "assigned while off"
    assert box.text == "assigned while off"

    box.enable()
    assert box.disabled is False


def test_a_users_pick_is_announced_and_a_write_is_not(window: tkfacade.Window) -> None:
    """COMBOBOX_SELECTED fires for the dropdown only.

    The user-only channel, which the events vocabulary already carried before this widget existed. Tk fires it for a pick from the list and for nothing else, so it means on this widget exactly what `command` means on the button family — and a watcher on the observable is the other half, hearing every change whoever made it.
    """
    box = tkfacade.Combobox(window, suggestions=COLOURS)
    box.grid(row=0, column=0)
    window._tk.update()
    heard: list[str] = []
    box.bind(
        tkfacade.Virtual(tkfacade.VirtualEvent.COMBOBOX_SELECTED),
        lambda _event: heard.append(box.text),
    )

    box.text = "green"
    box.text_observable.value = "blue"
    window._tk.update()
    after_writes = list(heard)

    box._tk.event_generate("<<ComboboxSelected>>")
    window._tk.update()

    assert after_writes == []
    assert heard == ["blue"]
