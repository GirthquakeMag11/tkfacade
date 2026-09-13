""":class:`~tkfacade.Listbox`: a themed list of strings.

Built on a ``ttk.Treeview`` rather than the classic ``tk.Listbox``,
which has no ttk style at all. The mutable-sequence contract is tested
whole, since almost all of it comes from the mixin and the mixin is
only as right as the five members underneath it.
"""

import pytest

import tkfacade

pytestmark = pytest.mark.gui

WORDS = ("alpha", "beta", "gamma", "delta")


def test_it_is_themed_and_shows_one_bare_column(window: tkfacade.Window) -> None:
    """The widget underneath is a themed tree showing only its tree column.

    The whole reason for the Treeview form: a classic tk.Listbox has no ttk style — Style().layout("TListbox") raises — so its look is per-widget colours and reliefs, which the facade forbids and no styling facade could reach. Asserting the class and the show option pins that this is the themed list rather than a tree wearing one column, which would leak headings and a column border.
    """
    box = tkfacade.Listbox(window, WORDS)
    box.grid(row=0, column=0)
    window._tk.update()

    assert box._treeview.winfo_class() == "Treeview"
    assert tuple(str(part) for part in box._treeview.cget("show")) == ("tree",)
    assert box._treeview.cget("columns") in ("", ())


def test_the_sequence_contract_holds_whole(window: tkfacade.Window) -> None:
    """Every member the MutableSequence mixin offers works on the widget.

    A contract tested whole, inherited members included. Nine of these members come free from the mixin and are only as correct as __len__, __getitem__, __setitem__, __delitem__ and insert underneath them — reverse in particular exercises __setitem__ and __getitem__ against each other, and pop exercises __delitem__ through a return value.
    """
    box = tkfacade.Listbox(window, WORDS)

    assert len(box) == 4
    assert box[0] == "alpha"
    assert box[-1] == "delta"
    assert list(box) == list(WORDS)
    assert "beta" in box
    assert box.index("gamma") == 2
    assert box.count("beta") == 1

    box.append("epsilon")
    box.insert(0, "zero")
    box.extend(("eta", "theta"))

    assert box[0] == "zero"
    assert box[-1] == "theta"

    assert box.pop() == "theta"
    box.remove("zero")
    box.reverse()

    assert list(box) == ["eta", "epsilon", "delta", "gamma", "beta", "alpha"]
    assert len(box) == 6

    box += ("iota", "kappa")
    assert list(box) == ["eta", "epsilon", "delta", "gamma", "beta", "alpha", "iota", "kappa"]
    assert list(reversed(box))[:2] == ["kappa", "iota"]

    box.clear()
    assert len(box) == 0
    assert list(box) == []


def test_items_can_be_replaced_by_index_and_by_slice(window: tkfacade.Window) -> None:
    """Assignment works for one item, for a span, and for an extended slice.

    Slices are where a MutableSequence is usually faked, so all three forms are exercised: a single index, a contiguous span that changes the length, and an extended slice that cannot. The raise is the contract's own rule — an extended slice takes exactly as many items as it names — and a widget that silently accepted the wrong count would leave the list and the screen disagreeing.
    """
    box = tkfacade.Listbox(window, WORDS)

    box[1] = "BETA"
    assert list(box) == ["alpha", "BETA", "gamma", "delta"]

    box[1:3] = ("one", "two", "three")
    assert list(box) == ["alpha", "one", "two", "three", "delta"]

    box[::2] = ("A", "B", "C")
    assert list(box) == ["A", "one", "B", "three", "C"]

    with pytest.raises(ValueError, match="extended slice"):
        box[::2] = ("only", "two")


def test_a_string_assigned_to_a_slice_is_one_item(window: tkfacade.Window) -> None:
    """A bare string does not spread one character per row.

    A list would spread the string into characters, and this deliberately does not: the items are strings, so a caller assigning one means one item. The departure from list's behaviour is worth a test precisely because it is a departure.
    """
    box = tkfacade.Listbox(window, WORDS)

    box[1:3] = "single"

    assert list(box) == ["alpha", "single", "delta"]


def test_deleting_by_index_and_by_slice(window: tkfacade.Window) -> None:
    """del removes one item or a span.

    The third of the five members, in both its forms, and the range check the sequence contract owes: an index past the end raises rather than quietly doing nothing, which is what a caller looping over a shrinking list depends on.
    """
    box = tkfacade.Listbox(window, WORDS)

    del box[0]
    assert list(box) == ["beta", "gamma", "delta"]

    del box[0:2]
    assert list(box) == ["delta"]

    with pytest.raises(IndexError):
        del box[5]


def test_selection_is_read_by_position_and_moved_by_the_verbs(
    window: tkfacade.Window,
) -> None:
    """The Tree vocabulary, keyed by index.

    The four verbs and the two readings, in the order a caller would reach for them. Reusing Tree's names rather than inventing is the point: a caller who knows one knows the other, and the only difference is that a position identifies an item here where a handle does there — necessary, because a list may hold the same string twice and a value is then not an identity. Every reading is taken before any is compared: asserting one tuple narrows the property's type, and mypy then calls each later reading unreachable.
    """
    box = tkfacade.Listbox(window, WORDS, selection_extended=True)
    box.grid(row=0, column=0)
    window._tk.update()

    unselected = box.selection
    box.select(0, 2)
    replaced, items = box.selection, box.selected_items
    box.add_to_selection(3)
    added = box.selection
    box.remove_from_selection(0)
    removed = box.selection
    box.toggle_selection(0, 2)
    toggled = box.selection

    assert unselected == ()
    assert replaced == (0, 2)
    assert items == ("alpha", "gamma")
    assert added == (0, 2, 3)
    assert removed == (2, 3)
    assert toggled == (0, 3)


def test_selection_answers_in_list_order(window: tkfacade.Window) -> None:
    """Positions come back ordered by the list, not by when they were picked.

    The promise both readings make. Tk answers a treeview's selection in its own walk order, so the wrapper sorts by position rather than passing that through — a caller zipping selection against selected_items would otherwise pair the wrong ones.
    """
    box = tkfacade.Listbox(window, WORDS, selection_extended=True)
    box.grid(row=0, column=0)
    window._tk.update()

    box.select(3, 1, 0)

    assert box.selection == (0, 1, 3)
    assert box.selected_items == ("alpha", "beta", "delta")


def test_a_single_selection_list_holds_only_one(window: tkfacade.Window) -> None:
    """Without extended selection, selecting replaces rather than adds.

    The two construction booleans Tree also takes, folded to Tk's one selectmode word by the helper both widgets now share. The default is single selection, which is what a list used as a chooser wants and what tk.Listbox itself defaults to.
    """
    box = tkfacade.Listbox(window, WORDS)
    box.grid(row=0, column=0)
    window._tk.update()

    assert box.selection_extended is False
    assert box.selection_enabled is True

    box.select(0)
    box.select(2)

    assert box.selection == (2,)


def test_a_selection_change_is_read_back_and_announced(window: tkfacade.Window) -> None:
    """A selection made the widget's own way is both readable and announced.

    Selection made the way a user makes it, read back through the facade and announced through it. The notification half was withheld when this widget landed, the composite routing defect meaning no subscriber could hear an event fired by the widget inside the frame; the documented repair, and this is the test it turned green.
    """
    box = tkfacade.Listbox(window, WORDS)
    box.grid(row=0, column=0)
    window._tk.update()
    heard: list[tuple[str, ...]] = []
    box.bind(
        tkfacade.Virtual(tkfacade.VirtualEvent.TREEVIEW_SELECT),
        lambda _event: heard.append(box.selected_items),
    )

    box._treeview.selection_set(box._treeview.get_children("")[1])
    window._tk.update()

    assert box.selection == (1,)
    assert box.selected_items == ("beta",)
    assert heard == [("beta",)]


def test_it_scrolls_through_the_inherited_navigation(window: tkfacade.Window) -> None:
    """A long list navigates by the scrollable contract, not its own.

    What inheriting AbstractScrollable buys, asserted rather than assumed: the frame, the gutter bar and the four-direction navigation all arrive without this widget defining any of them, exactly as they do for Tree and TextBox. The generator argument is deliberate — items is an Iterable, so a caller need not build a list first.
    """
    box = tkfacade.Listbox(window, (f"item {index}" for index in range(200)), height=5)
    box.grid(row=0, column=0)
    window._tk.update()

    assert len(box) == 200
    assert box.can_scroll_down
    box.scroll_down(3)
    window._tk.update()

    assert box.y_offset > 0.0
