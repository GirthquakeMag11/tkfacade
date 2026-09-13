"""Menu accelerators: a Chord worn by a row, one source of truth.

The rulings pinned (2026-08-27): the drawn accelerator text is derived
from the chord's own set, never written by a caller, so display and
binding cannot drift; the chord's edge drives the row's *invocation* —
Tk's disabled guard, the command, and the ACTIVATED emission all
riding — never the command directly; assigning a different chord or
deleting the row detaches only the row's own subscription, the chord
being the caller's; and the row is windowed where the chord is global,
invoking only while its own window holds the input focus.
"""

import pytest

import tkfacade
from conftest import Pump
from test_input_observer import _armed, _flushed, _press, _release
from tkfacade.menu import CommandRow
from tkfacade.window import Root

pytestmark = pytest.mark.gui


def _drawn(row: CommandRow) -> str:
    """The accelerator text Tk holds for the row, read back."""
    return str(row._owner._tk_menu.entrycget(row.index, "accelerator"))


def test_the_drawn_text_is_derived_and_clears(
    window: tkfacade.Window, pump: Pump, root: Root
) -> None:
    """Assigning a chord draws its caption; None takes it away.

    The caller never writes the text: it is the chord's caption, so what the row advertises is what is bound, by construction — the inversion of Tk's cosmetic ``-accelerator`` (`hazards/tkinter.md`, *Menus*).
    """
    button = tkfacade.Menubutton(window, "File")
    button.grid(row=0, column=0)
    row = button.insert_command("Open")
    pump(window)
    combo = root.inputs.chord("Control", "o")

    row.chord = combo
    assert row.chord is combo
    assert _drawn(row) == "Ctrl+O"

    row.chord = None
    assert row.chord is None
    assert _drawn(row) == ""
    combo.cancel()


def test_the_edge_invokes_the_row_and_a_disabled_row_stays_silent(
    window: tkfacade.Window, pump: Pump, root: Root
) -> None:
    """The chord drives the full invocation: command, emission, Tk's guard.

    The ruling: the chord subscribes the row's invocation, never the command — so the accelerator is indistinguishable from a click, the subscribers hear it with the row in the payload, and a disabled row holds Tk's own silence rather than a second guard written here.
    """
    ran: list[str] = []
    heard: list[object] = []
    button = tkfacade.Menubutton(window, "File")
    button.grid(row=0, column=0)
    row = button.insert_command("Save", command=lambda: ran.append("command"))
    button.bind(tkfacade.ACTIVATED, lambda event: heard.append(event.payload["row"]))
    pump(window)
    combo = root.inputs.chord("Control", "s")
    row.chord = combo
    _armed(window, pump)

    _press(window, "Control_L", 1000)
    _press(window, "s", 1050)
    assert ran == ["command"]
    assert heard == [row]

    _release(window, "s", 1100)
    _flushed(window, pump)
    row.enabled = False
    _press(window, "s", 1200)
    assert ran == ["command"]
    assert heard == [row]

    combo.cancel()
    for keysym, stamp in (("s", 1300), ("Control_L", 1350)):
        _release(window, keysym, stamp)
    _flushed(window, pump)


def test_replacing_the_chord_detaches_the_old_and_keeps_it_alive(
    window: tkfacade.Window, pump: Pump, root: Root
) -> None:
    """A swapped-out chord stops driving the row and loses nothing else.

    Detachment is the row's alone: the old chord still fires for its other subscriber and still tracks ``held`` — the caller's chord is never cancelled by a row letting go of it.
    """
    ran: list[str] = []
    button = tkfacade.Menubutton(window, "File")
    button.grid(row=0, column=0)
    row = button.insert_command("Run", command=lambda: ran.append("ran"))
    pump(window)
    old = root.inputs.chord("Control", "r")
    watcher: list[bool] = []
    old.subscribe(lambda: watcher.append(True))
    fresh = root.inputs.chord("Control", "e")
    row.chord = old
    row.chord = fresh
    assert _drawn(row) == "Ctrl+E"
    _armed(window, pump)

    _press(window, "Control_L", 2000)
    _press(window, "r", 2050)
    assert ran == []
    assert watcher == [True]
    assert old.held

    _release(window, "r", 2100)
    _flushed(window, pump)
    _press(window, "e", 2150)
    assert ran == ["ran"]

    old.cancel()
    fresh.cancel()
    for keysym, stamp in (("e", 2200), ("Control_L", 2250)):
        _release(window, keysym, stamp)
    _flushed(window, pump)


def test_deleting_the_row_detaches_without_touching_the_chord(
    window: tkfacade.Window, pump: Pump, root: Root
) -> None:
    """A deleted row lets go; the chord stays the caller's, live."""
    ran: list[str] = []
    button = tkfacade.Menubutton(window, "File")
    button.grid(row=0, column=0)
    row = button.insert_command("Gone", command=lambda: ran.append("ran"))
    pump(window)
    combo = root.inputs.chord("Control", "g")
    others: list[bool] = []
    combo.subscribe(lambda: others.append(True))
    row.chord = combo

    row.delete()
    released: tkfacade.Chord | None = row.chord
    assert released is None
    _armed(window, pump)
    _press(window, "Control_L", 3000)
    _press(window, "g", 3050)
    assert ran == []
    assert others == [True]

    combo.cancel()
    for keysym, stamp in (("g", 3100), ("Control_L", 3150)):
        _release(window, keysym, stamp)
    _flushed(window, pump)


def test_the_row_is_windowed_where_the_chord_is_global(
    window: tkfacade.Window, pump: Pump, root: Root
) -> None:
    """With another window focused the chord fires and the row holds back.

    The ruled split: the chord is root-global and genuinely fired — its edge stood — while the invocation is the row's, gated on the row's own window holding the focus, so one combination can mean different rows in different windows.
    """
    ran: list[str] = []
    button = tkfacade.Menubutton(window, "File")
    button.grid(row=0, column=0)
    row = button.insert_command("Mine", command=lambda: ran.append("ran"))
    pump(window)
    combo = root.inputs.chord("Control", "m")
    row.chord = combo
    other = tkfacade.Window(title="other", root=root)
    try:
        other._tk.update()
        other._tk.focus_force()
        pump(window)
        other._tk.event_generate("<KeyPress-Control_L>", time=4000)
        other._tk.event_generate("<KeyPress-m>", time=4050)
        assert ran == []
        assert combo.held

        other._tk.event_generate("<KeyRelease-m>", time=4100)
        other._tk.event_generate("<KeyRelease-Control_L>", time=4150)
        _flushed(window, pump)
        _armed(window, pump)
        _press(window, "Control_L", 4200)
        _press(window, "m", 4250)
        assert ran == ["ran"]
    finally:
        combo.cancel()
        other.destroy()
    for keysym, stamp in (("m", 4300), ("Control_L", 4350)):
        _release(window, keysym, stamp)
    _flushed(window, pump)


def test_a_menubar_rows_chord_finds_its_window(
    window: tkfacade.Window, pump: Pump, root: Root
) -> None:
    """The guard resolves a menubar's window: a menu is its own toplevel.

    The risky resolution, verified: Tk answers a *menu* as its own top-of-hierarchy window, so the guard steps off the ``tk.Menu`` through its master before asking for a toplevel — and the bar's row invokes for the window it actually belongs to.
    """
    barred = tkfacade.Window(title="barred", menubar=True, root=root)
    bar = barred.menubar
    assert bar is not None
    ran: list[str] = []
    row = bar.insert_submenu("File").insert_command("Help", command=lambda: ran.append("ran"))
    combo = root.inputs.chord("Control", "h")
    row.chord = combo
    try:
        barred._tk.update()
        barred._tk.focus_force()
        pump(window)
        barred._tk.event_generate("<KeyPress-Control_L>", time=5000)
        barred._tk.event_generate("<KeyPress-h>", time=5050)
        assert ran == ["ran"]

        barred._tk.event_generate("<KeyRelease-h>", time=5100)
        barred._tk.event_generate("<KeyRelease-Control_L>", time=5150)
        _flushed(window, pump)
    finally:
        combo.cancel()
        barred.destroy()
