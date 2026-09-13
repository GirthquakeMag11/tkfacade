"""The message and confirm dialogs: said, acknowledged, or answered.

The claims pinned: a message completes on OK and on Return, answering
nothing; a confirm answers True on its affirmative and False on the
decline button, Escape, and the close box alike — the family's one
deliberate bool, a declined confirmation being a "no"; the captions
are the caller's; and the save gate still rides the same machinery
(its regression lives in the file dialog suite).
"""

import pytest

import tkfacade
from conftest import Pump
from tkfacade import dialog
from tkfacade.dialog._message import _MessageDialog

pytestmark = pytest.mark.gui


def test_a_message_acknowledges_on_ok_and_on_return(window: tkfacade.Window, pump: Pump) -> None:
    """One button, two ways to press it, nothing answered."""
    box = _MessageDialog(window, "all done", title="Message")
    box.show()
    pump(window)
    box._affirm.invoke()
    assert box.result() is True

    keyed = _MessageDialog(window, "all done again", title="Message")
    keyed.show()
    pump(window)
    keyed._window._tk.event_generate("<Return>")
    pump(window)
    assert keyed.done


def test_confirm_answers_true_or_false_never_none(window: tkfacade.Window, pump: Pump) -> None:
    """The affirmative is True; decline, Escape — every no reads False."""

    def push(caption: str) -> None:
        import tkinter as tk
        from tkinter import ttk

        path = window._tk.tk.eval("grab current")
        holder = window._tk.nametowidget(path)
        stack: list[tk.Misc] = [holder]
        while stack:
            candidate = stack.pop()
            if isinstance(candidate, ttk.Button) and str(candidate.cget("text")) == caption:
                candidate.invoke()
                return
            stack.extend(candidate.winfo_children())
        raise AssertionError(f"no {caption!r} button")

    window._tk.after(150, lambda: push("Proceed"))
    assert dialog.confirm(window, "sure?", affirm="Proceed", decline="Back") is True

    window._tk.after(150, lambda: push("Back"))
    assert dialog.confirm(window, "sure?", affirm="Proceed", decline="Back") is False

    def escape() -> None:
        path = window._tk.tk.eval("grab current")
        assert path
        window._tk.tk.call("event", "generate", path, "<Escape>")

    window._tk.after(150, escape)
    answered = dialog.confirm(window, "sure?")
    assert answered is False


def test_the_message_function_blocks_and_answers_nothing(
    window: tkfacade.Window, pump: Pump
) -> None:
    """``dialog.message`` parks its caller and returns None either way."""

    def escape() -> None:
        path = window._tk.tk.eval("grab current")
        assert path
        window._tk.tk.call("event", "generate", path, "<Escape>")

    window._tk.after(150, escape)
    marks: list[str] = []
    marks.append("before")
    dialog.message(window, "for your information")  # returns None by signature
    marks.append("resumed")
    assert marks == ["before", "resumed"]
