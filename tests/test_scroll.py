"""Navigating a scrollable widget: four directions, an offset, and a reach.

The scrollbar item, exercised through the two widgets that own
bars. What is under test is the widget's own navigation surface, and
the bars' two doors beside it: the :class:`~tkfacade.ScrollbarSpec`
that declares a bar at construction, and the :class:`~tkfacade.Scrollbar`
facet the widget answers afterwards — placement, auto-hide, and
shown-ness, live.
"""

import pytest

import tkfacade

pytestmark = pytest.mark.gui

LINES = "\n".join(
    f"line {index} with a tail long enough to overflow sideways" for index in range(200)
)


def _scrolling_box(window: tkfacade.Window) -> tkfacade.TextBox:
    """A realized text box holding more than it can show, on both axes."""
    box = tkfacade.TextBox(
        window, LINES, width=20, height=5, wrap_word=False, horizontal_scrollbar=True
    )
    box.grid(row=0, column=0)
    window._tk.update()
    return box


def test_the_four_directions_move_their_own_axis(window: tkfacade.Window) -> None:
    """Each direction moves the content the way its name says.

    The whole navigation vocabulary in one pass, each direction checked against the one before it rather than against a number: down then up must land between the start and the deepest point, and the same sideways. Comparing movements beats pinning fractions, which would tie the test to a font and a window size.
    """
    box = _scrolling_box(window)

    box.scroll_down(3)
    window._tk.update()
    lowered = box.y_offset
    box.scroll_up(1)
    window._tk.update()
    raised = box.y_offset
    box.scroll_right(4)
    window._tk.update()
    rightward = box.x_offset
    box.scroll_left(2)
    window._tk.update()
    leftward = box.x_offset

    assert 0.0 < raised < lowered
    assert 0.0 < leftward < rightward


def test_scrolling_stops_at_the_ends(window: tkfacade.Window) -> None:
    """Moving further than there is content stops rather than overshooting.

    Tk's own clamping, relied on rather than reimplemented: a move past either end lands on the end, and asking again from there changes nothing. The second scroll_down is what makes this a claim about stopping rather than about one lucky number — an implementation that kept accumulating would drift on the repeat.
    """
    box = _scrolling_box(window)

    box.scroll_up(50)
    window._tk.update()
    assert box.y_offset == pytest.approx(0.0)

    box.scroll_down(500)
    window._tk.update()
    settled = box.y_offset

    assert settled > 0.0
    assert not box.can_scroll_down
    box.scroll_down(500)
    window._tk.update()
    assert box.y_offset == settled


def test_a_negative_amount_is_refused(window: tkfacade.Window) -> None:
    """A direction takes how far, not which way; a negative amount raises.

    The four directions exist so nobody reasons about signs, and letting scroll_down(-1) quietly mean scroll_up(1) would put the sign back. The unmoved offset pins it as a refusal rather than a half-move.
    """
    box = _scrolling_box(window)

    with pytest.raises(ValueError, match="not negative"):
        box.scroll_down(-1)
    assert box.y_offset == pytest.approx(0.0)


def test_scroll_to_places_each_axis_and_leaves_the_other_alone(
    window: tkfacade.Window,
) -> None:
    """One call moves either axis or both; an omitted axis does not move.

    The absolute move, in all three of its shapes: one axis, the other axis, and both at once. The middle assertions are what earn the "leaves the other alone" clause — after moving y then x, both are still where they were put, so neither call reset the other.
    """
    box = _scrolling_box(window)

    box.scroll_to(y=0.5)
    window._tk.update()
    assert box.y_offset > 0.0
    assert box.x_offset == pytest.approx(0.0)

    box.scroll_to(x=0.5)
    window._tk.update()
    moved_x, moved_y = box.x_offset, box.y_offset
    box.scroll_to(x=0.0, y=0.0)
    window._tk.update()

    assert moved_x > 0.0
    assert moved_y > 0.0
    assert (box.x_offset, box.y_offset) == (0.0, 0.0)


def test_an_unreachable_fraction_is_refused(window: tkfacade.Window) -> None:
    """A fraction outside 0.0 to 1.0 raises; Tk would clamp it silently.

    The refusal of what Tk would take and act on wrongly: `moveto 9.0` is silently clamped by Tk (`hazards/tkinter.md`, *Scrolling*), so a caller who miscalculated a fraction gets a scroll rather than a report. Both ends of the range are checked, and the unmoved offset proves nothing landed before the raise.
    """
    box = _scrolling_box(window)
    box.scroll_to(y=0.5)
    window._tk.update()
    before = box.y_offset

    with pytest.raises(ValueError, match="fraction"):
        box.scroll_to(y=9.0)
    with pytest.raises(ValueError, match="fraction"):
        box.scroll_to(x=-0.5)

    assert box.y_offset == before


def test_the_offsets_read_live_after_the_users_own_scroll(window: tkfacade.Window) -> None:
    """An offset answers from Tk, not from a Python-side copy.

    Tested the way the original check words it: move the widget behind the wrapper's back, through Tk directly, and re-read the property. A wrapper caching its own last write would still say 0.0 here.
    """
    box = _scrolling_box(window)
    assert box.y_offset == pytest.approx(0.0)

    box._text.yview("moveto", 0.4)
    window._tk.update()

    assert box.y_offset == pytest.approx(box._text.yview()[0])
    assert box.y_offset > 0.0


def test_the_reach_answers_for_each_direction(window: tkfacade.Window) -> None:
    """Each can_scroll_* is True where there is content and False at the end.

    "Can I scroll left?" answering itself, and every direction asserted in both of its states by moving between the two corners — a predicate stuck on True or False would pass one half and fail the other. The readings are captured before comparison: asserting a property mid-test narrows it, and mypy then calls the opposite reading unreachable.
    """
    box = _scrolling_box(window)
    at_origin = (box.can_scroll_up, box.can_scroll_down, box.can_scroll_left)

    box.scroll_to(x=1.0, y=1.0)
    window._tk.update()
    at_far_end = (box.can_scroll_up, box.can_scroll_down, box.can_scroll_left)

    assert at_origin == (False, True, False)
    assert at_far_end == (True, False, True)


def test_a_widget_with_no_bar_still_navigates(window: tkfacade.Window) -> None:
    """Scrolling belongs to the widget, not to the scrollbar.

    The separation the rebuild turns on: a scrollbar is one way to move content, not what gives a widget the ability to be moved. The child count is the proof no bar exists, so the navigation that follows is genuinely the widget's own.
    """
    bare = tkfacade.TextBox(window, LINES, width=20, height=5, vertical_scrollbar=False)
    bare.grid(row=0, column=0)
    window._tk.update()

    assert sorted(child.winfo_class() for child in bare.children.values()) == ["Text"]
    assert bare.can_scroll_down
    bare.scroll_down(3)
    window._tk.update()

    assert bare.y_offset > 0.0


def test_a_spec_hides_a_useless_bar_and_brings_it_back(window: tkfacade.Window) -> None:
    """auto_hide leaves the layout while everything fits, and returns when it stops.

    The spec doing the one job it exists for: saying what kind of bar to build, at the only moment a caller can say it, since no bar is ever handed back. Both directions are asserted because a bar that leaves and never returns is the failure worth catching, and the content grows through the box's own public surface rather than a poke at Tk.
    """
    box = tkfacade.TextBox(
        window,
        "one line",
        width=20,
        height=5,
        vertical_scrollbar=tkfacade.ScrollbarSpec(auto_hide=True),
    )
    box.grid(row=0, column=0)
    window._tk.update()
    while_fitting = bool(box._scroll_bars["vertical"].winfo_manager())

    box.text = LINES
    window._tk.update()
    once_overflowing = bool(box._scroll_bars["vertical"].winfo_manager())

    assert (while_fitting, once_overflowing) == (False, True)


def test_a_tree_navigates_through_the_same_contract(window: tkfacade.Window) -> None:
    """The base serves the tree exactly as it serves the text box.

    The contract tested over both implementations: the tree reaches the same base through a different inner widget, so a base that had quietly specialised to the text box fails here. A step is a row for a tree where it is a line for a box, which is why the assertion is on movement rather than on a distance.
    """
    tree = tkfacade.Table(window, columns=(tkfacade.TreeColumnSpec(name="n"),), height=4)
    for index in range(60):
        tree.insert(n=str(index))
    tree.grid(row=0, column=0)
    window._tk.update()

    assert tree.can_scroll_down
    tree.scroll_down(2)
    window._tk.update()

    assert tree.y_offset > 0.0
    assert tree.can_scroll_up


def test_the_facet_answers_where_a_bar_exists_and_none_where_not(
    window: tkfacade.Window,
) -> None:
    """Each axis answers its facet exactly when its bar was asked for.

    The Menubar precedent: a bar exists by the constructor's word alone, and the facet is the afterwards — None is the honest answer for an axis that has nothing, not a facet that would raise on first touch.
    """
    box = _scrolling_box(window)
    bare = tkfacade.TextBox(window, vertical_scrollbar=False, horizontal_scrollbar=False)

    vertical = box.vertical_scrollbar
    assert vertical is not None
    assert isinstance(vertical, tkfacade.Scrollbar)
    assert bare.vertical_scrollbar is None
    assert bare.horizontal_scrollbar is None


def test_placement_round_trips_and_the_wiring_never_notices(
    window: tkfacade.Window,
) -> None:
    """A bar moved to the left gutter keeps driving and tracking.

    The probe's hand relocation (experiments/scroll_probe), now through the public door: placement is the bar's cell, the content's cell and the stretch weight, and the scroll protocol — coupling callables, not widgets — never notices any of it.
    """
    box = _scrolling_box(window)
    vertical = box.vertical_scrollbar
    assert vertical is not None

    assert vertical.placement == "right"

    vertical.placement = "left"
    window._tk.update()
    bar = box._scroll_bars["vertical"]

    assert vertical.placement == "left"
    assert int(bar.grid_info()["column"]) == 0
    assert int(box._text.grid_info()["column"]) == 1

    box.scroll_to(y=0.5)
    window._tk.update()

    assert box.y_offset > 0.0
    assert abs(bar.get()[0] - box.y_offset) < 0.001


def test_a_side_off_the_axis_is_refused_with_nothing_moved(
    window: tkfacade.Window,
) -> None:
    """A vertical bar refuses top and bottom, before any regridding.

    Tk would grid a bar anywhere and draw nonsense, so the refusal is the facade's, raised before the layout is touched — the same reject-what-Tk-would-take posture scroll_to holds for fractions.
    """
    box = _scrolling_box(window)
    vertical = box.vertical_scrollbar
    assert vertical is not None

    with pytest.raises(ValueError, match="sits at one of"):
        vertical.placement = "top"

    assert vertical.placement == "right"
    assert int(box._text.grid_info()["column"]) == 0


def test_a_spec_places_at_construction(window: tkfacade.Window) -> None:
    """ScrollbarSpec(placement=...) seats the bar before the caller looks.

    The two doors run one path: the spec's visit goes through the same setter the facet offers, so a wrong-axis spec raises at the widget's construction exactly as the live write would.
    """
    box = tkfacade.TextBox(
        window,
        LINES,
        width=20,
        height=5,
        wrap_word=False,
        vertical_scrollbar=tkfacade.ScrollbarSpec(placement="left"),
    )
    box.grid(row=0, column=0)
    window._tk.update()
    vertical = box.vertical_scrollbar
    assert vertical is not None

    assert vertical.placement == "left"
    assert int(box._scroll_bars["vertical"].grid_info()["column"]) == 0

    with pytest.raises(ValueError, match="sits at one of"):
        tkfacade.TextBox(window, vertical_scrollbar=tkfacade.ScrollbarSpec(placement="top"))


def test_auto_hide_toggles_live_and_round_trips_relocated(
    window: tkfacade.Window,
) -> None:
    """The facet toggles auto-hide after construction, in any gutter.

    Live auto-hide is what the spec-only door could never offer, and the relocated cell is the probe's grid_remove fact as a regression test: hiding remembers the left gutter as faithfully as the right one.
    """
    box = _scrolling_box(window)
    vertical = box.vertical_scrollbar
    assert vertical is not None
    vertical.placement = "left"
    bar = box._scroll_bars["vertical"]

    assert vertical.auto_hide is False
    seated: bool = vertical.shown
    assert seated is True

    box._text.delete("1.0", "end")
    vertical.auto_hide = True
    window._tk.update()
    hidden: bool = vertical.shown

    assert hidden is False

    box._text.insert("1.0", LINES)
    window._tk.update()
    returned: bool = vertical.shown

    assert returned is True
    assert int(bar.grid_info()["column"]) == 0


def test_both_bars_relocate_into_the_far_corner(window: tkfacade.Window) -> None:
    """Left and top together put the content at (1, 1), both axes live.

    The corner case the layout arithmetic owns: each bar's cell depends on the other's side, so the whole grid is rewritten from both held sides at once — asserted through the content landing at (1, 1) and both bars still tracking their axes.
    """
    box = _scrolling_box(window)
    vertical, horizontal = box.vertical_scrollbar, box.horizontal_scrollbar
    assert vertical is not None and horizontal is not None

    vertical.placement = "left"
    horizontal.placement = "top"
    window._tk.update()

    target = box._text.grid_info()
    assert (int(target["row"]), int(target["column"])) == (1, 1)

    box.scroll_to(x=0.3, y=0.5)
    window._tk.update()

    assert box.x_offset > 0.0 and box.y_offset > 0.0
    assert abs(box._scroll_bars["vertical"].get()[0] - box.y_offset) < 0.001
    assert abs(box._scroll_bars["horizontal"].get()[0] - box.x_offset) < 0.001
