"""The data-fields dialog: a fixed form of titled entries, filled or declined.

A sequence of :class:`DataField` declarations defines the form — one
:class:`~tkfacade.TitleEntry` per field, by direction — and the answer
comes back as the values keyed by field label, which is why the labels
must be unique.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from ..button import Button
from ..events import Key, Press
from ..frame import Frame
from ..label import TextLabel
from ..text import TitleEntry
from ..window import Window
from ._dialog import Dialog, _posted


@dataclass(frozen=True, slots=True)
class DataField:
    """One field of a data-fields form: a label over an initial value.

    An inert declaration the dialog applies: carrying it constructs
    nothing until a dialog wears it.

    Args:
        label (str): The field's title, and the key its value comes
            back under — unique within one form.
        initial (str): What the field starts holding. Defaults to
            empty.
    """

    label: str
    initial: str = ""


class _DataFieldsDialog(Dialog[dict[str, str]]):
    """A message over a stack of titled entries, completed by its OK.

    Internal — :func:`data_fields` and :func:`async_data_fields` are
    the public surface. Return in any entry commits the whole form,
    the single-line convention; Escape and the close box cancel
    through the foundation.
    """

    __slots__ = ("_fields", "_ok")

    def __init__(
        self,
        parent: Window,
        /,
        *,
        title: str | None,
        message: str | None,
        fields: Sequence[DataField],
    ) -> None:
        """Build the form; refused whole before any window exists.

        Raises:
            ValueError: If ``fields`` is empty, or two fields share a
                label — the labels key the answer, so a duplicate
                would silently drop a value.
        """
        if not fields:
            raise ValueError("a data-fields dialog needs at least one field")
        labels = [field.label for field in fields]
        if len(set(labels)) != len(labels):
            raise ValueError(f"field labels must be unique, got {labels!r}")
        super().__init__(
            parent,
            title=title if title is not None else "Enter Fields",
            width=360,
            height=120 + 52 * len(fields),
        )
        window = self._window
        window.grid_columnconfigure(0, weight=1)
        row = 0
        if message is not None:
            TextLabel(window, text=message).grid(
                row=row, column=0, sticky="w", padx=10, pady=(10, 4)
            )
            row += 1
        self._fields: dict[str, TitleEntry] = {}
        for field in fields:
            entry = TitleEntry(window, title=field.label, text=field.initial, width=28)
            entry.grid(row=row, column=0, sticky="ew", padx=10, pady=(4, 0))
            entry.bind(Press(Key.ENTER), lambda event: self._commit())
            self._fields[field.label] = entry
            row += 1
        buttons = Frame(window)
        buttons.grid(row=row, column=0, sticky="e", padx=10, pady=10)
        self._ok = Button(buttons, "OK", command=self._commit)
        self._ok.grid(row=0, column=0, padx=(0, 8))
        Button(buttons, "Cancel", command=self.cancel).grid(row=0, column=1)

    def _commit(self) -> None:
        """Complete with every field's value, keyed by label."""
        self.complete({label: entry.text for label, entry in self._fields.items()})


def data_fields(
    parent: Window,
    /,
    *,
    title: str | None = None,
    message: str | None = None,
    fields: Sequence[DataField],
) -> dict[str, str] | None:
    """Ask for a fixed set of values; block until answered, pumping throughout.

    Args:
        parent (Window): The window the dialog prompts for.
        title (str | None): The dialog's title. Defaults to None,
            meaning "Enter Fields".
        message (str | None): A line drawn above the form saying what
            is being asked. Defaults to None, drawing nothing.
        fields (Sequence[DataField]): The form's fields, in drawn
            order; at least one, labels unique.

    Returns:
        Every field's value keyed by its label — empty strings
        included — or None for a dismissal.

    Raises:
        ValueError: If ``fields`` is empty or two fields share a
            label.
    """
    box = _DataFieldsDialog(parent, title=title, message=message, fields=fields)
    return box.result()


async def async_data_fields(
    parent: Window,
    /,
    *,
    title: str | None = None,
    message: str | None = None,
    fields: Sequence[DataField],
) -> dict[str, str] | None:
    """The awaitable :func:`data_fields`: same dialog, no parked frame.

    Await it from a coroutine on the root's core; the options and the
    answer are :func:`data_fields`'s exactly. The dialog is built and
    shown on the interpreter's thread — the crossing needs the
    mainloop live, like every off-thread door in the library.
    """
    box = await _posted(
        parent,
        lambda: _DataFieldsDialog(parent, title=title, message=message, fields=fields),
    )
    return await box.wait()
