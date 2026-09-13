""":class:`~tkfacade.Table`: the flat, click-to-sort :class:`~tkfacade.Tree`.

What distinguishes a table from its base is pinned here — the flatness
contract, and the sort machinery that heading clicks, programmatic
sorts, and insert-time placement all share. Heading clicks are driven
through the command Tk itself would invoke, reached via the Tcl name
the widget holds for it and the public ``tk`` interpreter handle —
``heading.command`` itself answers the held command, not the name.
Everything runs on the ``window`` fixture under the ``gui`` marker.
"""

import pytest

import tkfacade
from tkfacade.tree import TreeColumn, TreeColumnSpec
from tkfacade.window import Root

pytestmark = pytest.mark.gui


def _scores(window: tkfacade.Window, *counts: int) -> tuple[tkfacade.Table, TreeColumn]:
    """A one-int-column table preloaded with ``counts``, plus that column.

    Args:
        window (tkfacade.Window): The window to build the table in.
        *counts (int): Initial ``count`` cell values, in insertion
            order.

    Returns:
        The table and its ``count`` column.
    """
    table = tkfacade.Table(
        window,
        columns=(TreeColumnSpec(name="count", incoming_converter=str, outgoing_converter=int),),
    )
    for count in counts:
        table.insert(count=count)
    column = table.column("count")
    assert column is not None
    return table, column


def _click_heading(table: tkfacade.Table, column: TreeColumn) -> None:
    """Invoke the heading's click command exactly as Tk would.

    Args:
        table (tkfacade.Table): The table whose interpreter runs the
            command.
        column (TreeColumn): The column whose heading is clicked.
    """
    table.tk.call(str(table._treeview.heading(column.name, "command")))


def test_flatness_is_enforced(window: tkfacade.Window) -> None:
    """``insert`` and ``move`` with a non-root parent raise ``TypeError``.

    The table's defining restriction, checked at both mutation funnels; inherited Tree methods would happily nest, and a nested row would break every sort below (bisect walks only roots). TypeError rather than ValueError is the documented choice — the *kind* of operation is wrong for a Table — so the exception type is part of the pin.
    """
    table, _column = _scores(window, 1)
    row = table.roots[0]

    with pytest.raises(TypeError, match="child rows"):
        table.insert(parent=row, count=2)
    with pytest.raises(TypeError, match="child rows"):
        table.move(row, parent=row)


def test_first_heading_click_sorts_descending_then_toggles(window: tkfacade.Window) -> None:
    """A heading click sorts descending; the next click flips ascending.

    The click cycle's documented opening move is descending — the convention users expect from score-like columns — and it is one boolean away from the opposite. Driving the real heading command (not the commander internals) keeps the test on the path a mouse takes. The 9/10/200 values double as the lexicographic trap: raw string sorting would answer 9, 200, 10.
    """
    table, column = _scores(window, 10, 200, 9)

    _click_heading(table, column)
    assert [row["count"] for row in table.roots] == [200, 10, 9]

    _click_heading(table, column)
    assert [row["count"] for row in table.roots] == [9, 10, 200]


def test_active_sort_shows_an_arrow_on_that_heading_only(window: tkfacade.Window) -> None:
    """The sorted column's heading gains a marker; others keep bare text.

    One active sort at a time is the coordinator's whole job: the arrow moving means the old commander was told to stand down when the new one reported in.
    """
    table = tkfacade.Table(
        window,
        columns=(
            TreeColumnSpec(name="count", incoming_converter=str, outgoing_converter=int),
            TreeColumnSpec(name="name"),
        ),
    )
    count = table.column("count")
    name = table.column("name")
    assert count is not None and name is not None

    _click_heading(table, count)

    assert count.heading.text.startswith("Count") and count.heading.text != "Count"
    assert name.heading.text == "Name"

    _click_heading(table, name)

    assert count.heading.text == "Count"
    assert name.heading.text != "Name"


def test_the_sort_arrow_is_a_unicode_11_glyph(window: tkfacade.Window) -> None:
    """The ascending and descending arrows carry near-universal font coverage.

    The glyphs are U+25B2 (▲) and U+25BC (▼) — Unicode 1.1 code points with near-universal default-font coverage, chosen over U+2BC5/U+2BC6 (⯅/⯆, Unicode 7.0) which rendered as hollow boxes on Linux Mint. The assertion pins the specific character so an edit that swaps back or replaces with another unrendered codepoint is caught. Both Unicode spellings are denied for good measure.
    """
    table = tkfacade.Table(
        window,
        columns=(
            TreeColumnSpec(name="count", incoming_converter=str, outgoing_converter=int),
            TreeColumnSpec(name="name"),
        ),
    )
    count = table.column("count")
    assert count is not None

    _click_heading(table, count)

    assert "▼" in count.heading.text
    assert "▲" not in count.heading.text
    assert "⯅" not in count.heading.text
    assert "⯆" not in count.heading.text

    _click_heading(table, count)

    assert "▲" in count.heading.text
    assert "▼" not in count.heading.text


def test_insert_sorts_into_an_active_sort(window: tkfacade.Window) -> None:
    """With a sort active, an index-less insert lands in sorted position.

    The sorted-insert promise, driven through the programmatic sort_rows path to prove it arms the same machinery as a click (it routes through the column's commander, keeping insert-time sorting and the arrow in step). 15 lands strictly inside the run, so an append-only implementation fails on position rather than on order.
    """
    table, column = _scores(window, 30, 10, 20)
    table.sort_rows(column, ascending=True)

    table.insert(count=15)

    assert [row["count"] for row in table.roots] == [10, 15, 20, 30]


def test_insert_honors_an_explicit_index_despite_a_sort(window: tkfacade.Window) -> None:
    """An explicit index — even ``"end"`` — bypasses sorted placement.

    The escape hatch is documented down to its subtlest case: an *explicit* "end" is honored even though it equals the default landing spot before sorting-in. Table.insert distinguishes index=None from index="end" for exactly this, and collapsing the two — the natural refactor — puts 20 between 10 and 30 and fails here.
    """
    table, column = _scores(window, 10, 30)
    table.sort_rows(column, ascending=True)

    table.insert(count=20, index="end")

    assert [row["count"] for row in table.roots] == [10, 30, 20]


def test_sort_rows_without_a_sort_keeps_insertion_order(window: tkfacade.Window) -> None:
    """Before any sort, rows stand in insertion order and inserts append.

    The quiet default the sorted-insert tests lean on: _sort_in must be a no-op while no sort is active, or every table would be implicitly sorted from birth. Deliberately unsorted values prove nothing reorders them behind the caller's back.
    """
    table, _column = _scores(window, 30, 10)

    table.insert(count=20)

    assert [row["count"] for row in table.roots] == [30, 10, 20]


def test_add_column_at_an_index_leaves_the_new_column_empty(window: tkfacade.Window) -> None:
    """A column inserted into a table starts blank, and the headings still sort.

    Table reaches Tree.add_column through super(), so the cell-preserving behaviour is inherited rather than its own — but Table owns the full signature and wires a commander onto the new column afterwards, so it is the plausible place for a future override to grow its own snapshot and reintroduce the shift. The heading assertion is what makes this more than a duplicate of the tree-side test: the new column's commander has to be installed by the same call that preserves the cells.
    """
    table = tkfacade.Table(
        window,
        columns=(TreeColumnSpec(name="name"), TreeColumnSpec(name="count")),
    )
    row = table.insert(name="bolt", count="7")

    column = table.add_column("z", 1)

    assert dict(row.tree._treeview.set(row.iid)) == {"name": "bolt", "z": "", "count": "7"}
    # the sort cycle is installed on the widget even with no user command held
    assert str(table._treeview.heading(column.name, "command")) != ""


def test_add_column_composes_its_heading_options_into_the_sort(window: tkfacade.Window) -> None:
    """A ``heading_text`` observable drives the base; ``heading_command`` runs after a sort.

    The two options Table withholds from its base call, and the only ones whose behaviour differs from Tree's: both are *composed* into the sort machinery rather than installed on the heading, so the command runs after the click-driven sort instead of replacing it, and the observable supplies the base text the arrow is appended to — the merged heading_text taking either a string, which passes through to visit, or the observable withheld here.  The text_observable assertion is the one that earns its place. Every other assertion here passes even if the two options are forwarded to Tree.add_column as well as given to the commander — the end state looks right because the commander installs itself second and wins. What forwarding really does is leave a *second* watch registered through the heading's own machinery, and `heading.text_observable` reading None is what says the commander is the sole owner the class claims to be. Verified by mutation: without that line, withholding and forwarding are indistinguishable.  The text is asserted by prefix rather than equality so the arrow glyph stays the commander's business, with `!= "Amount"` pinning that some suffix is re-applied on an external write.
    """
    table = tkfacade.Table(window, columns=(TreeColumnSpec(name="name"),))
    caption = tkfacade.ObservableStr("Quantity")
    clicks: list[int] = []

    column = table.add_column(
        "count",
        heading_text=caption,
        heading_command=lambda: clicks.append(1),
    )
    _click_heading(table, column)

    assert clicks == [1]
    assert column.heading.text.startswith("Quantity")
    assert column.heading.text_observable is None

    caption.value = "Amount"

    assert column.heading.text.startswith("Amount")
    assert column.heading.text != "Amount"


def test_a_heading_observable_outliving_its_table_goes_quiet(
    root: Root, window: tkfacade.Window
) -> None:
    """A write to the user observable after the table dies raises nothing anywhere.

    The commander's write watcher re-rendered the heading unguarded, where the plain-Tree path suppresses TclError for exactly this — so once the table died without drop_column, every later write to the caller's value dumped "invalid command name" through the callback-exception route, forever. A watcher's raise is reported rather than re-raised at the assignment, which is why the assertion reads a patched report_callback_exception rather than pytest.raises: the report route is where the noise lands, and an empty list is the whole claim. The table dies by raw Tk destroy because orderly teardown through drop_column was precisely the mask.
    """
    caption = tkfacade.ObservableStr("Name")
    table = tkfacade.Table(window, columns=(TreeColumnSpec(name="a", heading_text=caption),))
    dumped: list[BaseException] = []
    root._tk.report_callback_exception = lambda *exc: dumped.append(exc[1])

    table._tk.destroy()
    caption.value = "after death"

    assert dumped == []


def test_adding_a_column_keeps_the_active_sort_arrow(window: tkfacade.Window) -> None:
    """A column added mid-sort leaves the sorted heading's arrow and command alone.

    Table used to re-install every heading itself after a column change, because reconfiguring ``columns`` reset them; Tree now carries them across, and that call is gone. This is what says the removal was safe. The arrow is checked by comparing against the pre-add text rather than a literal glyph, with ``!= "Count"`` pinning that some arrow is there at all — a heading reset to its title-cased default would satisfy an equality test against the bare name. The second click is the part a text assertion alone would miss: the command has to survive too, or the sort silently stops cycling.
    """
    table, column = _scores(window, 3, 1, 2)
    _click_heading(table, column)
    sorted_text = column.heading.text

    table.add_column("note")

    assert column.heading.text == sorted_text
    assert column.heading.text != "Count"
    assert [row["count"] for row in table.roots] == [3, 2, 1]

    _click_heading(table, column)

    assert [row["count"] for row in table.roots] == [1, 2, 3]


def test_a_manual_reorder_retires_the_sort(window: tkfacade.Window) -> None:
    """After a move, the arrow goes and later inserts append instead of bisecting.

    sort_in places a row by binary search, which needs the other rows to already stand in the sorted order. A move breaks that and used to leave the sort marked active anyway, so the next index-less insert bisected an unsorted list and put the row somewhere arbitrary with nothing raised — 25 landed between 20 and 30 in a table reading [20, 30, 10]. Retiring the sort on any placement it did not choose fixes the placement and the arrow together, which is why both are asserted. The re-sort at the end is the other half: retiring must not be one-way, or a table could never be sorted again after a move.
    """
    table, column = _scores(window, 10, 20, 30)
    table.sort_rows(column, ascending=True)

    assert column.heading.text != "Count"

    table.move(table.roots[0], index=2)

    assert column.heading.text == "Count"

    table.insert(count=25)

    assert [row["count"] for row in table.roots] == [20, 30, 10, 25]

    table.sort_rows(column, ascending=True)

    assert [row["count"] for row in table.roots] == [10, 20, 25, 30]
    assert column.heading.text != "Count"


def test_sorting_does_not_retire_itself(window: tkfacade.Window) -> None:
    """A sort reordering its own rows keeps its arrow and keeps cycling.

    The trap in retiring a sort on move: Tree.sort_rows reorders through move, so a Table sorting itself would stand its own sort down on the first row it placed — the arrow vanishing and the next click starting the cycle over rather than toggling. The mechanism is split from the public method for exactly this, and the second click is what proves it: a self-retired sort re-enters at descending, so the rows would come back descending rather than ascending.
    """
    table, column = _scores(window, 10, 30, 20)

    _click_heading(table, column)
    descending = column.heading.text
    _click_heading(table, column)

    assert [row["count"] for row in table.roots] == [10, 20, 30]
    assert column.heading.text != descending
    assert column.heading.text != "Count"


def test_reattaching_a_row_retires_the_sort(window: tkfacade.Window) -> None:
    """``show_row`` under an active sort drops the arrow; inserts append again.

    reattach restores a recorded position, not one the sort chose — the 50 lands back at its remembered index 1, above the 30 sorted in while it was hidden, which is exactly the out-of-order state the retirement exists for. It used to leave the sort standing: the arrow claimed an order the rows no longer had, and the next index-less insert bisected an unsorted list and landed somewhere arbitrary. The arrow-down assertion is the retirement itself, and the trailing 40 appending — rather than bisecting the broken order — pins that insert stopped trusting a sort that no longer holds.
    """
    table, column = _scores(window, 10, 50)
    table.sort_rows(column, ascending=True)
    hidden = table.roots[1]
    table.hide_row(hidden.iid)
    table.insert(count=30)

    table.show_row(hidden.iid)

    assert column.heading.text == "Count"
    assert [row["count"] for row in table.roots] == [10, 50, 30]

    table.insert(count=40)

    assert [row["count"] for row in table.roots] == [10, 50, 30, 40]


def test_a_failed_sort_in_retires_the_sort(window: tkfacade.Window) -> None:
    """An insert whose sort-in cannot convert raises, appends, and drops the arrow.

    The documented conversion failure — the sort column omitted, its empty cell unconvertible — propagates after the row is already appended out of order, and unlike every other placement the sort did not choose, nothing stood the sort down: the arrow claimed an order the rows no longer had, and the next valid index-less insert bisected the unsorted list, comparing against the empty cell and raising out of an insert whose own values were fine. The arrow-down assertion is the retirement; the raw-cell reads (the empty cell cannot pass the int converter) pin both the append-at-end the docstring promises and the follow-up insert appending instead of raising — the poisoned call this entry was really about.
    """
    table, column = _scores(window, 3, 1, 2)
    table.sort_rows(column, ascending=True)

    with pytest.raises(ValueError):
        table.insert()

    assert column.heading.text == "Count"
    raw = [table._treeview.set(row.iid, "count") for row in table.roots]
    assert raw == ["1", "2", "3", ""]

    table.insert(count=0)

    raw = [table._treeview.set(row.iid, "count") for row in table.roots]
    assert raw == ["1", "2", "3", "", "0"]


def test_an_empty_heading_observable_is_seeded_on_a_table_too(window: tkfacade.Window) -> None:
    """Both Table doors seed an empty observable with the resolved heading text.

    TreeColumnSpec.heading_text promises an empty observable is seeded with the title-cased name, and visit keeps it — but the Table doors strip the observable from the spec before visit and hand it to the sort commander, which used to fall back to the heading text for its own base and never write back. Identical code then diverged by class: value = value + " (3)" titled a Tree "Alpha (3)" and blanked a Table to " (3)". Both doors are driven because each builds its own commander, and the derive-from-the-value write is the idiom the seeding exists for — its assertion is the cost, the two seed reads are the mechanism.
    """
    built = tkfacade.ObservableStr("")
    added = tkfacade.ObservableStr("")
    table = tkfacade.Table(
        window,
        columns=(TreeColumnSpec(name="alpha", heading_text=built),),
    )
    column = table.add_column("count", heading_text=added)

    assert built.value == "Alpha"
    assert added.value == "Count"

    built.value = built.value + " (3)"

    assert table.column("alpha") is not None
    assert column.heading.text.startswith("Count")
    heading = table.column("alpha")
    assert heading is not None
    assert heading.heading.text == "Alpha (3)"


def test_a_cell_write_under_an_active_sort_keeps_the_sort_honest(window: tkfacade.Window) -> None:
    """Editing the sorted column re-places the row; an unorderable value retires the sort.

    The retirement discipline covered structural placements only, and a value write was a fourth door to an order the sort did not choose: editing the sorted [1, 2, 3] to [99, 2, 3] left the arrow claiming an order the rows no longer had, and the next index-less insert bisected the unsorted list into [99, 2, 3, 4]. A write is now the same maintenance an insert gets — the changed row sorts back in, so the arrow stays truthful — which the follow-up insert pins from the outside: the 4 can only land between 3 and 99 over rows that are really sorted. clear() drives the other branch: the blanked cell cannot pass the int converter, so the sort stands down (arrow read) rather than raising out of a write that already landed, and the rows stay where the retirement left them.
    """
    table, column = _scores(window, 1, 2, 3)
    table.sort_rows(column, ascending=True)

    table.roots[0]["count"] = 99

    assert [row["count"] for row in table.roots] == [2, 3, 99]
    assert column.heading.text != "Count"

    table.insert(count=4)

    assert [row["count"] for row in table.roots] == [2, 3, 4, 99]

    table.roots[0].clear()

    assert column.heading.text == "Count"
    raw = [table._treeview.set(row.iid, "count") for row in table.roots]
    assert raw == ["", "3", "4", "99"]


def test_the_heading_command_property_composes_into_the_sort(window: tkfacade.Window) -> None:
    """Assigning ``heading.command`` on a Table keeps the click cycle sorting.

    The commander promises a user command "is composed rather than clobbered", and the spec/add_column door kept it — but the inherited property setter wrote the heading option raw, so heading.command = cb replaced the sort cycle wholesale: clicks ran the callback and nothing else, no sort, no arrow, no error anywhere. The first click pins all three composed halves at once — rows descending, arrow up, callback run. The None leg pins the asymmetry that matters: None removes only the *user* command (the second click still toggles to ascending, and clicks stays [1]), where the raw write's None would have unbound the heading entirely.
    """
    table, column = _scores(window, 2, 1, 3)
    clicks: list[int] = []

    column.heading.command = lambda: clicks.append(1)
    _click_heading(table, column)

    assert clicks == [1]
    assert [row["count"] for row in table.roots] == [3, 2, 1]
    assert column.heading.text != "Count"

    column.heading.command = None
    _click_heading(table, column)

    assert clicks == [1]
    assert [row["count"] for row in table.roots] == [1, 2, 3]


def test_clearing_the_sorted_column_retires_the_sort(window: tkfacade.Window) -> None:
    """``TreeColumn.clear`` under an active sort stands it down; inserts append again.

    The _cell_changed hook covers every public mapping-face write — TreeRow.__setitem__, TreeRow.clear, TreeColumn.__setitem__ — and TreeColumn.clear was the one that didn't call it, writing raw per-row blanks and returning: the arrow stayed up over cells that no longer convert, and the next index-less insert, its own value perfectly valid, raised ValueError out of the bisect — the poisoned call the failed-sort-in fix was really about, reintroduced through this door. The converting column is the point: identity converters tie on "" and order trivially, which is what hid it. The arrow read is the retirement, and the follow-up insert appending cleanly is the poisoned call refuted.
    """
    table, column = _scores(window, 1, 2, 3)
    table.sort_rows(column, ascending=True)

    column.clear()

    assert column.heading.text == "Count"

    table.insert(count=5)

    raw = [table._treeview.set(row.iid, "count") for row in table.roots]
    assert raw == ["", "", "", "5"]


def test_a_failed_sort_claims_nothing(window: tkfacade.Window) -> None:
    """A raising sort leaves no arrow and no claim, and a prior sort survives it.

    _update committed mode, arrow, and the active slot before _sort() could raise, with no rollback — so a sort whose key didn't convert left the rows in their old order under a rendered arrow, with every other commander already reset, and the next index-less insert bisected the unsorted list. sorted() raises before any row moves, which is what makes claim-after-sort sufficient: on failure nothing moved, so whatever order held before still holds. The first leg pins the no-claim half (no arrow, insertion order intact); the second pins the rollback's other beneficiary — a prior sort's arrow and order survive a later failed sort untouched, where the old code had already reset its commander to NONE.
    """
    table = tkfacade.Table(
        window,
        columns=(
            TreeColumnSpec(name="name"),
            TreeColumnSpec(name="count", incoming_converter=str, outgoing_converter=int),
        ),
    )
    for name, count in (("b", 1), ("a", 3), ("c", 2)):
        table.insert(values={"name": name, "count": count})
    table.insert(values={"name": "d"})  # count omitted: its empty cell won't convert
    count_column = table.column("count")
    name_column = table.column("name")
    assert count_column is not None and name_column is not None

    with pytest.raises(ValueError):
        table.sort_rows(count_column)

    assert count_column.heading.text == "Count"
    assert [table._treeview.set(row.iid, "name") for row in table.roots] == ["b", "a", "c", "d"]

    table.sort_rows(name_column)
    with pytest.raises(ValueError):
        table.sort_rows(count_column)

    assert name_column.heading.text != "Name"
    assert [table._treeview.set(row.iid, "name") for row in table.roots] == ["a", "b", "c", "d"]


def test_a_heading_click_on_unconvertible_values_stands_the_sort_down(
    window: tkfacade.Window,
) -> None:
    """A click on a column whose values won't sort retires the sort without raising.

    Before the fix cycle escaped the Tk callback with the _update re-raise, dropping both the heading command and ACTIVATED — and more importantly, letting an exception propagate from a Tk binding with nobody on the other side to catch it. The catch-and-stand-down posture mirrors _cell_changed, which already handled the same failure on the write path. The heading command and ACTIVATED are intentionally not fired: the sort did not complete, so there is nothing to react to.
    """
    table = tkfacade.Table(
        window,
        columns=(
            TreeColumnSpec(name="name", incoming_converter=str, outgoing_converter=str),
            TreeColumnSpec(name="score", incoming_converter=str, outgoing_converter=int),
        ),
    )
    for name, score in (("a", 3), ("b", 1), ("c", 2)):
        table.insert(values={"name": name, "score": score})
    table.insert(values={"name": "d"})  # score omitted: empty cell fails int converter
    score_column = table.column("score")
    assert score_column is not None

    _click_heading(table, score_column)

    assert score_column.heading.text == "Score"
    assert [table._treeview.set(row.iid, "name") for row in table.roots] == ["a", "b", "c", "d"]


def test_a_heading_command_is_not_run_when_the_sort_fails_to_convert(
    window: tkfacade.Window,
) -> None:
    """The heading command watches the sort; a failed sort is not a completed one."""
    fired: list[str] = []
    table = tkfacade.Table(
        window,
        columns=(
            TreeColumnSpec(name="name", incoming_converter=str, outgoing_converter=str),
            TreeColumnSpec(
                name="score",
                incoming_converter=str,
                outgoing_converter=int,
                heading_command=lambda: fired.append("score"),
            ),
        ),
    )
    for row_name, row_score in (("a", 3), ("b", 1)):
        table.insert(values={"name": row_name, "score": row_score})
    table.insert(values={"name": "c"})  # score omitted
    score_column = table.column("score")
    assert score_column is not None

    _click_heading(table, score_column)

    assert fired == []


def test_the_text_observable_property_composes_into_the_sort(window: tkfacade.Window) -> None:
    """Assigning ``heading.text_observable`` on a sorted Table drives the base, arrow intact.

    The property setter installed the plain-Tree raw watch with no funnel like the command's, so the observable and the commander fought over the heading: assigning wiped the arrow while the sort stayed armed, a click clobbered the user's text with the stale base plus arrow, and each later write clobbered back. The setter routes through _set_heading_observable and the commander adopts the observable as its base. Every assertion is one round of the old fight refuted: the seed honors the spec doors' empty-observable promise, the arrow surviving the assign and the write is the no-wipe half, and the click keeping the user's text (observable untouched, rows re-sorted) is the no-clobber half.
    """
    table, column = _scores(window, 2, 1, 3)
    table.sort_rows(column, ascending=True)
    caption = tkfacade.ObservableStr("")

    column.heading.text_observable = caption

    assert caption.value == "Count"
    assert column.heading.text.startswith("Count")
    assert column.heading.text != "Count"

    caption.value = "Points"

    assert column.heading.text.startswith("Points")
    assert column.heading.text != "Points"

    _click_heading(table, column)

    assert caption.value == "Points"
    assert column.heading.text.startswith("Points")
    assert [row["count"] for row in table.roots] == [3, 2, 1]


def test_a_commanded_columns_property_answers_the_user_command(window: tkfacade.Window) -> None:
    """What was assigned is what reads back, never the sort cycle.

    On a commanded column the cycle is machinery; the property door
    holds the caller's command, and None removes only that.
    """
    table, column = _scores(window, 2, 1)

    def held() -> None:
        return None

    assert column.heading.command is None

    column.heading.command = held

    assert column.heading.command is held

    column.heading.command = None

    assert column.heading.command is None
    # the cycle stays installed throughout
    assert str(table._treeview.heading(column.name, "command")) != ""


def test_writing_heading_text_on_a_sorted_table_preserves_the_arrow(
    window: tkfacade.Window,
) -> None:
    """Setting heading text on a commanded column keeps the sort arrow.

    The text setter used to write straight to Tk, stripping the arrow off an active sort while leaving the sort standing. The setter now goes through _set_heading_text, which the Table routes into the commander's _base — the commander re-renders, base plus arrow. The arrow assertion pins the routing; the prefix read is the user's text surviving.
    """
    table = tkfacade.Table(
        window,
        columns=(
            TreeColumnSpec(name="count", incoming_converter=str, outgoing_converter=int),
            TreeColumnSpec(name="name"),
        ),
    )
    for row_count, row_name in ((2, "b"), (1, "a"), (3, "c")):
        table.insert(values={"count": row_count, "name": row_name})
    count_col = table.column("count")
    assert count_col is not None
    _click_heading(table, count_col)
    assert "▼" in count_col.heading.text

    count_col.heading.text = "Total"

    assert count_col.heading.text.startswith("Total")
    assert "▼" in count_col.heading.text


def test_writing_heading_text_routes_through_the_commander_not_around_it(
    window: tkfacade.Window,
) -> None:
    """After a heading-text write, the arrow survives a re-render from a sibling click.

    The stale-base clobber: before the fix, clicking any other heading re-rendered every commander, and the old _base overwrote the user's text — the user wrote "Qty", name.click rendered "Count ▼" back (the base had never changed). Now the write goes through _set_heading_text and updates _base, so "Qty" survives the re-render. The click on "name" both re-renders (tests base survival) and retires the sort (the arrow leaves "count", confirming it was not stripped earlier).
    """
    table = tkfacade.Table(
        window,
        columns=(
            TreeColumnSpec(name="count", incoming_converter=str, outgoing_converter=int),
            TreeColumnSpec(name="name"),
        ),
    )
    for row_count, row_name in ((2, "b"), (1, "a"), (3, "c")):
        table.insert(values={"count": row_count, "name": row_name})
    count_col = table.column("count")
    name_col = table.column("name")
    assert count_col is not None and name_col is not None
    _click_heading(table, count_col)

    count_col.heading.text = "Qty"

    assert "Qty ▼" in count_col.heading.text

    _click_heading(table, name_col)

    assert "Qty" in count_col.heading.text
    assert "▼" not in count_col.heading.text
