"""The textbox dialog: free text asked for, taken or declined.

A message, a multi-line box, OK and Cancel; the answer is the content
as it stands, the empty string included — ``None`` stays the
dismissal's spelling, so a caller can tell "nothing entered" from
"declined to answer".
"""

from ..button import Button
from ..frame import Frame
from ..label import TextLabel
from ..text import TextBox
from ..window import Window
from ._dialog import Dialog, _posted


class _TextboxDialog(Dialog[str]):
    """A message over a multi-line box, completed by its own OK.

    Internal — :func:`textbox` and :func:`async_textbox` are the
    public surface. Return types a newline here, the box being
    multi-line, so the affirmative is the OK button alone; Escape and
    the close box cancel through the foundation.
    """

    __slots__ = ("_box", "_ok")

    def __init__(
        self,
        parent: Window,
        /,
        *,
        title: str | None,
        message: str | None,
        initial_text: str,
    ) -> None:
        super().__init__(
            parent,
            title=title if title is not None else "Enter Text",
            width=420,
            height=280,
        )
        window = self._window
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(1, weight=1)
        if message is not None:
            TextLabel(window, text=message).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 4))
        self._box = TextBox(window, initial_text, width=46, height=8)
        self._box.grid(row=1, column=0, sticky="nsew", padx=10)
        buttons = Frame(window)
        buttons.grid(row=2, column=0, sticky="e", padx=10, pady=8)
        self._ok = Button(buttons, "OK", command=lambda: self.complete(self._box.text))
        self._ok.grid(row=0, column=0, padx=(0, 8))
        Button(buttons, "Cancel", command=self.cancel).grid(row=0, column=1)

    def show(self) -> None:
        """Post the dialog and put the keyboard in the box, ready to type."""
        super().show()
        if not self.done:
            self._box._text.focus_set()


def textbox(
    parent: Window,
    /,
    *,
    title: str | None = None,
    message: str | None = None,
    initial_text: str = "",
) -> str | None:
    """Ask for free text; block until answered, pumping throughout.

    Args:
        parent (Window): The window the dialog prompts for.
        title (str | None): The dialog's title. Defaults to None,
            meaning "Enter Text".
        message (str | None): A line drawn above the box saying what
            is being asked. Defaults to None, drawing nothing.
        initial_text (str): What the box starts holding. Defaults to
            empty.

    Returns:
        The content as it stands on OK — the empty string included —
        or None for a dismissal.
    """
    box = _TextboxDialog(parent, title=title, message=message, initial_text=initial_text)
    return box.result()


async def async_textbox(
    parent: Window,
    /,
    *,
    title: str | None = None,
    message: str | None = None,
    initial_text: str = "",
) -> str | None:
    """The awaitable :func:`textbox`: same dialog, no parked frame.

    Await it from a coroutine on the root's core; the options and the
    answer are :func:`textbox`'s exactly. The dialog is built and
    shown on the interpreter's thread — the crossing needs the
    mainloop live, like every off-thread door in the library.
    """
    box = await _posted(
        parent,
        lambda: _TextboxDialog(parent, title=title, message=message, initial_text=initial_text),
    )
    return await box.wait()
