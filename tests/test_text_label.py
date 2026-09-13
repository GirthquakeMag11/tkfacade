""":class:`~tkfacade.TextLabel`: the text-only half of the split Label.

The split gave the text its own widget, so ``justify`` can now mean what
it says: it reads as the horizontal half of the label's anchor and
writes by replacing only that half. These pin the text round-trip and
the justify-to-anchor mapping, the regression the old ``Label`` could
never satisfy. Everything needs a real Tk interpreter, so the suite
rides the ``window`` fixture under the ``gui`` marker.
"""

from typing import cast

import pytest

import tkfacade
from conftest import Pump

pytestmark = pytest.mark.gui


def test_a_text_label_answers_its_text_and_wraplength(window: tkfacade.Window, pump: Pump) -> None:
    """Text writes round-trip through the widget, and wraplength has Tk's 0 for unset.

    The label reads straight through Tk rather than caching, so a write
    through the property must be visible back through it in the same
    process. wraplength is the one member with a boundary worth
    asserting both ways: unset answers 0 rather than the empty string
    ttk reports, and assigning 0 returns it to that state.
    """
    label = tkfacade.TextLabel(window, text="hello")
    label.grid(row=0, column=0)
    pump(window)

    assert label.text == "hello"

    label.text = "world"
    label.wraplength = 60

    assert label.text == "world"
    assert label.wraplength == 60

    label.wraplength = 0

    assert label.wraplength == 0


def test_justify_right_moves_the_text_to_the_right(window: tkfacade.Window, pump: Pump) -> None:
    """``justify = "right"`` actually right-justifies the text, through the anchor.

    The regression the old ``Label`` carried in `Problems.md`: justify
    only aligned a multi-line block's lines against each other and did
    nothing at all to a single line. The split makes anchor free, so
    justify now writes it: right lands on ``"e"``. Read off Tk's own
    anchor, which is the option the renderer honors.
    """
    label = tkfacade.TextLabel(window, text="hi", anchor="w")
    label.grid(row=0, column=0)
    pump(window)

    label.justify = "right"

    assert str(label._tk.cget("anchor")) == "e"
    assert label.justify == "right"


def test_justify_keeps_the_vertical_half_of_the_anchor(window: tkfacade.Window, pump: Pump) -> None:
    """A justify write replaces only the anchor's horizontal component.

    The anchor is the full compass word, so justify must not clobber
    the vertical placement a caller chose: ``"n"`` plus right is
    ``"ne"``, and a bottom-right ``"se"`` plus left becomes ``"sw"``.
    """
    label = tkfacade.TextLabel(window, text="hi", anchor="n")
    label.grid(row=0, column=0)
    pump(window)

    label.justify = "right"
    assert label.anchor == "ne"

    label.anchor = "se"
    label.justify = "left"
    assert str(label._tk.cget("anchor")) == "sw"


def test_justify_reads_the_horizontal_half_of_the_anchor(
    window: tkfacade.Window, pump: Pump
) -> None:
    """The justify getter derives from the anchor rather than storing a twin.

    One value, one place: setting the anchor and asking justify must
    agree, whatever the corner the anchor names.
    """
    label = tkfacade.TextLabel(window, text="hi", anchor="ne")
    label.grid(row=0, column=0)
    pump(window)

    assert label.justify == "right"

    label.anchor = "sw"
    assert str(label._tk.cget("anchor")) == "sw"
    assert cast(tkfacade.Justify, label.justify) == "left"


def test_width_round_trips_and_none_sizes_to_the_text(window: tkfacade.Window, pump: Pump) -> None:
    """A width in characters round-trips, and None is Tk's own auto-width.

    ttk reads a character width of 0 as "size to the text", so the
    wrapper reports that as None and writes None back to it.
    """
    label = tkfacade.TextLabel(window, text="hi")
    label.grid(row=0, column=0)
    pump(window)

    assert label.width is None

    label.width = 12
    assert label.width == 12

    label.width = None
    assert label.width is None
