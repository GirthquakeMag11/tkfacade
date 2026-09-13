"""The data-fields dialog: a fixed form filled, committed, or declined.

The claims pinned: initial values come back unedited and edits come
back keyed by field label, empty strings included; Return in any
entry commits the whole form; a duplicate label or an empty field
sequence is refused whole, before any window exists; and the
function surface blocks its caller and answers None on Escape.
"""

import pytest

import tkfacade
from conftest import Pump
from tkfacade import dialog
from tkfacade.dialog._fields import _DataFieldsDialog

pytestmark = pytest.mark.gui


def _form(window: tkfacade.Window) -> _DataFieldsDialog:
    """A two-field form: a prefilled name, an empty email."""
    return _DataFieldsDialog(
        window,
        title=None,
        message="who are you",
        fields=(
            dialog.DataField("Name", "Ada"),
            dialog.DataField("Email"),
        ),
    )


def test_ok_answers_every_field_keyed_by_label(window: tkfacade.Window, pump: Pump) -> None:
    """Initials survive, edits land, and the empty string is a value."""
    box = _form(window)
    box.show()
    pump(window)

    box._fields["Email"].text = "ada@example.org"
    box._ok.invoke()

    assert box.result() == {"Name": "Ada", "Email": "ada@example.org"}

    untouched = _form(window)
    untouched._ok.invoke()
    assert untouched.result() == {"Name": "Ada", "Email": ""}


def test_return_in_an_entry_commits_the_whole_form(window: tkfacade.Window, pump: Pump) -> None:
    """The single-line convention: Return anywhere is the form's OK."""
    box = _form(window)
    box.show()
    pump(window)
    entry = box._fields["Name"]
    entry._entry.focus_force()
    pump(window)

    entry._entry.event_generate("<Return>")
    pump(window)

    assert box.result() == {"Name": "Ada", "Email": ""}


def test_a_bad_field_set_is_refused_whole(window: tkfacade.Window, pump: Pump) -> None:
    """Duplicate labels and an empty sequence raise before any window."""
    with pytest.raises(ValueError, match="unique"):
        _DataFieldsDialog(
            window,
            title=None,
            message=None,
            fields=(dialog.DataField("Twin"), dialog.DataField("Twin")),
        )
    with pytest.raises(ValueError, match="at least one"):
        _DataFieldsDialog(window, title=None, message=None, fields=())


def test_the_function_blocks_and_escape_answers_none(window: tkfacade.Window, pump: Pump) -> None:
    """``dialog.data_fields`` parks its caller; Escape dismisses to None."""

    def escape() -> None:
        path = window._tk.tk.eval("grab current")
        assert path
        window._tk.tk.call("event", "generate", path, "<Escape>")

    window._tk.after(200, escape)
    answer = dialog.data_fields(window, fields=(dialog.DataField("Anything"),))

    assert answer is None
