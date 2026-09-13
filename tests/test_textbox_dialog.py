"""The textbox dialog: content taken as it stands, or declined.

The claims pinned: OK answers the box's content exactly — multi-line,
edited, or empty, the empty string staying distinct from ``None`` so
a caller can tell nothing-entered from declined; the initial text is
what the box starts holding; and the function surface blocks its
caller and answers None on Escape.
"""

import pytest

import tkfacade
from conftest import Pump
from tkfacade import dialog
from tkfacade.dialog._textbox import _TextboxDialog

pytestmark = pytest.mark.gui


def test_ok_answers_the_content_as_it_stands(window: tkfacade.Window, pump: Pump) -> None:
    """Multi-line content comes back exactly; the empty string is an answer."""
    box = _TextboxDialog(window, title=None, message="say it", initial_text="dear diary")
    box.show()
    pump(window)

    assert box._box.text == "dear diary"
    box._box.text = "line one\nline two"
    box._ok.invoke()

    assert box.result() == "line one\nline two"

    empty = _TextboxDialog(window, title=None, message=None, initial_text="")
    empty._ok.invoke()

    answered = empty.result()
    assert answered == ""
    assert answered is not None


def test_the_function_blocks_and_escape_answers_none(window: tkfacade.Window, pump: Pump) -> None:
    """``dialog.textbox`` parks its caller; Escape dismisses to None."""

    def escape() -> None:
        path = window._tk.tk.eval("grab current")
        assert path
        window._tk.tk.call("event", "generate", path, "<Escape>")

    window._tk.after(200, escape)
    answer = dialog.textbox(window, title="say", message="anything")

    assert answer is None
