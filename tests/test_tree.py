""":class:`~tkfacade.Tree` with the :class:`TreeRow` and :class:`TreeColumn` views over it.

Rows and columns are live handles — keyed by iid and by name — so the
contracts under test are about what a handle observes through the
widget: converted cell values, tag order, structural moves,
detachment, and deletion. Every tree lives on the ``window`` fixture
and the suite carries the ``gui`` marker.
"""

import asyncio
import io
import itertools
import threading
import tkinter as tk

import pytest
from PIL import Image

import tkfacade
from conftest import RunMainloop
from tkfacade.tree import TreeColumnSpec

pytestmark = pytest.mark.gui


def _png() -> bytes:
    """An 8x8 solid red PNG, as encoded bytes."""
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (255, 0, 0)).save(buffer, format="PNG")
    return buffer.getvalue()


def _image_name(answer: object) -> str:
    """The Tk image name in an ``item``/``heading`` answer; ``""`` when unset.

    Args:
        answer (object): What Tk gave back for an ``image`` option — a
            one-element tuple while an image is set, a bare ``""``
            once it is cleared.

    Returns:
        The image's name, or ``""`` when none is set.
    """
    return str(answer[0]) if isinstance(answer, tuple) else str(answer)


def _raw(row: tkfacade.TreeRow) -> dict[str, str]:
    """Read ``row``'s cells straight off the Treeview, bypassing converters.

    Args:
        row (tkfacade.TreeRow): The row to read.

    Returns:
        The cells as Tk stores them, keyed by column name; empty once
        the row is gone.
    """
    return dict(row.tree._treeview.set(row.iid))


def _inventory(window: tkfacade.Window) -> tkfacade.Tree:
    """A tree with a plain ``item`` column and an int-converted ``count``.

    Args:
        window (tkfacade.Window): The window to build the tree in.

    Returns:
        The empty, two-column tree.
    """
    return tkfacade.Tree(
        window,
        columns=(
            TreeColumnSpec(name="item"),
            TreeColumnSpec(name="count", incoming_converter=str, outgoing_converter=int),
        ),
    )


def test_another_trees_row_is_a_stranger_here(window: tkfacade.Window) -> None:
    """Membership and cell lookup refuse a row of a different tree with the same iid.

    Tk generates the same I001, I002, … names in every tree, and both lookup paths degraded a row to its bare iid without asking whose it was — so a guard like ``row in target`` answered True for a stranger and a column write through the foreign handle silently corrupted the same-iid row of the wrong tree. The equal-iids assertion pins the collision this test exists to produce, the write is driven as well as the read because the write was the corrupting half, and the final read pins that this tree's own handle still resolves through the tightened path.
    """
    ours = _inventory(window)
    theirs = _inventory(window)
    our_row = ours.insert(item="bolt", count=1)
    their_row = theirs.insert(item="nut", count=2)
    assert our_row.iid == their_row.iid

    column = ours.column("item")
    assert column is not None
    assert their_row not in ours
    assert their_row not in column
    with pytest.raises(KeyError):
        column[their_row]
    with pytest.raises(KeyError):
        column[their_row] = "clobber"
    assert column[our_row] == "bolt"


def test_the_mutators_refuse_another_trees_row(window: tkfacade.Window) -> None:
    """Every row-taking mutator raises ``KeyError`` for a foreign handle, changing nothing.

    The lookup fix (the test above) guarded membership and the column key path only; Tree._iid still degraded a foreign row to its bare iid, so t1.delete(row_of_t2) silently deleted t1's same-iid row — the most destructive call sites kept exactly the hazard the lookup fix names. Every mutator funnelling through _iid is driven in one sweep because the fix lives in that funnel: a single call site bypassing it (say a future delete taking iids directly) is the regression this loop would catch. walk is forced through list() because it is a generator — its refusal only fires on first iteration. The final length and selection reads pin that the refusals really were refusals, not raises after the deed.
    """
    ours = _inventory(window)
    theirs = _inventory(window)
    our_row = ours.insert(item="bolt", count=1)
    their_row = theirs.insert(item="nut", count=2)
    assert our_row.iid == their_row.iid

    for mutate in (
        ours.delete,
        ours.detach,
        ours.reattach,
        ours.move,
        ours.select,
        ours.add_to_selection,
        ours.remove_from_selection,
        ours.toggle_selection,
        ours.see,
        lambda row: list(ours.walk(row)),
        lambda row: ours.insert(parent=row),
        lambda row: setattr(ours, "focus", row),
    ):
        with pytest.raises(KeyError):
            mutate(their_row)

    assert len(ours) == 1
    assert ours.selection == ()


def test_a_tree_refuses_all_columns_hidden(window: tkfacade.Window) -> None:
    """Declaring every column hidden raises at construction, as ``hide_column`` would.

    The zero-displayed state is exactly what hide_column exists to forbid ("Tk requires at least one") but construction bypassed the guard: Tk accepted displaycolumns=(), reported it back as the empty string, displayed_columns normalized that into a phantom column named '', and show_column choked on the phantom for every column, forever — a tree no wrapper call could ever unwedge. Each spec is individually legal, which is why the refusal must read the set whole; the match string ties the message to the invariant's existing wording.
    """
    with pytest.raises(ValueError, match="at least one"):
        tkfacade.Tree(
            window,
            columns=(
                TreeColumnSpec(name="a", displayed=False),
                TreeColumnSpec(name="b", displayed=False),
            ),
        )


def test_a_tree_refuses_duplicate_column_names(window: tkfacade.Window) -> None:
    """Two specs sharing a name raise at construction, as ``add_column`` would.

    add_column refuses a name the tree already has, but construction was the other door with no check on it: Tk itself accepts columns=('a', 'a') and builds two on-screen columns behind one name, so a cell write split them (('x', 'y')) while the mapping face showed one key and every per-name registration collapsed onto it. Two identical minimal specs are the whole shape — nothing but the name collision distinguishes them, so nothing else can be what the refusal reads.
    """
    with pytest.raises(ValueError, match="declared twice"):
        tkfacade.Tree(
            window,
            columns=(TreeColumnSpec(name="a"), TreeColumnSpec(name="a")),
        )


def test_a_default_factory_fires_only_for_inserts_that_use_it(window: tkfacade.Window) -> None:
    """An insert providing the column leaves its factory unconsulted."""
    counter = itertools.count(1)
    tree = tkfacade.Tree(
        window,
        columns=(TreeColumnSpec(name="n", default_factory=lambda: next(counter)),),
    )

    first = tree.insert()
    explicit = tree.insert(values={"n": 99})
    second = tree.insert()

    assert (first["n"], explicit["n"], second["n"]) == ("1", "99", "2")


def test_a_colliding_bound_name_is_refused_everywhere_it_could_land(
    window: tkfacade.Window,
) -> None:
    """A ``bound_name`` shadowing another column raises, at construction and add alike.

    A stateful factory is the canonical reason to prefer one over a plain default, and insert used to call every factory before looking at the caller's values — so the middle insert burned a counter value it never wrote, and the rows read 1, 99, 3. The written cells were always right, which is why only a sequence with an explicit-value insert in the middle can show the defect: the "2" is the whole assertion, the neighbours pin that covered inserts still draw from the factory in order. Strings because the tree's default converters stringify through Tk.
    """
    with pytest.raises(ValueError, match="another column's name"):
        tkfacade.Tree(
            window,
            columns=(
                TreeColumnSpec(name="b"),
                TreeColumnSpec(name="a", bound_name="b"),
            ),
        )
    with pytest.raises(ValueError, match="already bound"):
        tkfacade.Tree(
            window,
            columns=(
                TreeColumnSpec(name="a", bound_name="x"),
                TreeColumnSpec(name="b", bound_name="x"),
            ),
        )

    tree = tkfacade.Tree(window, columns=(TreeColumnSpec(name="a", bound_name="x"),))
    with pytest.raises(ValueError, match="already bound"):
        tree.add_column("x")

    assert [col.name for col in tree.columns] == ["a"]
    row = tree.insert(values={"x": "mine"})
    assert row["a"] == "mine"


def test_tree_answers_the_whole_collection_contract(window: tkfacade.Window) -> None:
    """``len`` and iteration speak for the attached rows; ``in`` for every row Tk holds.

    The whole of Collection, which is all Tree declares: no subscript, no mapping face, a row reached through Tree.row instead. Collection supplies no mixin methods, so the three dunders are the contract entire — and declaring it changes no behavior, which is the point: isinstance already answered True through Collection's structural subclasshook, and the declaration is what makes that an answer the class chose rather than one it happened to give. The detach is what separates the two halves: len and iteration drop the row while ``in`` keeps it, the asymmetry TreeColumn follows rather than inventing a third rule. A nested child is inserted so iteration order is pre-order rather than insertion order, and ``0 not in tree`` pins that a key of an unusable type is answered rather than raised.
    """
    tree = _inventory(window)
    parent = tree.insert(item="crate")
    child = parent.insert_child(item="bolt")
    loose = tree.insert(item="nut")

    assert len(tree) == 3
    assert list(tree) == [parent, child, loose]
    assert parent in tree
    assert parent.iid in tree
    assert 0 not in tree

    tree.detach(loose)

    assert len(tree) == 2
    assert list(tree) == [parent, child]
    assert loose in tree


def test_cell_values_round_trip_through_converters(window: tkfacade.Window) -> None:
    """A converted write stores Tk's string and reads back the Python value.

    The converter pair is the wrapper's central claim: Tk only stores strings, and the mapping face hides that. All three reads matter — raw proves what actually landed in Tk, the converted read proves the outgoing converter runs, and data proves the snapshot goes through the same converted path rather than the raw one.
    """
    tree = _inventory(window)
    row = tree.insert(item="bolt", count=7)

    assert _raw(row)["count"] == "7"
    assert row["count"] == 7
    assert row.data == {"item": "bolt", "count": 7}


def test_update_merges_with_kwargs_winning(window: tkfacade.Window) -> None:
    """``update`` writes both sources, keyword arguments beating the mapping.

    dict-style precedence, promised by the docstring ("win over competing keys in data"). The mapping's own count entry is the bait: an implementation applying kwargs first and the mapping second would leave 2, and one ignoring the mapping entirely would leave "bolt" — each wrong order fails a different assertion.
    """
    tree = _inventory(window)
    row = tree.insert(item="bolt", count=1)

    row.update({"item": "nut", "count": 2}, count=3)

    assert row["item"] == "nut"
    assert row["count"] == 3


def test_update_with_an_unknown_column_raises(window: tkfacade.Window) -> None:
    """``update`` raises ``KeyError`` for a name matching no column.

    The contrast case to insert, which documents that unknown names are *silently discarded*: update goes through __setitem__, where an unknown column is an error. The two behaviors are easy to assume identical, and this pins the stricter side of the asymmetry.
    """
    tree = _inventory(window)
    row = tree.insert(item="bolt", count=1)

    with pytest.raises(KeyError):
        row.update(bogus="x")


def test_clear_blanks_every_cell_but_keeps_the_columns(window: tkfacade.Window) -> None:
    """A cleared row still reports all columns, each holding ``""``.

    The regression test for the ledger's old column-loss entry: clear once wrote values=() and the row afterwards read as having no columns at all — len 0, iteration empty — indistinguishable from a deleted row. The Mapping invariants (stable keys, stable len) are exactly what the fix restores, so len and iteration are the assertions, with raw items pinning that the blanks really landed in Tk rather than being synthesized by a converter.
    """
    tree = _inventory(window)
    row = tree.insert(item="bolt", count=7)

    row.clear()

    assert len(row) == 2
    assert tuple(row) == ("item", "count")
    assert _raw(row) == {"item": "", "count": ""}


def test_clear_on_a_deleted_row_is_a_no_op(window: tkfacade.Window) -> None:
    """Clearing a row that no longer exists raises nothing.

    The other half of clear's contract: a gone row reads as an empty mapping everywhere in the class, and clear matches by swallowing the TclError rather than surfacing it. The fix moved a cget inside that suppress block, so this pins that the gone-row path stayed silent.
    """
    tree = _inventory(window)
    row = tree.insert(item="bolt", count=7)
    row.delete()

    row.clear()

    assert row.deleted


def test_cell_deletion_is_refused(window: tkfacade.Window) -> None:
    """``del`` on a cell raises ``NotImplementedError`` rather than blanking it.

    Columns are tree-wide, so deleting one cell cannot keep Mapping's invariants (the key would remain, len would not move) — the refusal is the documented resolution, with blanking via ``row[col] = ""`` as the sanctioned alternative. The raw read is the half that matters most: the regression to guard against is not a missing raise but a refusal that blanks the cell on its way out, which no exception assertion would catch.
    """
    tree = _inventory(window)
    row = tree.insert(item="bolt", count=1)

    with pytest.raises(NotImplementedError):
        del row["count"]

    assert _raw(row)["count"] == "1"


def test_row_answers_the_whole_mutable_mapping_contract(window: tkfacade.Window) -> None:
    """Every inherited mapping operation reads through the converters, or refuses.

    The rest of MutableMapping, none of which the class writes itself: keys, values, items, get and __contains__ are mixins standing on __getitem__ and __iter__, so a converter or an iteration order changing underneath them would break a caller with nothing in this class's source looking different — values and items are asserted converted for exactly that reason. setdefault is the odd one: it cannot insert, because a name no column answers to raises rather than becoming a column, so it is pinned in both directions. The closing data read is what makes the refusals mean something: pop raising while having written is the failure an exception assertion alone would miss.
    """
    tree = _inventory(window)
    row = tree.insert(item="bolt", count=7)

    assert list(row.keys()) == ["item", "count"]
    assert list(row.values()) == ["bolt", 7]
    assert list(row.items()) == [("item", "bolt"), ("count", 7)]
    assert "count" in row
    assert "missing" not in row
    assert row.get("count") == 7
    assert row.get("missing", "fallback") == "fallback"
    assert row.setdefault("count") == 7

    with pytest.raises(KeyError):
        row.setdefault("missing", 0)
    with pytest.raises(NotImplementedError):
        row.pop("count")
    with pytest.raises(NotImplementedError):
        row.popitem()

    assert row.data == {"item": "bolt", "count": 7}


def test_row_handles_for_one_iid_are_interchangeable(window: tkfacade.Window) -> None:
    """Two handles on the same tree and iid compare equal and hash together.

    Rows hold no state, so callers are invited to re-fetch handles freely and use them as dict keys; that only works if equality and hash follow the (tree, iid) identity rather than object identity. The is-not assertion guards the test itself against a future cache that would make the comparison vacuous.
    """
    tree = _inventory(window)
    iid = tree.insert(item="bolt", count=1).iid

    first = tree.row(iid)
    second = tree.row(iid)

    assert first is not None and second is not None
    assert first is not second
    assert first == second
    assert hash(first) == hash(second)
    assert len({first, second}) == 1


def test_row_tags_answer_the_whole_collection_contract(window: tkfacade.Window) -> None:
    """``len``, ``in`` and iteration read Tk's live list, duplicates counted.

    The whole of Collection, which is all TreeRowTags claims to be: no set algebra, no ordering promises beyond Tk's own list. The duplicated "alpha" is the case that separates this view from a set — len counts repeats and iteration yields both — and re-reading the same view object after a discard is what pins the class's central claim that it caches nothing.
    """
    tree = _inventory(window)
    row = tree.insert(item="bolt", count=1)
    row.tags.set(("alpha", "beta", "alpha"))
    tags = row.tags

    assert len(tags) == 3
    assert "alpha" in tags
    assert "gamma" not in tags
    assert list(tags) == ["alpha", "beta", "alpha"]

    row.tags.discard("alpha")

    assert len(tags) == 1
    assert "alpha" not in tags


def test_tags_keep_order_and_deduplicate(window: tkfacade.Window) -> None:
    """``add`` appends each unknown tag once; ``discard`` is total.

    Deduplicating onto an ordered store is the class's whole reason to exist: Tk keeps a list, so nothing underneath enforces either half. The repeated "beta" probes add's membership check against what is already on the row and the doubled "gamma" probes it within one call, which are separate paths. The second act pins discard's documented every-occurrence sweep, which only matters because set() accepts duplicates in the first place.
    """
    tree = _inventory(window)
    row = tree.insert(item="bolt", count=1)

    row.tags.set(("alpha", "beta"))
    row.tags.add("beta")
    row.tags.add("beta", "gamma", "gamma")

    assert tuple(row.tags) == ("alpha", "beta", "gamma")

    row.tags.set(("dup", "keep", "dup"))
    row.tags.discard("dup")

    assert tuple(row.tags) == ("keep",)


def test_tags_toggle_round_trips_and_replace_keeps_position(window: tkfacade.Window) -> None:
    """``toggle`` reports the new membership; ``replace`` swaps in place.

    replace exists only because position survives it, so the assertion that matters is the middle one: discard-then-add reaches the same membership and leaves ("one", "three", "deux"), which is why the tag order — not just the tag set — is what gets compared. toggle is pinned on its return value rather than on membership afterwards, since answering the wrong way round while still mutating correctly is the failure a membership assertion would miss. The absent-tag case guards the documented no-op, which the dedupe pass inside replace would otherwise be free to write through.
    """
    tree = _inventory(window)
    row = tree.insert(item="bolt", count=1)

    row.tags.set(("one", "two", "three"))

    assert row.tags.toggle("four") is True
    assert row.tags.toggle("four") is False
    assert tuple(row.tags) == ("one", "two", "three")

    assert row.tags.replace("two", "deux") is True
    assert tuple(row.tags) == ("one", "deux", "three")

    assert row.tags.replace("absent", "nothing") is False
    assert tuple(row.tags) == ("one", "deux", "three")


def test_replace_keeps_olds_position_whichever_side_new_was_on(window: tkfacade.Window) -> None:
    """A pre-existing ``new`` is surplus wherever it sits; the survivor takes ``old``'s slot.

    The dedupe pass used to keep the *first* occurrence of new, so a copy already sitting before old survived in its own slot and the survivor landed at the pre-existing copy's position — the opposite of the docstring's "carried once, at old's position". Both orderings are driven because the old code got new-after-old right and new-before-old wrong: a regression to first-occurrence logic passes the second block and fails the first, while a regression that drops position entirely fails both.
    """
    tree = _inventory(window)
    row = tree.insert(item="bolt", count=1)

    row.tags.set(("new", "mid", "old"))
    assert row.tags.replace("old", "new") is True
    assert tuple(row.tags) == ("mid", "new")

    row.tags.set(("old", "mid", "new"))
    assert row.tags.replace("old", "new") is True
    assert tuple(row.tags) == ("new", "mid")


def test_move_updates_parent_children_and_index(window: tkfacade.Window) -> None:
    """A reparenting move is visible through parent, children, and index.

    One structural mutation read back through every structural view: the views cache nothing, so each assertion is a separate question to Tk and any one of them diverging means a view lied about live state. depth rides along because it is derived from the ancestor walk, the one view not directly answered by a single Tk call.
    """
    tree = _inventory(window)
    parent = tree.insert(item="parent", count=0)
    child = tree.insert(item="child", count=1)

    tree.move(child, parent, 0)

    assert child.parent == parent
    assert child in parent.iter_children()
    assert child.index == 0
    assert child.depth == 1


def test_iter_children_yields_attached_children_in_order(window: tkfacade.Window) -> None:
    """``iter_children`` walks the direct children in display order, detached ones excluded.

    Three contracts the deleted TreeRowChildren held between its __iter__, __len__, and __contains__, now carried by one method: direct children only, display order, attached only. The grandchild is what makes "direct" falsifiable — a walk that recursed would yield it — and the detach is asserted through the same call rather than through is_detached because the exclusion is this method's own contract, not the row's. Order is compared as a list, not a set, since a set comparison would pass on any permutation.
    """
    tree = _inventory(window)
    parent = tree.insert(item="parent", count=0)
    first = parent.insert_child(item="first", count=1)
    parent.insert_child(item="second", count=2)
    parent.insert_child(item="third", count=3)
    first.insert_child(item="grandchild", count=4)

    assert [row["item"] for row in parent.iter_children()] == ["first", "second", "third"]

    tree.detach(first)

    assert [row["item"] for row in parent.iter_children()] == ["second", "third"]


def test_detach_hides_the_subtree_and_reattach_restores_position(window: tkfacade.Window) -> None:
    """A detached row's subtree leaves traversal; reattach restores its slot.

    detach/reattach is the wrapper's own bookkeeping (Tk forgets a detached row's position entirely), so the restored *middle* slot is the real assertion — Tk alone would only ever re-add at an end. The child pins the documented chain walk in is_detached: its own parent link is intact, so only walking to the root can notice the hidden ancestor, and deleted must stay False to distinguish hiding from deletion.
    """
    tree = _inventory(window)
    first = tree.insert(item="first", count=0)
    middle = tree.insert(item="middle", count=1)
    tree.insert(item="last", count=2)
    child = middle.insert_child(item="leaf", count=3)

    tree.detach(middle)

    assert middle.is_detached
    assert child.is_detached
    assert not child.deleted
    assert [row["item"] for row in tree] == ["first", "last"]

    tree.reattach(middle)

    assert [row["item"] for row in tree.roots] == ["first", "middle", "last"]
    assert middle.index == 1
    assert first.index == 0


def test_walk_is_depth_first_in_screen_order(window: tkfacade.Window) -> None:
    """``walk`` yields parents before children, siblings in display order.

    Pre-order is the promise callers rely on when mirroring the tree to another structure. The child is inserted *after* both roots, so an insertion-order walk — the most likely wrong implementation — yields a, c, b and fails. len rides along as the same traversal counted.
    """
    tree = _inventory(window)
    a = tree.insert(item="a", count=0)
    tree.insert(item="c", count=2)
    a.insert_child(item="b", count=1)

    assert [row["item"] for row in tree] == ["a", "b", "c"]
    assert len(tree) == 3


def test_delete_cascades_and_marks_handles(window: tkfacade.Window) -> None:
    """Deleting a row removes its descendants and flips their ``deleted``.

    The cascade plus the dangling-handle contract: handles cache nothing, so a deleted row's old handles must answer deleted rather than raising or resurrecting. The survivor guards the cascade's extent — a clear() misimplementation would take it too.
    """
    tree = _inventory(window)
    parent = tree.insert(item="parent", count=0)
    child = parent.insert_child(item="child", count=1)
    survivor = tree.insert(item="survivor", count=2)

    parent.delete()

    assert parent.deleted
    assert child.deleted
    assert not survivor.deleted
    assert len(tree) == 1


def test_sort_children_orders_by_converted_values(window: tkfacade.Window) -> None:
    """Sorting a numeric column orders 9 before 10, not after it.

    The reason sorting goes through converters at all: Tk stores "10" and "9", and a string sort — what raw Treeview sorting does — puts "10" first. The 9/10/200 triple is the classic lexicographic trap; a sort reading raw cells fails it immediately.
    """
    tree = _inventory(window)
    for count in (10, 9, 200):
        tree.insert(item=f"n{count}", count=count)
    column = tree.column("count")
    assert column is not None

    tree.sort_rows(column)

    assert [row["count"] for row in tree.roots] == [9, 10, 200]


def test_column_cells_round_trip_through_its_own_converters(window: tkfacade.Window) -> None:
    """A column read and write apply the converters the column itself owns.

    The point of the change: the column used to borrow a TreeRow to apply converters it already owns, and this pins that it no longer does. The zero-padding converter is what makes the write observable — the tree's default str() and Tk's own stringification both yield "9", so only "009" proves the *column's* incoming converter ran on the column's own write path. The row read afterwards pins that both faces address one cell rather than diverging stores.
    """
    tree = _inventory(window)
    row = tree.insert(item="bolt", count=7)
    column = tree.column("count")
    assert column is not None
    column.incoming_converter = "{:03d}".format

    assert column[row.iid] == 7

    column[row.iid] = 9

    assert _raw(row)["count"] == "009"
    assert row["count"] == 9


def test_column_keys_are_row_iids_in_screen_order(window: tkfacade.Window) -> None:
    """A column iterates the attached rows' iids depth-first, values alongside.

    Keys are iids, not screen positions, so dict(column) means iid -> value. The child is inserted after both roots, so an insertion-order implementation yields a, c, b and fails. len rides along because __iter__ and __len__ must count the same rows or every mixin built on them lies. values() is asserted as the replacement for the removed cells(), and is what would catch __iter__ yielding values instead of keys — which is what the legacy sequence protocol did before the ABC landed, silently and without a call site to notice.
    """
    tree = _inventory(window)
    a = tree.insert(item="a", count=0)
    c = tree.insert(item="c", count=2)
    b = a.insert_child(item="b", count=1)
    column = tree.column("count")
    assert column is not None

    assert list(column) == [a.iid, b.iid, c.iid]
    assert len(column) == 3
    assert list(column.values()) == [0, 1, 2]
    assert column.data == {a.iid: 0, b.iid: 1, c.iid: 2}


def test_column_accepts_a_row_an_iid_or_an_index_as_key(window: tkfacade.Window) -> None:
    """The three key forms name the same cell for reading, writing, and ``in``.

    Row, iid, and index address one cell, matching Tree.row()/Tree.column(), which already take str | int, and Tree.__contains__, which already accepts a row or a bare iid. The chained equality is anchored to the literal 2 so it cannot pass by all three forms failing the same way. Index 1 rather than 0 is deliberate: 0 is the falsy int, and a resolver written with a truthiness test instead of an isinstance check would pass on 0 and fail here. The write goes through the row form and reads back through the iid form, pinning that resolution is shared by both halves rather than implemented twice.  The index membership check calls __contains__ directly because `1 in column` is a mypy error, not a runtime one: the class declares MutableMapping[str, Any], so the `in` operator is checked against Container[str] and cannot see the widened __contains__. Calling the method exercises the same path a suppression would have hidden, and leaves the type-level limitation visible where it belongs rather than papered over.
    """
    tree = _inventory(window)
    tree.insert(item="first", count=1)
    second = tree.insert(item="second", count=2)
    column = tree.column("count")
    assert column is not None

    assert column[second] == column[second.iid] == column[1] == 2
    assert second in column
    assert second.iid in column
    assert column.__contains__(1)

    column[second] = 5

    assert column[second.iid] == 5


def test_column_rejects_unknown_keys_without_raising_on_membership(window: tkfacade.Window) -> None:
    """An unusable key raises on read and write, and reads as absent.

    The out-of-range index is the trap this pins: it used to raise IndexError, which Mapping.__contains__ and get() do not catch, so `4 in column` would have raised instead of answering False. The write case matters separately and is the interesting half — on an ordinary MutableMapping writing an unknown key *creates* it, and a column must never conjure a row. The arbitrary object covers the other direction: an unusable key type answers False rather than raising TypeError, as Tree.__contains__ does, which is why __contains__ is overridden at all. len closes it by pinning that none of the failed writes landed.
    """
    tree = _inventory(window)
    tree.insert(item="bolt", count=7)
    column = tree.column("count")
    assert column is not None

    with pytest.raises(KeyError):
        column["nosuchrow"]
    with pytest.raises(KeyError):
        column[4]
    with pytest.raises(KeyError):
        column["nosuchrow"] = 5

    assert "nosuchrow" not in column
    assert not column.__contains__(4)
    assert object() not in column
    assert column.get("nosuchrow") is None
    assert len(column) == 1


def test_column_cell_deletion_is_refused(window: tkfacade.Window) -> None:
    """``del`` and the mixins built on it raise ``NotImplementedError``.

    The column refuses for the row face's reason, from the other side: a cell is where a row and a column cross, so removing one alone would mean deleting the row, and blanking instead would leave the key present with len unchanged. pop and popitem are asserted because MutableMapping builds them on __delitem__, so pinning them is what makes the refusal total rather than a property of one syntax. The final read proves the refusals were not partial writes.
    """
    tree = _inventory(window)
    row = tree.insert(item="bolt", count=7)
    column = tree.column("count")
    assert column is not None

    with pytest.raises(NotImplementedError):
        del column[row.iid]
    with pytest.raises(NotImplementedError):
        column.pop(row.iid)
    with pytest.raises(NotImplementedError):
        column.popitem()

    assert column[row.iid] == 7


def test_column_clear_blanks_only_its_own_cells(window: tkfacade.Window) -> None:
    """A cleared column reads ``""`` in every row; the rows and siblings survive.

    MutableMapping.clear pops through __delitem__ and would raise NotImplementedError on any non-empty column, so the override is load-bearing and this is what pins it. The surviving count values are the scope assertion: a clear reaching Tk's item(values=...) the way the row side does would blank the whole row instead of one column. One raw read pins that the blanks landed in Tk rather than being synthesized by the identity converter. "item" is cleared rather than "count" because a blanked cell is raw "" which count's int converter cannot read back — that hazard belongs to the converter, not to clear, and is deliberately left unasserted here.
    """
    tree = _inventory(window)
    first = tree.insert(item="bolt", count=7)
    second = tree.insert(item="nut", count=8)
    column = tree.column("item")
    assert column is not None

    column.clear()

    assert len(column) == 2
    assert list(column) == [first.iid, second.iid]
    assert list(column.values()) == ["", ""]
    assert _raw(first)["item"] == ""
    assert first["count"] == 7
    assert second["count"] == 8


def test_column_answers_the_whole_mutable_mapping_contract(window: tkfacade.Window) -> None:
    """The inherited mapping operations key by iid and convert like the rest.

    The positive half of the contract, the refusals being pinned by the deletion test above. Everything here is inherited from MutableMapping and reaches Tk through this column's own accessors, so the assertions are on converted values and on iid order: values and items going through __getitem__ is what makes the outgoing converter apply to them, and keys following __iter__ is what makes screen order theirs too. setdefault cannot insert — a key naming no row raises rather than becoming one — so both directions are pinned, and update is asserted by reading the cell back through a row handle rather than through the column that wrote it.
    """
    tree = _inventory(window)
    first = tree.insert(item="bolt", count=1)
    second = tree.insert(item="nut", count=2)
    column = tree.column("count")
    assert column is not None

    assert list(column.keys()) == [first.iid, second.iid]
    assert list(column.values()) == [1, 2]
    assert list(column.items()) == [(first.iid, 1), (second.iid, 2)]
    assert column.get(first.iid) == 1
    assert column.get("nobody", 0) == 0
    assert column.setdefault(second.iid) == 2

    column.update({first.iid: 9})

    assert column[first] == 9
    with pytest.raises(KeyError):
        column.setdefault("nobody", 0)


def test_a_detached_rows_cell_leaves_iteration_but_stays_readable(window: tkfacade.Window) -> None:
    """A detached row is no longer a key, though its value still answers by iid.

    The documented asymmetry, inherited from Tree itself: Tree.__contains__ answers existence while Tree.__iter__ yields attached rows only, so the column answers the same question the same way rather than inventing a third rule. The alternative — an O(n) __contains__ that walks the tree — was rejected because it would make `in` deny a key __getitem__ answers, and disagree with get() besides. This test records the choice so a later consistency fix has to argue with it instead of silently flipping it.
    """
    tree = _inventory(window)
    kept = tree.insert(item="kept", count=1)
    gone = tree.insert(item="gone", count=2)
    column = tree.column("count")
    assert column is not None

    tree.detach(gone)

    assert list(column) == [kept.iid]
    assert len(column) == 1
    assert column[gone.iid] == 2
    assert gone.iid in column


def test_column_handles_compare_by_identity_not_by_contents(window: tkfacade.Window) -> None:
    """Handles for one column are equal and hash together; different columns are not.

    collections.abc.Mapping supplies content equality and sets __hash__ = None, so the hand-written __eq__/__hash__ are the only thing keeping a column identified by tree and name once the ABC is a base. mypy cannot see the clash — typeshed's Mapping declares neither — which makes a test the only possible guard. The tree is left deliberately empty because that is exactly when content equality makes every column equal to every other ({} == {}), so a populated tree would hide the regression. Losing __hash__ fails on the hash line; losing only __eq__ sails past it and surfaces at the displayed pair, which goes through Tree.displayed_columns membership and would report the hidden column as still displayed.
    """
    tree = _inventory(window)
    count = tree.column("count")
    again = tree.column("count")
    item = tree.column("item")
    assert count is not None and again is not None and item is not None

    assert count is not again
    assert count == again
    assert hash(count) == hash(again)
    assert len({count, again}) == 1
    assert count != item

    tree.hide_column("item")

    assert count.displayed
    assert not item.displayed


def test_a_dropped_column_reads_as_an_empty_mapping(window: tkfacade.Window) -> None:
    """A dropped column iterates nothing and holds no keys; the rows remain.

    The dangling-handle contract, matched to the row face: a deleted row reads as an empty mapping everywhere rather than raising, and a dropped column now does the same. Without the exists gate, __len__ would still answer 1 (it counts the tree's rows) and __iter__ would still yield the iid, while every value read raised KeyError — so data would raise on a handle that claimed to have keys. The tree's own len and the surviving item value are the scope assertion: dropping a column must not disturb the rows or their other cells.
    """
    tree = _inventory(window)
    row = tree.insert(item="bolt", count=7)
    column = tree.column("count")
    assert column is not None

    tree.drop_column("count")

    assert not column.exists
    assert len(column) == 0
    assert list(column) == []
    assert column.data == {}
    assert row.iid not in column
    assert len(tree) == 1
    assert row["item"] == "bolt"


def _ledger(window: tkfacade.Window) -> tkfacade.Tree:
    """A tree with three plain columns, so one of them can be a middle.

    Args:
        window (tkfacade.Window): The window to build the tree in.

    Returns:
        The empty, three-column tree.
    """
    return tkfacade.Tree(window, columns=tuple(TreeColumnSpec(name=n) for n in ("a", "b", "c")))


def test_add_column_at_an_index_leaves_the_new_column_empty(window: tkfacade.Window) -> None:
    """An inserted column starts blank in every row, and its neighbours keep theirs.

    Tk stores a row's cells as a positional tuple, so inserting a name anywhere but the end re-slots every later value onto its neighbour's name. The restore pass used to write back only the names it had snapshotted, which corrected the old columns and left the new one holding whatever slid into its slot — "2" and "5" here. Index 1 is the whole point: appending shifts nothing and would pass either way, which is why the existing drop-a-last-column test never caught this. Two rows rather than one guards against a fix that happens to clear only the first. No row is detached, because this half of the defect needs none — it is ordinary use.
    """
    tree = _ledger(window)
    first = tree.insert(a="1", b="2", c="3")
    second = tree.insert(a="4", b="5", c="6")

    tree.add_column("z", 1)

    assert _raw(first) == {"a": "1", "z": "", "b": "2", "c": "3"}
    assert _raw(second) == {"a": "4", "z": "", "b": "5", "c": "6"}


def test_column_changes_keep_detached_rows_aligned(window: tkfacade.Window) -> None:
    """A detached row's values stay under their own names across add and drop.

    The filed defect: no traversal rooted at the root reaches a detached row, so the snapshot skipped it entirely and Tk's positional re-slot went uncorrected — c came back holding b's value. The attached row is asserted alongside as the control, since it was always restored correctly and a fix that broke it would otherwise pass. Both directions are exercised because add and drop shift opposite ways and share one helper. The reattach at the end is what a caller actually does with a hidden row, and reading through the converted face proves the damage was not merely hidden from the raw one.
    """
    tree = _ledger(window)
    kept = tree.insert(a="k1", b="k2", c="k3")
    gone = tree.insert(a="d1", b="d2", c="d3")
    tree.detach(gone)

    tree.drop_column("b")

    assert _raw(kept) == {"a": "k1", "c": "k3"}
    assert _raw(gone) == {"a": "d1", "c": "d3"}

    tree.add_column("z", 1)

    assert _raw(gone) == {"a": "d1", "z": "", "c": "d3"}

    tree.reattach(gone)

    assert gone["a"] == "d1"
    assert gone["c"] == "d3"


def test_column_changes_reach_a_detached_rows_descendant(window: tkfacade.Window) -> None:
    """A row hidden inside a detached subtree keeps its values too.

    The case that decides how detached rows are enumerated. The detach record is keyed only by rows passed to detach, so the child is not in it and never will be — it is reachable only by walking down from its detached parent. A fix that iterated the record's keys and stopped there would pass the test above and fail this one, which is why the two are separate. The existing detach test already builds this exact parent/child shape; it just never reconfigures columns in between.
    """
    tree = _ledger(window)
    parent = tree.insert(a="p1", b="p2", c="p3")
    child = parent.insert_child(a="c1", b="c2", c="c3")
    tree.detach(parent)

    tree.drop_column("b")

    assert _raw(child) == {"a": "c1", "c": "c3"}


def test_hide_row_and_show_row_act_on_a_tree_with_no_columns(window: tkfacade.Window) -> None:
    """Both act on the row they find, however many columns the tree declares.

    Both methods guarded with `if row := self.row(key):`, and a row's length is its *column* count — so on a column-less tree every row is falsy, the detach never happened, and the row was still returned as though it had. Declaring no columns is the whole point of the fixture: _inventory's two columns are exactly the condition that masks this, which is why every other test in the file passes either way. The returned row is asserted as well as the effect, because the defect's signature was a truthful-looking return value over an action that never ran. mypy cannot catch this class of bug — truthy-bool only fires for types that are always truthy, and TreeRow defines __len__ — so this test is the only guard there can be.
    """
    tree = tkfacade.Tree(window, columns=())
    row = tree.insert(text="only")

    assert tree.hide_row(row.iid) == row
    assert row.is_detached

    assert tree.show_row(row.iid) == row
    assert not row.is_detached


def test_tagged_finds_detached_rows(window: tkfacade.Window) -> None:
    """A detached row carrying the tag is returned, after the attached ones.

    Tk's one-argument tag_has walks down from the root, so it answers only for attached rows and the wrapper handed back a silently short list under a docstring promising all of them. The detached *untagged* row is the trap: a fix that appended every detached row rather than testing each against the tag would return it too and fail here. The result is compared as an ordered tuple, not a set, because the docstring now commits to attached matches first — and the plain attached row pins that the tag is still doing the filtering.
    """
    tree = _inventory(window)
    kept = tree.insert(item="kept", count=1, tags="flag")
    gone = tree.insert(item="gone", count=2, tags="flag")
    tree.insert(item="plain", count=3)
    bare = tree.insert(item="bare", count=4)

    tree.detach(gone)
    tree.detach(bare)

    assert tree.tagged("flag") == (kept, gone)


def test_tagged_reaches_inside_a_detached_subtree(window: tkfacade.Window) -> None:
    """A tagged row hidden inside a detached parent is still found.

    The child is never a key of the detach record — only rows passed to detach are — so it is reachable only by walking down from its detached parent. A fix that iterated the record's keys and tested those alone passes the test above and fails this one, which is why the two are separate; the column-reconfigure tests split on exactly the same seam for the same reason. The parent is deliberately left untagged so the single-element result cannot come from the parent instead.
    """
    tree = _inventory(window)
    parent = tree.insert(item="parent", count=1)
    child = parent.insert_child(item="child", count=2, tags="flag")

    tree.detach(parent)

    assert tree.tagged("flag") == (child,)


def test_reconfiguring_columns_keeps_every_surviving_heading(window: tkfacade.Window) -> None:
    """Adding and dropping a column leave the other headings' text and commands intact.

    Reconfiguring ``columns`` resets every heading Tk holds, so the cell snapshot _reconfigure_columns has always taken needed a heading snapshot beside it. Text and command are asserted separately because they fail differently: text came back as "" rather than as the title-cased default, while a lost command is invisible until someone clicks. The command is invoked through Tk, as a click would, rather than compared as a string — the string is a Tcl procedure name, and that it round-trips is exactly what the replay depends on. The new column asserts the other half of the contract: it gets its own default heading, not a neighbour's.
    """
    fired: list[str] = []
    tree = tkfacade.Tree(
        window,
        columns=(
            TreeColumnSpec(
                name="a", heading_text="Part No.", heading_command=lambda: fired.append("a")
            ),
            TreeColumnSpec(name="b", heading_text="Qty"),
        ),
    )
    first = tree.column("a")
    assert first is not None

    tree.add_column("z", 1)
    second = tree.column("b")
    added = tree.column("z")
    assert second is not None and added is not None

    assert first.heading.text == "Part No."
    assert second.heading.text == "Qty"
    assert added.heading.text == "Z"

    tree.tk.call(str(tree._treeview.heading(first.name, "command")))
    tree.drop_column("z")

    assert fired == ["a"]
    assert first.heading.text == "Part No."
    assert second.heading.text == "Qty"


def test_column_clear_skips_a_failing_row_and_blanks_the_rest(
    window: tkfacade.Window, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One row Tk refuses is skipped; every other row is still blanked.

    ``clear`` used to wrap its whole loop in one suppress, so the first row Tk refused ended the pass and every later row silently kept its value — the docstring promising "every attached row" all the while. The failure is injected because there is no way to ask a live Treeview to refuse one row and accept its neighbours, and the refusal is what the contract is about; the row before and the rows after are what the assertion is really comparing, since a suppress around the loop leaves "3" and "4" standing. The untouched b column is the scope half: a clear must not spill into the row's other cells.
    """
    tree = tkfacade.Tree(window, columns=(TreeColumnSpec(name="a"), TreeColumnSpec(name="b")))
    rows = [tree.insert(a=str(index), b="keep") for index in range(5)]
    column = tree.column("a")
    assert column is not None

    real_set = tree._treeview.set
    refused = rows[2].iid

    def flaky_set(item: str, column: str, value: str) -> object:
        if item == refused and value == "":
            raise tk.TclError(f"Item {item} not found")
        return real_set(item, column, value)

    monkeypatch.setattr(tree._treeview, "set", flaky_set)
    column.clear()
    monkeypatch.undo()

    assert [row["a"] for row in rows] == ["", "", "2", "", ""]
    assert [row["b"] for row in rows] == ["keep"] * 5


def test_reconfiguring_columns_keeps_sibling_body_options(window: tkfacade.Window) -> None:
    """A sibling's width, minwidth, stretch, and anchor survive an add and a drop.

    Tk resets all column state when the columns list is reconfigured, and the reconfigure used to snapshot only cells and headings — so every add_column or drop_column silently snapped sibling columns back to 200px, "w", stretch-on. All four body options are set away from their defaults first, precisely so a reset to any default is visible, and both directions are driven because add and drop share the reconfigure but arrive with different survivor sets. Reads go through the raw treeview query because the wrapper's own accessors ride the same option names being pinned.
    """
    tree = tkfacade.Tree(
        window,
        columns=(TreeColumnSpec(name="a", width=55, anchor="e"), TreeColumnSpec(name="b")),
    )
    tree._treeview.column("a", minwidth=33, stretch=False)

    tree.add_column("z")
    added = {k: tree._treeview.column("a", k) for k in ("width", "minwidth", "stretch", "anchor")}
    tree.drop_column("z")
    dropped = {k: tree._treeview.column("a", k) for k in ("width", "minwidth", "stretch", "anchor")}

    expected = {"width": 55, "minwidth": 33, "stretch": 0, "anchor": "e"}
    assert {k: str(v) if k == "anchor" else int(str(v)) for k, v in added.items()} == expected
    assert {k: str(v) if k == "anchor" else int(str(v)) for k, v in dropped.items()} == expected


def test_a_rejected_add_column_leaves_the_tree_unchanged(window: tkfacade.Window) -> None:
    """A Tk-rejected option rolls the new column back out, and the retry lands.

    add_column's docstring promises that a call that raises leaves the tree unchanged, and the promise held only for what the spec could check itself: a value only Tk rejects surfaced after the destructive reconfigure and the registrations, so retrying with a fixed value hit "column already exists" over a half-configured column. The retry is the sharpest pin — it can only land if the failed call dropped both its column and every registration back out — and the pre-existing row's cell is read because the rollback rides _reconfigure_columns, whose whole job is carrying data across. The bad anchor needs its ignore because the option's literal type already excludes it: the test stands in for the runtime-sourced value mypy cannot rule out.
    """
    tree = _inventory(window)
    row = tree.insert(item="bolt", count=1)

    with pytest.raises(tk.TclError):
        tree.add_column("q", anchor="bogus")  # type: ignore[arg-type]

    assert [col.name for col in tree.columns] == ["item", "count"]
    assert row["item"] == "bolt"

    added = tree.add_column("q", anchor="e")

    assert [col.name for col in tree.columns] == ["item", "count", "q"]
    assert added.anchor == "e"


def test_column_reconfigure_survives_an_explicit_displaycolumns(window: tkfacade.Window) -> None:
    """Dropping and adding columns works, and keeps hidden hidden, after a hide.

    The reconfigure funnel both drop_column and add_column ride assigns ``columns`` while Tk validates the still-explicit displaycolumns against the *new* set — any tree that ever hid a column kept one, and a dropped column still named there aborted mid-configure with the option record half-committed: drop_column raised from a method documented never to, cget("columns") disagreed with the live table, and the cells re-slotted positionally (c reading "B"). The cell assertion pins the re-slot specifically; the displayed reads pin that shepherding displaycolumns through the reconfigure does not quietly reveal the hidden column. Every prior test dropped from a never-hidden tree, whose ``#all`` is valid against any set — the masking condition this tree exists to break.
    """
    tree = tkfacade.Tree(window, columns=tuple(TreeColumnSpec(name=n) for n in ("a", "b", "c")))
    row = tree.insert(values={"a": "A", "b": "B", "c": "C"})
    tree.hide_column("c")

    tree.drop_column("b")

    assert [col.name for col in tree.columns] == ["a", "c"]
    assert [col.name for col in tree.displayed_columns] == ["a"]
    assert tree._treeview.set(row.iid) == {"a": "A", "c": "C"}

    tree.add_column("d")

    assert [col.name for col in tree.columns] == ["a", "c", "d"]
    assert [col.name for col in tree.displayed_columns] == ["a", "d"]


def test_a_drop_leaving_only_hidden_columns_is_refused_whole(window: tkfacade.Window) -> None:
    """Dropping the last displayed column raises and changes nothing at all.

    The zero-displayed state is refused at this third door with the same wording as the constructor's and hide_column's, and — the half the old failure made expensive — refused *before* anything moves: drop_column used to evict the column's registrations ahead of the reconfigure, so an aborted drop lost the converters, defaults, and aliases of a column it then failed to remove. The bound_name column is the sentinel for that: the final insert routing "beta" to its column proves the alias table survived the refusal untouched.
    """
    tree = tkfacade.Tree(
        window,
        columns=(
            TreeColumnSpec(name="a"),
            TreeColumnSpec(name="b", bound_name="beta"),
        ),
    )
    row = tree.insert(values={"a": "A", "beta": "B"})
    tree.hide_column("b")

    with pytest.raises(ValueError, match="at least one"):
        tree.drop_column("a")

    assert [col.name for col in tree.columns] == ["a", "b"]
    assert [col.name for col in tree.displayed_columns] == ["a"]
    assert tree._treeview.set(row.iid) == {"a": "A", "b": "B"}
    assert tree.insert(values={"beta": "again"})["b"] == "again"


def test_sorting_refuses_another_trees_column(window: tkfacade.Window) -> None:
    """All three sort doors raise ``KeyError`` for a foreign column, moving nothing.

    The foreign-row refusal covered rows only: sort_rows, TreeRow.sort_children, and Table.sort_rows took a TreeColumn and used nothing but its name — and column names are caller-chosen, so two trees built from one spec list share every one, and t1.sort_rows(t2.column("x")) silently sorted the wrong tree (a Table also raised its arrow, actively claiming the sort). All three doors are driven because each resolves the column separately; the order reads pin that the refusals moved nothing — insertion order still standing is the whole claim.
    """
    ours = _inventory(window)
    theirs = _inventory(window)
    for count in (3, 1, 2):
        ours.insert(item="row", count=count)
    parent = ours.insert(item="parent", count=0)
    for count in (5, 4):
        ours.insert(item="child", count=count, parent=parent)
    foreign = theirs.column("count")
    assert foreign is not None

    with pytest.raises(KeyError):
        ours.sort_rows(foreign)
    with pytest.raises(KeyError):
        parent.sort_children(foreign)

    table = tkfacade.Table(window, columns=(TreeColumnSpec(name="count"),))
    with pytest.raises(KeyError):
        table.sort_rows(foreign)

    assert [row["count"] for row in ours.roots] == [3, 1, 2, 0]
    assert [row["count"] for row in parent.iter_children()] == [5, 4]


def test_a_row_image_round_trips_the_wrapper_it_was_given(window: tkfacade.Window) -> None:
    """A row answers None until given an image, then with the very wrapper it was given.

    The property's whole contract in one pass, because the interesting failures are on different routes: insert and the setter each store separately, and a getter reading Tk instead of the store could not answer with a wrapper at all. Identity is asserted rather than equality — ImageWrapper defines no __eq__, so == would be identity wearing a disguise, and saying `is` makes the claim the code actually makes: a wrapper handed in is stored as given, not copied. The fresh row is what stops the getter passing vacuously by handing back some wrapper regardless, and the bytes row pins the other half, that a source which is not a wrapper becomes one.
    """
    tree = _inventory(window)
    icon = tkfacade.small_icon(_png())

    fresh = tree.insert(item="a", count=1)
    inserted = tree.insert(item="b", count=2, image=icon)
    assigned = tree.insert(item="c", count=3)
    assigned.image = icon
    loaded = tree.insert(item="d", count=4)
    loaded.image = _png()

    assert fresh.image is None
    assert inserted.image is icon
    assert assigned.image is icon
    assert isinstance(loaded.image, tkfacade.ImageWrapper)
    assert loaded.image is not icon


def test_setting_a_row_image_replaces_the_one_the_tree_holds(window: tkfacade.Window) -> None:
    """A second assignment supersedes the first, on the widget and in the store.

    Overwriting is the half a store invites getting wrong: the retention dict is keyed by iid, so a setter that stored without replacing would leave the first wrapper in place and the getter would keep answering with it while the widget drew the second. Both ends are read for that reason — the store through the property, the widget through Tk's own name — and the two icons are built separately from identical bytes so they are distinct objects with distinct handles; the closing inequality is what says the widget moved at all rather than the two names having coincided.
    """
    tree = _inventory(window)
    first = tkfacade.small_icon(_png())
    second = tkfacade.small_icon(_png())
    row = tree.insert(item="a", count=1, image=first)

    was = _image_name(tree._treeview.item(row.iid, "image"))
    row.image = second

    assert row.image is second
    assert _image_name(tree._treeview.item(row.iid, "image")) == str(
        second.photo_for(tree._treeview)
    )
    assert was != _image_name(tree._treeview.item(row.iid, "image"))


def test_clearing_a_row_image_takes_it_off_the_widget_and_the_store(
    window: tkfacade.Window,
) -> None:
    """Assigning None blanks the item's image and drops the tree's reference.

    ``""`` used to be how a caller cleared a row image, and it cannot be any more: an empty string is a valid ImageInput — a path — so None had to take the job, matching Label.image.set(None). The store is asserted directly because that is the only place a leak would show: a clear that blanked the widget but left the entry standing would satisfy both public reads while pinning the image for the row's life, and the retention suite would not catch it either, since it only ever asks whether an image is still alive.
    """
    tree = _inventory(window)
    row = tree.insert(item="a", count=1, image=tkfacade.small_icon(_png()))

    row.image = None

    assert row.image is None
    assert _image_name(tree._treeview.item(row.iid, "image")) == ""
    assert row.iid not in tree._images


def test_rows_given_one_wrapper_share_it_and_its_tk_handle(window: tkfacade.Window) -> None:
    """Two rows handed one wrapper hold that same object and draw one Tk image.

    The test that pins storing-as-given rather than copying, and the only one that does: a setter calling ImageWrapper(arg) unconditionally passes every other test in this block, since a copy answers to `isinstance` and round-trips just as well. It fails here twice over — the identity chain, and the Tk names, which would be two handles over two copies of the same pixels. That is the point of the decision: a tree whose rows all carry one icon carries one image, not one per row.
    """
    tree = _inventory(window)
    icon = tkfacade.small_icon(_png())

    first = tree.insert(item="a", count=1, image=icon)
    second = tree.insert(item="b", count=2)
    second.image = icon

    assert first.image is second.image is icon
    assert _image_name(tree._treeview.item(first.iid, "image")) == _image_name(
        tree._treeview.item(second.iid, "image")
    )


def test_a_heading_image_round_trips_the_wrapper_it_was_given(window: tkfacade.Window) -> None:
    """A column heading answers None until given an image, then with that wrapper.

    The heading carries its own copy of the row's machinery against a different Tk call and a different store, so it is held to the same contract separately rather than trusted to follow. The whole cycle is one test because a heading has no equivalent of a fresh row — the unset state is only reachable before the first write — so reading it first is the only chance to pin it, and the clear at the end is what proves the release path is the heading's own rather than drop_column's, which the retention suite already covers.
    """
    tree = _inventory(window)
    column = tree.column("item")
    assert column is not None
    icon = tkfacade.small_icon(_png())

    before = column.heading.image
    column.heading.image = icon
    after = column.heading.image
    column.heading.image = None

    assert before is None
    assert after is icon
    assert column.heading.image is None
    assert _image_name(tree._treeview.heading("item", "image")) == ""


def test_configure_tag_tells_an_omitted_image_from_a_cleared_one(window: tkfacade.Window) -> None:
    """Leaving ``image`` out keeps a tag's image; passing None takes it away.

    The two halves of the OMIT split, which only mean anything together: the middle call configures something else entirely and must leave the image standing, and the last passes None and must remove it. A version that ignored the parameter passes the first; one that treated every non-image call as a clear passes the second; nothing passes both without telling "not given" from "given as None", which is the whole reason the default became OMIT rather than None. The store is read alongside Tk because a clear that blanked the widget and left the entry would pin the image for the tree's life with both public reads agreeing.
    """
    tree = _inventory(window)
    tree.configure_tag("warn", image=_png())
    set_name = _image_name(tree._treeview.tag_configure("warn", "image"))

    tree.configure_tag("warn", foreground="red")
    omitted = (
        _image_name(tree._treeview.tag_configure("warn", "image")),
        "warn" in tree._tag_images,
    )
    tree.configure_tag("warn", image=None)
    cleared = (
        _image_name(tree._treeview.tag_configure("warn", "image")),
        "warn" in tree._tag_images,
    )

    assert set_name != ""
    assert omitted == (set_name, True)
    assert cleared == ("", False)


def test_a_heading_command_reads_back_and_swaps(window: tkfacade.Window) -> None:
    """The property answers the held command, and a swap needs no rewiring.

    The tree registers one dispatcher per column and holds the command
    behind it, so assigning again changes what runs without a second
    Tcl registration, and None leaves a click running nothing.
    """
    tree = tkfacade.Tree(window, columns=(TreeColumnSpec(name="a"),))
    column = tree.column("a")
    assert column is not None
    runs: list[str] = []

    def first() -> None:
        runs.append("first")

    column.heading.command = first
    registered = str(tree._treeview.heading("a", "command"))

    assert column.heading.command is first

    column.heading.command = lambda: runs.append("second")

    assert str(tree._treeview.heading("a", "command")) == registered
    tree.tk.call(registered)
    assert runs == ["second"]

    column.heading.command = None
    tree.tk.call(registered)

    assert column.heading.command is None
    assert runs == ["second"]


def test_a_coroutine_heading_command_runs_on_the_core(
    window: tkfacade.Window, run_mainloop: RunMainloop
) -> None:
    """A coroutine function as a heading command is scheduled off-thread.

    The same dual-kind command — a plain callable or a coroutine
    function — as every command, through the same dispatch: the click's
    dispatcher schedules a coroutine function on the root's core rather
    than the mainloop.
    """
    main = threading.get_ident()
    ran_on: list[int] = []
    done = threading.Event()

    async def command() -> None:
        await asyncio.sleep(0)
        ran_on.append(threading.get_ident())
        done.set()

    tree = tkfacade.Tree(window, columns=(TreeColumnSpec(name="a", heading_command=command),))
    tree.grid(row=0, column=0)
    registered = str(tree._treeview.heading("a", "command"))
    window._tk.after(0, lambda: tree.tk.call(registered))
    run_mainloop(window, done)

    assert len(ran_on) == 1
    assert ran_on[0] != main
