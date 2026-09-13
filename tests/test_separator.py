""":class:`~tkfacade.Separator`: a themed rule, and the axis it runs along.

The smallest widget in the library, and one of two placed in the queue
as calibration probes: it holds no value, masters nothing, and offers a
single property. The suite is correspondingly short, and covers the
contract whole — the one property both ways, the refusal, and the
inherited halves that a separator still owes because every
:class:`~tkfacade.Widget` owes them.
"""

import tkinter as tk

import pytest

import tkfacade
from conftest import Pump

pytestmark = pytest.mark.gui


def test_it_defaults_to_a_horizontal_rule(window: tkfacade.Window) -> None:
    """A separator built with no axis divides top from bottom."""
    rule = tkfacade.Separator(window)

    assert rule.orient == "horizontal"


def test_the_axis_round_trips_both_ways(window: tkfacade.Window) -> None:
    """Either axis can be asked for at construction and reads back."""
    sideways = tkfacade.Separator(window, orient="horizontal")
    upright = tkfacade.Separator(window, orient="vertical")

    assert sideways.orient == "horizontal"
    assert upright.orient == "vertical"


def test_the_axis_is_assignable_after_construction(window: tkfacade.Window) -> None:
    """Unlike a paned frame's, a separator's axis can be changed.

    The regression guard for `hazards/tkinter.md`, *Query answers*: Tk answers an enumerated option with an index object that prints as the word and compares unequal to it. Every assertion above would fail on a raw pass-through, but only because they use ==; this one names the reason so a future reader knows the str() in the property is load-bearing rather than decoration.
    """
    rule = tkfacade.Separator(window)

    rule.orient = "vertical"
    assert rule.orient == "vertical"

    rule.orient = "horizontal"
    assert rule.orient == "horizontal"


def test_the_axis_reads_back_as_a_real_string(window: tkfacade.Window) -> None:
    """The property converts Tk's index object at the boundary."""
    rule = tkfacade.Separator(window)
    reading = rule.orient
    raw = rule._tk.cget("orient")

    assert reading == "horizontal"
    assert raw != "horizontal"
    assert str(raw) == reading


def test_a_nonsense_axis_is_refused(window: tkfacade.Window) -> None:
    """Tk raises on its own, loudly enough that no guard is owed."""
    with pytest.raises(tk.TclError, match="must be horizontal or vertical"):
        tkfacade.Separator(window, orient="sideways")  # type: ignore[arg-type]

    rule = tkfacade.Separator(window)
    with pytest.raises(tk.TclError, match="must be horizontal or vertical"):
        rule.orient = "diagonal"  # type: ignore[assignment]

    assert rule.orient == "horizontal"


def test_it_lays_out_and_binds_like_any_widget(window: tkfacade.Window, pump: Pump) -> None:
    """The inherited halves: geometry through Widget, events through the registrar."""
    rule = tkfacade.Separator(window, orient="horizontal")
    rule.grid(row=0, column=0, sticky="ew")
    pump(window)

    assert rule.winfo_ismapped()

    seen: list[tkfacade.Event] = []
    handle = rule.bind(tkfacade.PointerEnter(), seen.append)
    rule._tk.event_generate("<Enter>")

    assert len(seen) == 1
    assert seen[0].widget is rule

    handle.cancel()
    rule._tk.event_generate("<Enter>")

    assert len(seen) == 1
