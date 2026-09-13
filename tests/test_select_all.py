"""Ctrl+A selects all, everywhere text is typed: the dialect repair.

Tk's x11 keymap spells ``<<LineStart>>`` as Home *and* Control-a — the
Emacs dialect — leaving ``<<SelectAll>>`` on the archaic Control-slash,
so Ctrl+A in an entry jumped the cursor to the start instead of
selecting (witnessed 2026-08-28, in the file dialog's name entry). The
root remaps the virtual events at interpreter level, so the class
bindings repair every text surface at once: these tests pin the entry
and the multi-line box, and that Home still means line-start.
"""

import pytest

import tkfacade
from conftest import Pump

pytestmark = pytest.mark.gui


def _armed(window: tkfacade.Window, pump: Pump) -> None:
    """Give the window keyboard focus: Tk drops generated keys without it."""
    window._tk.focus_force()
    pump(window)


def test_control_a_selects_the_whole_entry(window: tkfacade.Window, pump: Pump) -> None:
    """The full content selects, and the cursor does not jump home."""
    entry = tkfacade.Entry(window, "hello world")
    entry.grid(row=0, column=0)
    _armed(window, pump)
    entry._tk.focus_force()
    entry._tk.icursor("end")
    pump(window)

    entry._tk.event_generate("<Control-a>")
    pump(window)

    assert entry._tk.index("sel.first") == 0
    assert entry._tk.index("sel.last") == len("hello world")
    assert entry._tk.index("insert") != 0


def test_control_a_selects_the_whole_text_box(window: tkfacade.Window, pump: Pump) -> None:
    """The multi-line box speaks the same dialect through its own binding."""
    box = tkfacade.TextBox(window)
    box.text = "line one\nline two"
    box.grid(row=0, column=0)
    _armed(window, pump)
    box._text.focus_force()
    pump(window)

    box._text.event_generate("<Control-a>")
    pump(window)

    # the trailing newline is the text widget's own permanent last
    # character, honestly inside a whole-content selection
    assert str(box._text.get("sel.first", "sel.last")) == "line one\nline two\n"


def test_home_still_means_line_start(window: tkfacade.Window, pump: Pump) -> None:
    """The remap took Ctrl+A alone; ``<<LineStart>>`` keeps its Home spelling."""
    entry = tkfacade.Entry(window, "hello")
    entry.grid(row=0, column=0)
    _armed(window, pump)
    entry._tk.focus_force()
    entry._tk.icursor("end")
    pump(window)

    entry._tk.event_generate("<Home>")
    pump(window)

    assert entry._tk.index("insert") == 0
