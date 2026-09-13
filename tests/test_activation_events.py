"""Commands as virtual events: every activation is subscribable.

The item's claims, each pinned: wherever the command machinery runs,
the wrapper also emits :data:`~tkfacade.ACTIVATED` — command first,
emission after, and the emission happens with no command set at all,
which is the gap the item exists to fill. A coroutine subscriber hears
a button the way it hears any event, which was the original impetus;
the wrappers holding several activatable parts say which part in the
payload — a menu's row, a tree's column, a bank's button.
"""

import asyncio
import time
import tkinter as tk
from typing import cast

import pytest

import tkfacade
from conftest import Pump
from tkfacade.events import Event

pytestmark = pytest.mark.gui


def _is_x11() -> bool:
    """True when the test display is X11."""
    try:
        probe = tk.Tk()
    except tk.TclError:
        return False
    result = str(probe.tk.call("tk", "windowingsystem")) == "x11"
    probe.destroy()
    return result


def test_a_button_emits_with_command_first_and_without_one(
    window: tkfacade.Window, pump: Pump
) -> None:
    """Activation runs the command, then the subscribers — or just them.

    The two halves of the gap-fill in one frame: a button with no command at all still tells its subscribers — the single command slot stops being the only door — and where both exist, the widget's own command runs before the broadcast, the same precedence the wrapper's own bindings enjoy everywhere else.
    """
    order: list[str] = []
    plain = tkfacade.Button(window, "bare")
    plain.bind(tkfacade.ACTIVATED, lambda event: order.append("subscribed"))
    plain.grid(row=0, column=0)
    pump(window)

    plain.invoke()
    assert order == ["subscribed"]

    commanded = tkfacade.Button(window, "told", command=lambda: order.append("command"))
    commanded.bind(tkfacade.ACTIVATED, lambda event: order.append("heard"))
    commanded.grid(row=1, column=0)
    pump(window)
    commanded.invoke()

    assert order == ["subscribed", "command", "heard"]


def test_a_coroutine_hears_a_button(window: tkfacade.Window, pump: Pump) -> None:
    """The original impetus, end to end: button pressed, coroutine run.

    What tkinter's command could never say simply: the activation reaches a coroutine, scheduled on the root's core by the observer role's standing machinery — no special-case async command plumbing, just the event route being complete.
    """
    landed: list[str] = []

    async def reaction(event: Event) -> None:
        await asyncio.sleep(0)  # genuinely on the core's loop, not just declared so
        landed.append("ran")

    button = tkfacade.Button(window, "go")
    button.bind(tkfacade.ACTIVATED, reaction)
    button.grid(row=0, column=0)
    pump(window)

    button.invoke()
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not landed:
        pump(window)
        time.sleep(0.01)

    assert landed == ["ran"]


def test_a_menu_rows_activation_lands_on_the_menubutton_with_the_row(
    window: tkfacade.Window, pump: Pump
) -> None:
    """Rows emit on their facade unit's wrapper, the row in the payload.

    Menus close Tk's event route, so the wrapper is where subscribers can stand — and a row nested a submenu deep still reaches it, the emitter walk climbing owners to the widget. The payload answers which row, since one menubutton holds many; the rows are driven through their public invoke, Tk's own entry path — the same funnel a real click runs, disabled-guard included.
    """
    heard: list[object] = []
    button = tkfacade.Menubutton(window, "File")
    button.grid(row=0, column=0)
    row = button.insert_command("Open", command=lambda: None)
    deep = button.insert_submenu("More")
    nested = deep.insert_command("Deep")
    button.bind(tkfacade.ACTIVATED, lambda event: heard.append(event.payload["row"]))
    pump(window)

    row.invoke()
    nested.invoke()

    assert heard == [row, nested]


@pytest.mark.skipif(not _is_x11(), reason="X11-only: win32 native menus are separate toplevels")
def test_a_menubar_rows_activation_lands_on_the_bar(window: tkfacade.Window, pump: Pump) -> None:
    """The risky case: a generated virtual on a tk.Menu delivers.

    The menubar's underlying widget is a tk.Menu — the one place a generated virtual event might plausibly vanish, given the bar-clone path troubles real pointer events. It delivers: generation targets the real menu widget, whose own binding fires; no fallback needed.
    """
    barred = tkfacade.Window(title="barred", menubar=True, root=None)
    bar = barred.menubar
    assert bar is not None
    heard: list[object] = []
    row = bar.insert_submenu("File").insert_command("Help", command=lambda: None)
    bar.bind(tkfacade.ACTIVATED, lambda event: heard.append(event.payload["row"]))
    pump(window)

    row.invoke()
    barred.destroy()

    assert heard == [row]


def test_a_heading_activation_carries_its_column_and_needs_no_command(
    window: tkfacade.Window, pump: Pump
) -> None:
    """A heading click emits on the tree with the column, command or not.

    Headings never had a subscribable activation and often carry no command at all — a sortable table's click is machinery, not a caller's callback. The dispatcher is installed for every column from birth and emits after whatever it holds; driven directly here because a real click needs pixel geometry the claim does not.
    """
    heard: list[str] = []
    tree = tkfacade.Table(window, columns=(tkfacade.TreeColumnSpec(name="n"),))
    tree.bind(
        tkfacade.ACTIVATED,
        # cast per the emission contract: a heading activation's payload
        # carries the TreeColumn under "column"
        lambda event: heard.append(cast(tkfacade.TreeColumn, event.payload["column"]).name),
    )
    tree.grid(row=0, column=0)
    pump(window)

    tree._heading_dispatchers["n"]()

    assert heard == ["n"]


def test_a_bank_buttons_activation_lands_on_the_bank_with_the_button(
    window: tkfacade.Window, pump: Pump
) -> None:
    """A choice bank emits on itself, naming the member pressed.

    The bank is the widget and the buttons are its parts, so the event arrives where subscribers hold a wrapper and the payload says which member — the same shape as the menu's rows and the tree's columns.
    """
    heard: list[object] = []
    bank = tkfacade.ChoiceButtons(window, ("a", "b"))
    bank.bind(tkfacade.ACTIVATED, lambda event: heard.append(event.payload["button"]))
    bank.grid(row=0, column=0)
    pump(window)

    bank.buttons[1].invoke()

    assert heard == [bank.buttons[1]]
