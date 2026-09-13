""":class:`~tkfacade.FloatScale` and :class:`~tkfacade.IntScale`.

The continuous-and-stepped pair, split by what they count the way
the progress bars are. The contract is tested over both, since almost
all of it lives on the shared base: the value observable, the readout
that renders it, the command that fires only for a user, and the range.
"""

import pytest

import tkfacade

pytestmark = pytest.mark.gui


def test_construction_options_round_trip(window: tkfacade.Window) -> None:
    """The range, value, and enabled state land and read back live.

    The state surface read live from Tk — the bounds through cget, the enabled state through the state flags — after construction and again after assignment. The range is settable because a scale whose bounds depend on loaded data is ordinary: a seek bar learns its end when the media does.
    """
    scale = tkfacade.FloatScale(window, start=0.0, end=50.0, value=10.0, enabled=False)

    assert scale.start == pytest.approx(0.0)
    assert scale.end == pytest.approx(50.0)
    assert scale.value == pytest.approx(10.0)
    assert scale.enabled is False

    scale.end = 200.0
    scale.enabled = True

    assert scale.end == pytest.approx(200.0)
    assert scale.enabled is True


def test_the_value_and_the_observable_are_one_value(window: tkfacade.Window) -> None:
    """Driving the observable moves the slider; the slider writes the observable.

    Both directions on one shared value, with the widget read through Tk rather than through the wrapper's view of itself: a write reaches the slider, and a write through the shared observable reaches it too. The watcher's tape proves each change was heard once, the immediate birth call included.
    """
    shared = tkfacade.ObservableFloat(0.0)
    scale = tkfacade.FloatScale(window, start=0.0, end=100.0, value=shared)
    seen: list[float] = []
    shared.watch(seen.append)

    scale.value = 40.0
    window._tk.update()

    assert scale._scale.get() == pytest.approx(40.0)
    assert shared.value == pytest.approx(40.0)

    shared.value = 75.0
    window._tk.update()

    assert scale._scale.get() == pytest.approx(75.0)
    assert seen == [0.0, 40.0, 75.0]


def test_an_int_scale_holds_whole_steps(window: tkfacade.Window) -> None:
    """The stepped scale's value is an integer wherever the handle rests.

    The whole point of the split: the value quantises even where the widget does not. Setting the underlying slider to 7.6 — which is what a drag between two steps produces — leaves the value reading 7, an int, because the transport behind it is an IntVar. The handle itself stays where it was put; that limitation is documented on the class and is a known gap.
    """
    scale = tkfacade.IntScale(window, start=0, end=10, value=3)
    scale.grid(row=0, column=0)
    window._tk.update()

    assert scale.value == 3
    assert isinstance(scale.value, int)

    scale._scale.set(7.6)
    window._tk.update()

    assert scale.value == 7
    assert isinstance(scale.value, int)


def test_a_value_outside_the_range_is_refused(window: tkfacade.Window) -> None:
    """The property and the constructor both refuse a value past either end.

    The refusal of what Tk would take and act on wrongly. Witnessed: a variable-driven write past the end is neither clamped nor refused by Tk — the widget simply reports 99 on a 0-to-10 scale and strands the slider at the end of its track. So the wrapper refuses it at both doors a plain number comes in by, and the unchanged value proves the raise landed before the write did.  The last two lines pin the deliberate escape rather than a defect: driving the shared observable directly bypasses the check, exactly as it does on the progress bars, and the class docstring says so. Pinning it is what stops the seam being closed by accident later.
    """
    scale = tkfacade.FloatScale(window, start=0.0, end=10.0, value=4.0)
    scale.grid(row=0, column=0)
    window._tk.update()

    with pytest.raises(ValueError, match=r"from 0\.0 to 10\.0"):
        scale.value = 99.0
    with pytest.raises(ValueError, match=r"from 0\.0 to 10\.0"):
        tkfacade.FloatScale(window, start=0.0, end=10.0, value=-1.0)

    assert scale.value == pytest.approx(4.0)

    scale.value_observable.value = 99.0
    window._tk.update()

    assert scale.value == pytest.approx(99.0)


def test_an_inverted_range_is_allowed(window: tkfacade.Window) -> None:
    """A scale may run from its high value to its low one.

    The reason the bounds are named start and end rather than minimum and maximum: Tk genuinely supports a scale running the other way, and a vertical volume slider wanting its loudest at the top is the ordinary case for it. The range check takes the two ends either way round, which is what the raise here proves.
    """
    scale = tkfacade.IntScale(window, start=10, end=0, value=7)
    scale.grid(row=0, column=0)
    window._tk.update()

    assert scale.start == pytest.approx(10.0)
    assert scale.end == pytest.approx(0.0)
    assert scale.value == 7

    with pytest.raises(ValueError, match="from 0 to 10"):
        scale.value = 11


def test_the_command_runs_for_a_user_and_not_for_a_write(window: tkfacade.Window) -> None:
    """A write through the observable is silent; the slider's own route is not.

    The distinction that justifies a command beside a watchable observable, and the one this widget nearly failed: Tk fires a scale's command for `Scale.set` as well as for a drag, so a wrapper driving the widget that way would call it for its own writes. Driving through the transport variable instead — which is what every value-bearing wrapper here already does — leaves the command meaning exactly what it means on Button and Checkbutton. Both halves are asserted: silence through two write routes, then one call from the user's.
    """
    ran: list[str] = []
    scale = tkfacade.FloatScale(
        window, start=0.0, end=100.0, length=200, command=lambda: ran.append("user")
    )
    scale.grid(row=0, column=0)
    window._tk.update()

    scale.value = 30.0
    scale.value_observable.value = 60.0
    window._tk.update()
    after_writes = list(ran)

    scale._scale.event_generate("<Button-1>", x=10, y=10)
    scale._scale.event_generate("<B1-Motion>", x=120, y=10)
    scale._scale.event_generate("<ButtonRelease-1>", x=120, y=10)
    window._tk.update()

    assert after_writes == []
    assert ran == ["user"]


def test_the_readout_shows_the_value_and_follows_it(window: tkfacade.Window) -> None:
    """show_value puts a rendered readout beside the slider, kept current.

    The capability absorbed from ttk's own LabeledScale, which this library rules out in favour of this option. The readout is asserted at birth as well as after a change, because a label wired only to later updates would start blank and look right forever after.
    """
    scale = tkfacade.IntScale(window, start=0, end=10, value=4, show_value=True)
    scale.grid(row=0, column=0)
    window._tk.update()
    at_first = str(scale._readout.cget("text"))

    scale.value = 9
    window._tk.update()

    assert at_first == "4"
    assert str(scale._readout.cget("text")) == "9"
    assert scale.show_value is True


def test_the_readout_can_be_hidden_and_reformatted(window: tkfacade.Window) -> None:
    """show_value and value_format are live options, not construction-only.

    On the two options a caller is most likely to change after the fact: a scale built without a readout can grow one, and the rendering is the caller's to set — a fraction shown as a percentage is exactly the case a fixed format would have made unreachable.
    """
    scale = tkfacade.FloatScale(window, start=0.0, end=1.0, value=0.5)
    scale.grid(row=0, column=0)
    window._tk.update()
    hidden_at_first = scale.show_value

    scale.show_value = True
    scale.value_format = "{:.0%}"
    window._tk.update()

    assert hidden_at_first is False
    assert scale.show_value is True
    assert str(scale._readout.cget("text")) == "50%"


def test_the_readout_moves_around_the_slider(window: tkfacade.Window) -> None:
    """arrangement re-places the pair without disturbing the value.

    The same vocabulary TitleEntry uses for the same shape, and the same promise: re-placing the halves is a layout change and nothing else, so the value and its rendering survive the move. Both a side-by-side and a stacked arrangement are exercised, since the two take different branches through the gridding.
    """
    scale = tkfacade.FloatScale(
        window, start=0.0, end=10.0, value=6.0, show_value=True, arrangement="left-right"
    )
    scale.grid(row=0, column=0)
    window._tk.update()
    started = scale.arrangement

    scale.arrangement = "bottom-top"
    window._tk.update()

    assert started == "left-right"
    assert scale.arrangement == "bottom-top"
    assert scale.value == pytest.approx(6.0)
    assert str(scale._readout.cget("text")) == "6.00"


def test_destroying_the_scale_gives_back_what_it_holds(window: tkfacade.Window) -> None:
    """A destroyed scale releases its transport and stops watching.

    The teardown half, and the half a readout adds to it: the transport ride goes back so a shared observable never pins a dead interpreter (`hazards/tkinter.md`, *Variables*), and the readout's watch is cancelled so a later write does not try to relabel a destroyed widget. The write after the destroy is what proves the second half — it would raise from inside the watcher if the watch had survived. The attachment is captured rather than asserted in place: asserting it narrows the attribute, and mypy then calls the later reading unreachable.
    """
    shared = tkfacade.ObservableInt(2)
    scale = tkfacade.IntScale(window, start=0, end=10, value=shared, show_value=True)
    scale.grid(row=0, column=0)
    window._tk.update()
    attached = shared._var is not None

    scale.destroy()
    window._tk.update()
    shared.value = 8

    assert attached
    assert shared._var is None
    assert shared.value == 8


def test_arrangement_answers_on_a_default_scale_with_no_readout(window: tkfacade.Window) -> None:
    """With ``show_value=False`` — the default — arrangement answers without raising."""
    scale = tkfacade.IntScale(window, start=0, end=10)

    assert scale.arrangement == "top-bottom"


def test_setting_arrangement_does_not_unhide_the_readout(window: tkfacade.Window) -> None:
    """Assigning arrangement does not flip show_value from False to True."""
    scale = tkfacade.IntScale(window, start=0, end=10)

    scale.arrangement = "left-right"

    assert scale.show_value is False
    assert scale.arrangement == "left-right"


def test_a_hidden_readout_moves_to_the_remembered_arrangement_when_shown(
    window: tkfacade.Window,
) -> None:
    """Turning show_value on after arranging applies the stored arrangement.

    The getter used grid_info on an unmanaged widget, which answers an empty dict — a KeyError on a documented public property in the scale's default configuration. The setter called _arrange directly, which re-gridded the readout and silently unmasked a grid_remove'd slave, flipping show_value from False to True. The arrangement is now an stored member: the getter answers from it and the setter writes to it, and _arrange is called only when the readout is actually visible — by the setter then, and by show_value's setter on the stored value when turning the readout on.
    """
    scale = tkfacade.IntScale(window, start=0, end=10)
    scale.arrangement = "right-left"

    scale.show_value = True

    assert scale.arrangement == "right-left"
