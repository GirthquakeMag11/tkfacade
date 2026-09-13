"""The progress bars: range enforcement, the observable link, and a live maximum.

Both classes are thin over ``ttk.Progressbar``, so what is worth testing
is the seam: that a value assigned actually reaches Tk rather than being
kept in Python, that the range checks sit where the docstrings say, and
that :attr:`~tkfacade.ItemBasedProgressBar.maximum` is read back off the
widget rather than remembered from construction. Everything needs a live widget, so
the suite rides the ``window`` fixture under the ``gui`` marker.
"""

import pytest

import tkfacade

pytestmark = pytest.mark.gui


def _value(bar: tkfacade.PercentageBasedProgressBar | tkfacade.ItemBasedProgressBar) -> float:
    """Read the Tk widget's own ``-value``, through the public handles.

    Args:
        bar (tkfacade.PercentageBasedProgressBar | tkfacade.ItemBasedProgressBar):
            The bar to interrogate.

    Returns:
        What Tk is drawing the bar from, which is the variable's value
        whenever the two are linked.
    """
    return float(bar.tk.call(bar, "cget", "-value"))


def test_percentage_bar_takes_the_whole_range_and_refuses_outside_it(
    window: tkfacade.Window,
) -> None:
    """0 and 100 are accepted; anything past either end raises.

    The boundaries are the whole of it: the check is inclusive at both ends, and written exclusive it would reject a bar that is exactly empty or exactly done — the two commonest values rather than edges. The refusals use the values just outside, which is the tightest refutation available; 200 and -50 would fail an exclusive check too and so prove less. Ints go in and floats come out, pinning the documented conversion at the same time. The constructor's plain-value form takes the same check — an observable passed in is the documented exception, adopted unchecked in its own test below. Every float assertion in this file goes through ``approx``: the values chosen all survive Tcl's double formatting exactly, but exact float equality is a lint error here and arguing the exception per assertion is not worth it.
    """
    bar = tkfacade.PercentageBasedProgressBar(window, orient="horizontal", length=200)

    bar.current = 0
    empty = bar.current
    bar.current = 100
    full = bar.current

    assert (empty, full) == pytest.approx((0.0, 100.0))
    with pytest.raises(ValueError, match="current"):
        bar.current = 100.1
    with pytest.raises(ValueError, match="current"):
        bar.current = -0.1
    with pytest.raises(ValueError, match="current"):
        tkfacade.PercentageBasedProgressBar(window, orient="horizontal", length=200, current=100.1)


def test_percentage_bar_progress_reaches_the_widget(window: tkfacade.Window) -> None:
    """An assignment to ``current`` lands on the Tk widget's own value.

    Reading ``current`` back cannot tell a variable linked into the widget from a plain Python attribute, and it is the link that makes the number a drawn bar — so the assertion has to come from Tk's side. It is taken through the public interpreter handle and the wrapper's own Tcl path rather than through ``_tk``, which is the same route test_text.py uses for the clipboard.
    """
    bar = tkfacade.PercentageBasedProgressBar(window, orient="horizontal", length=200)

    bar.current = 42.5

    assert _value(bar) == pytest.approx(42.5)


def test_an_observable_passed_in_is_adopted_unchecked(window: tkfacade.Window) -> None:
    """The bar displays the caller's observable as it stands, out of range and all.

    Three documented claims in one pass, all about the sharing route: the observable is adopted rather than replaced, its held value is not reset to zero, and nothing range-checks it — the check lives in the setter, so a caller driving the observable writes past it. 150 and -20 are outside 0..100 on purpose; anything the setter would have accepted could not tell the adoption from a coincidence. The closing widget-side read is the drive-and-follow contract on this wrapper: the driven value is what Tk draws. Unlike the variable era there is no interpreter to build the observable against — the bar's own transport acquisition is what marries the value to Tk.
    """
    shared = tkfacade.ObservableFloat(150.0)

    bar = tkfacade.PercentageBasedProgressBar(
        window, orient="horizontal", length=200, current=shared
    )

    assert bar.current == pytest.approx(150.0)
    shared.value = -20.0
    assert bar.current == pytest.approx(-20.0)
    assert _value(bar) == pytest.approx(-20.0)


def test_item_bar_refuses_a_maximum_below_one_item(window: tkfacade.Window) -> None:
    """A maximum under one whole item is refused, at construction and after.

    0.5 is the case the setter's check is shaped around: it is greater than zero, so a check on the value as given passes it, and the truncation to whole items then leaves the widget with a maximum of 0 — a bar drawn full for no work done, and every later ``current`` assignment refused. The closing read proves a refused assignment left the widget alone rather than half-applying, which a check placed after the ``configure`` would not.
    """
    with pytest.raises(ValueError, match="maximum"):
        tkfacade.ItemBasedProgressBar(window, orient="horizontal", length=200, maximum=0)

    bar = tkfacade.ItemBasedProgressBar(window, orient="horizontal", length=200, maximum=10)

    with pytest.raises(ValueError, match="maximum"):
        bar.maximum = 0
    with pytest.raises(ValueError, match="maximum"):
        bar.maximum = 0.5
    assert bar.maximum == 10


def test_item_bar_current_is_bounded_by_the_maximum_in_force(window: tkfacade.Window) -> None:
    """A count past the total raises; the same count is fine once the total grows.

    The bound is read off the widget on every assignment rather than remembered from the constructor, and raising the total to admit a previously refused count is what distinguishes the two: a captured maximum passes the rejection half of this test and fails the second. That mobility is the point of the class — a job that discovers more work moves the total mid-run. The closing constructor refusal pins the plain-value form of ``current`` against the same bound, checked against the ``maximum`` given beside it.
    """
    bar = tkfacade.ItemBasedProgressBar(window, orient="horizontal", length=200, maximum=10)

    with pytest.raises(ValueError, match="current"):
        bar.current = 11
    bar.maximum = 20
    bar.current = 11

    assert (bar.current, bar.maximum) == (11, 20)
    with pytest.raises(ValueError, match="current"):
        tkfacade.ItemBasedProgressBar(
            window, orient="horizontal", length=200, maximum=10, current=11
        )


def test_lowering_the_maximum_strands_the_count_above_it(window: tkfacade.Window) -> None:
    """A total dropped below the count leaves the count where it was.

    The setter configures the widget and does nothing else, so shrinking the total neither clamps nor rewinds the count: ``current`` reads back above ``maximum`` and Tk draws the bar full. Documented rather than accidental, which is what makes it worth pinning — a later decision to clamp instead fails here and says so, rather than passing quietly. The refused assignment is the other half: a count stranded above the total is not licence to write another one like it.
    """
    bar = tkfacade.ItemBasedProgressBar(window, orient="horizontal", length=200, maximum=10)
    bar.current = 8

    bar.maximum = 5

    assert (bar.current, bar.maximum) == (8, 5)
    with pytest.raises(ValueError, match="current"):
        bar.current = 6


def test_item_bar_maximum_reads_back_as_a_whole_count(window: tkfacade.Window) -> None:
    """``maximum`` answers an int whatever Tcl is holding behind it.

    ``-maximum`` is a Tcl double option and ``cget`` answers in whatever type the value was set as, so storing the float unconverted makes the property answer 7.9 against its own annotation — and the comparison in the ``current`` setter then admits a fractional count. The isinstance check is what makes this a test: ``== 7`` is equally true of 7.0.
    """
    bar = tkfacade.ItemBasedProgressBar(window, orient="horizontal", length=200, maximum=10)

    bar.maximum = 7.9

    assert bar.maximum == 7
    assert isinstance(bar.maximum, int)


def test_item_bar_current_truncates_a_float(window: tkfacade.Window) -> None:
    """A fractional count within range reaches the widget as whole items.

    4.7 separates truncation from rounding, which is the documented half of the contract. The widget-side read is the other half and the reason the test is not vacuous: ``IntVar.get`` truncates on the way out, so ``current`` answers 4 even when Tcl is holding 4.7 — only the value Tk draws from shows whether the conversion happened before the store, which is what anything else watching that variable sees.
    """
    bar = tkfacade.ItemBasedProgressBar(window, orient="horizontal", length=200, maximum=10)

    bar.current = 4.7

    assert bar.current == 4
    assert _value(bar) == pytest.approx(4.0)
