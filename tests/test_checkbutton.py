""":class:`~tkfacade.Checkbutton`: one boolean in widget form.

The first observability proof on a widget: the tick is an
:class:`~tkfacade.ObservableBool`, shared or private, and every change
— clicked or assigned — passes through it. The command beside it is
the user's channel only, in both kinds, riding the button family's
shared dispatch. The async leg runs the real mainloop through
``run_mainloop``, per the thread wall.
"""

import asyncio
import threading

import pytest

import tkfacade
from conftest import RunMainloop

pytestmark = pytest.mark.gui


def test_construction_options_round_trip(window: tkfacade.Window) -> None:
    """text, checked, and enabled land at construction and read back live.

    The state surface read live from Tk: text through cget, enabled through the state flags, checked through the observable — each after construction and after assignment, with the ticked-and-disabled start proving the keywords are independent.
    """
    plain = tkfacade.Checkbutton(window, "Alerts")
    ticked = tkfacade.Checkbutton(window, "Sound", checked=True, enabled=False)

    assert plain.text == "Alerts"
    assert plain.checked is False
    assert plain.enabled is True
    assert ticked.checked is True
    assert ticked.enabled is False

    plain.text = "Alerts on"
    ticked.enabled = True

    assert plain.text == "Alerts on"
    assert ticked.enabled is True


def test_the_tick_and_the_observable_are_one_value(window: tkfacade.Window) -> None:
    """Activation writes the shared observable; writes move the drawn tick.

    Both directions of the observability story on one shared value: the user's toggle lands in the observable — invoke's variable write comes back through the transport trace, synchronously — and a bare observable write moves the drawn tick, pinned through ttk's own selected state flag beside the wrapper's view of itself. Each side is read through the channel the other wrote, and the watcher's tape proves every change was heard exactly once, the immediate birth call included. (The property is asserted once per polarity: mypy narrows a property expression and would call a re-read unreachable.)
    """
    shared = tkfacade.ObservableBool(False)
    box = tkfacade.Checkbutton(window, "Sync", checked=shared)
    seen: list[bool] = []
    shared.watch(seen.append)

    box.invoke()

    assert shared.value is True
    assert box._tk.instate(["selected"])

    shared.value = False

    assert box.checked is False
    assert not box._tk.instate(["selected"])
    assert seen == [False, True, False]


def test_the_command_runs_on_activation_and_not_on_writes(window: tkfacade.Window) -> None:
    """invoke runs the command; observable and property writes never do.

    The distinction that justifies the command's existence beside a watchable observable: ttk runs -command only for user activation, so a write through the property or the observable moves the tick — asserted, so the silence is not the equal-write drop — without it ever firing. A watcher hears every change; only the command knows the user made this one.
    """
    ran: list[str] = []
    box = tkfacade.Checkbutton(window, "Sync", command=lambda: ran.append("ran"))

    box.invoke()
    assert ran == ["ran"]
    assert box.checked is True

    box.checked = False
    box.checked_observable.value = True

    assert ran == ["ran"]
    assert box.checked is True


def test_invoke_toggles_before_the_command_runs(window: tkfacade.Window) -> None:
    """The command reads the new state, ttk having toggled first.

    The ordering the class docstring promises — toggle, then command — witnessed rather than assumed: a command reading its own widget sees the state the activation produced, not the one it left. This is what makes a command a sound place to react to the user's toggle without a watcher.
    """
    story: list[bool] = []
    box = tkfacade.Checkbutton(window, "Sync")
    box.command = lambda: story.append(box.checked)

    box.invoke()
    box.invoke()

    assert story == [True, False]


def test_invoke_honors_disabled(window: tkfacade.Window) -> None:
    """invoke runs nothing while disabled, wrapper and raw alike.

    The disabled leg witnessed the Button way: ttk itself honors the state — neither the command nor the toggle happens — so the wrapper carries no second guard. The raw call stays beside the facade's as the pin: a build where ttk stops honoring the state fails here first, and the no-guard decision gets revisited on evidence. The unchanged tick matters as much as the silent command — a disabled activation must not half-happen.
    """
    ran: list[str] = []
    box = tkfacade.Checkbutton(window, "Go", command=lambda: ran.append("ran"))

    box.invoke()
    assert ran == ["ran"]
    assert box.checked is True

    box.enabled = False
    box._tk.invoke()
    box.invoke()

    assert ran == ["ran"]
    assert box.checked is True


def test_a_coroutine_command_runs_on_the_core(
    window: tkfacade.Window, run_mainloop: RunMainloop
) -> None:
    """A coroutine function as command is scheduled off-thread per activation.

    The family's shared dispatch proven from this widget's own seam: the same command parameter takes a coroutine function with no second spelling, and activation schedules it on the root's core. The raise routing behind it is pinned once, on Button, because the dispatch is one function; this test is the wiring, not the plumbing.
    """
    main = threading.get_ident()
    ran_on: list[int] = []
    done = threading.Event()

    async def command() -> None:
        await asyncio.sleep(0)
        ran_on.append(threading.get_ident())
        done.set()

    box = tkfacade.Checkbutton(window, "Fetch", command=command)
    box.grid(row=0, column=0)
    window._tk.after(0, box.invoke)
    run_mainloop(window, done)

    assert len(ran_on) == 1
    assert ran_on[0] != main


def test_destroy_gives_back_the_transport_ride(window: tkfacade.Window) -> None:
    """A destroyed checkbutton stops riding its shared observable.

    The rider count in both directions: one death leaves the transport standing for the survivor, and the last death drops it, so a shared observable never pins a dead interpreter through a widget that took a ride and never gave it back (`hazards/tkinter.md`, *Variables*). The not-None assertions guard the vacuity — a transport that never existed would pass the final check for the wrong reason.
    """
    shared = tkfacade.ObservableBool(True)
    first = tkfacade.Checkbutton(window, "One", checked=shared)
    second = tkfacade.Checkbutton(window, "Two", checked=shared)
    assert shared._var is not None

    first.destroy()
    window._tk.update()
    assert shared._var is not None

    second.destroy()
    window._tk.update()
    assert shared._var is None
