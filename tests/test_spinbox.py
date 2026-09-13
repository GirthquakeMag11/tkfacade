""":class:`~tkfacade.FloatSpinbox` and :class:`~tkfacade.IntSpinbox`.

The numeric half of ttk's spinbox, split by what it counts as the
scales are. The contract is tested over both, since almost all of it
lives on the shared base: the range, the stepping and its two
behaviours at the ends, and the command that fires for a user only.
"""

import pytest

import tkfacade

pytestmark = pytest.mark.gui


def test_construction_options_round_trip(window: tkfacade.Window) -> None:
    """The range, the step, and the two state flags land and read back live.

    The state surface read live from Tk, and the last pair is the one that nearly went wrong: editable and enabled are independent, but ttk's state *option* has three words for their four combinations, so switching the widget off through it discards whether typing was allowed. Both are read and written as state *flags*, which hold together — the same distinction `Entry.disabled` already records between `instate` and `cget('state')`. Asserting both after setting both is what catches a regression to the option.
    """
    box = tkfacade.IntSpinbox(window, minimum=0, maximum=10, value=4, step=2)

    assert box.minimum == 0
    assert box.maximum == 10
    assert box.step == 2
    assert box.value == 4
    assert box.wraps is False
    assert box.editable is True
    assert box.enabled is True

    box.editable = False
    box.enabled = False

    assert box.editable is False
    assert box.enabled is False


def test_stepping_moves_by_the_step_and_stops_at_the_ends(window: tkfacade.Window) -> None:
    """Each step moves one increment, and the ends hold.

    The whole movement contract in one pass: a step is exactly one increment, stepping past the top holds there rather than overshooting or wrapping, and stepping below the bottom holds too. The extra presses at the top are what make it a claim about stopping rather than about one lucky arithmetic result.
    """
    box = tkfacade.IntSpinbox(window, minimum=0, maximum=6, value=2, step=2)
    box.grid(row=0, column=0)
    window._tk.update()

    box.step_up()
    window._tk.update()
    stepped = box.value

    box.step_up()
    box.step_up()
    box.step_up()
    window._tk.update()
    at_top = box.value

    box.value = 0
    box.step_down()
    window._tk.update()

    assert stepped == 4
    assert at_top == 6
    assert box.value == 0


def test_wrapping_cycles_past_each_end(window: tkfacade.Window) -> None:
    """With wraps set, a step past an end lands on the other.

    The other half of the same option, asserted in both directions so that a wrap implemented one way round would fail. Off by default, which is what a bounded quantity usually wants and what the previous test pins.
    """
    box = tkfacade.IntSpinbox(window, minimum=0, maximum=3, value=3, wraps=True)
    box.grid(row=0, column=0)
    window._tk.update()

    box.step_up()
    window._tk.update()
    over_the_top = box.value

    box.step_down()
    window._tk.update()

    assert over_the_top == 0
    assert box.value == 3


def test_a_value_outside_the_range_is_refused(window: tkfacade.Window) -> None:
    """Both doors a plain number comes in by are closed.

    The refusal of what Tk would take and act on wrongly. Witnessed: a spinbox limited to 10 accepts a written 99 and displays it, snapping away only on the next step. So the range is the facade's to keep, at both doors — and the last two lines pin the deliberate escape, the shared observable reaching the widget unchecked as it does on the choice box, the scales and the progress bars.
    """
    with pytest.raises(ValueError, match="must lie from"):
        tkfacade.IntSpinbox(window, minimum=0, maximum=10, value=99)

    box = tkfacade.IntSpinbox(window, minimum=0, maximum=10, value=4)
    with pytest.raises(ValueError, match="must lie from"):
        box.value = -1

    assert box.value == 4

    box.value_observable.value = 99
    assert box.value == 99


def test_an_inverted_range_is_refused(window: tkfacade.Window) -> None:
    """A maximum below the minimum is rejected rather than built.

    Where the scales differ, and why these bounds are named for their order. A ttk.Scale runs happily from its high value to its low one; a ttk.Spinbox does not — witnessed, one built from 10 down to 0 answers every step in either direction with 10, whatever it held first. So the inversion the scales allow is refused here, and the names say which widget is which. A step of zero is refused beside it: arrows that cannot move are the same kind of unbuildable widget.
    """
    with pytest.raises(ValueError, match="above minimum"):
        tkfacade.IntSpinbox(window, minimum=10, maximum=0)
    with pytest.raises(ValueError, match="step must be positive"):
        tkfacade.IntSpinbox(window, minimum=0, maximum=10, step=0)


def test_the_command_runs_for_a_step_and_not_for_a_write(window: tkfacade.Window) -> None:
    """Tk fires the command for the arrows only.

    The user-only meaning command carries across the family, which this widget gets from Tk directly rather than by arrangement: ttk fires a spinbox's command for a step and not for Spinbox.set or a variable write. Worth pinning precisely because the neighbouring scale gets the same guarantee only because the library declines to use the one write path that would break it — here there is no such path to avoid.
    """
    ran: list[str] = []
    box = tkfacade.FloatSpinbox(
        window, minimum=0.0, maximum=10.0, value=1.0, command=lambda: ran.append("stepped")
    )
    box.grid(row=0, column=0)
    window._tk.update()

    box.value = 5.0
    box.value_observable.value = 6.0
    window._tk.update()
    after_writes = list(ran)

    box.step_up()
    window._tk.update()

    assert after_writes == []
    assert ran == ["stepped"]


def test_an_int_spinbox_holds_whole_numbers_through_part_typed_text(
    window: tkfacade.Window,
) -> None:
    """Text the transport cannot read leaves the last good value standing.

    What an editable spinbox does while a user is halfway through typing, which is the one place a numeric widget bound to live text could hand nonsense to a watcher. It does not: the transport is an IntVar, text it cannot read is dropped by the observable, and the tape shows the partial numbers a live binding necessarily produces without the unparseable one among them. The value that survives is an int, not a string that happens to look like one.
    """
    box = tkfacade.IntSpinbox(window, minimum=0, maximum=200, value=5)
    box.grid(row=0, column=0)
    window._tk.update()
    seen: list[int] = []
    box.value_observable.watch(seen.append)
    transport = box.value_observable.transport_for(window._tk)

    for keystroke in ("1", "12", "12x", "123"):
        transport.set(keystroke)
        window._tk.update()

    box.value_observable.release_transport()

    assert box.value == 123
    assert isinstance(box.value, int)
    assert seen == [5, 1, 12, 123]


def test_destroying_the_spinbox_gives_back_its_transport(window: tkfacade.Window) -> None:
    """A destroyed spinbox stops riding its shared observable.

    The teardown half: the transport ride goes back so a shared observable never pins a dead interpreter through a widget that took one and never gave it back (`hazards/tkinter.md`, *Variables*).
    """
    shared = tkfacade.ObservableFloat(2.0)
    box = tkfacade.FloatSpinbox(window, minimum=0.0, maximum=10.0, value=shared)
    attached = shared._var is not None

    box.destroy()
    window._tk.update()

    assert attached
    assert shared._var is None
