"""The message and confirm dialogs: one line said, acknowledged or answered.

One class carries both: a message over one button acknowledges, over
two it answers.

:func:`confirm` is the one deliberate departure from the family's
``T | None`` convention: a declined confirmation *is* a "no", so
Escape, the close box, and the decline button all read ``False``.
"""

from ..button import Button
from ..events import Key, Press
from ..label import TextLabel
from ..window import Window
from ._dialog import Dialog, _posted


class _MessageDialog(Dialog[bool]):
    """A message over one or two buttons; True on the affirmative.

    Internal — :func:`message` and :func:`confirm` (and the save
    gate's overwrite check) are the public surface. Return affirms,
    the default-button convention; Escape and the close box cancel
    through the foundation.
    """

    __slots__ = ("_affirm", "_decline", "_label")

    def __init__(
        self,
        parent: Window,
        message: str,
        /,
        *,
        title: str,
        affirm: str = "OK",
        decline: str | None = None,
    ) -> None:
        super().__init__(parent, title=title, width=340, height=130)
        window = self._window
        window.resizable_width = False
        window.resizable_height = False
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(0, weight=1)

        self._label = TextLabel(window, text=message).grid(
            row=0, column=0, padx=14, pady=(14, 8), columnspan=2
        )
        self._affirm = Button(window, affirm, command=lambda: self.complete(True))

        if decline is not None:
            window.grid_columnconfigure(1, weight=1)
            self._affirm.grid(row=1, column=0, padx=(8, 8), pady=(0, 8))
            self._label.grid(row=0, column=0, padx=14, pady=(14, 8), columnspan=2)
            self._decline = Button(window, decline, command=self.cancel).grid(
                row=1, column=1, padx=(0, 8), pady=(0, 8)
            )
        else:
            self._affirm.grid(row=1, column=0, padx=8, pady=(0, 8))
            self._label.grid(row=0, column=0, padx=14, pady=(14, 8))

        window.bind(Press(Key.ENTER), lambda event: self.complete(True))


def message(
    parent: Window,
    message: str,
    /,
    *,
    title: str | None = None,
) -> None:
    """Say one thing and wait for it to be acknowledged.

    Blocks until OK, Return, Escape, or the close box — pumping
    throughout, like every sync dialog — and answers nothing: an
    acknowledgment carries no information.

    Args:
        parent (Window): The window the dialog prompts for.
        message (str): What is said.
        title (str | None): The dialog's title. Defaults to None,
            meaning "Message".
    """
    _MessageDialog(parent, message, title=title if title is not None else "Message").result()


async def async_message(
    parent: Window,
    message: str,
    /,
    *,
    title: str | None = None,
) -> None:
    """The awaitable :func:`message`: same dialog, no parked frame."""
    box = await _posted(
        parent,
        lambda: _MessageDialog(parent, message, title=title if title is not None else "Message"),
    )
    await box.wait()


def confirm(
    parent: Window,
    message: str,
    /,
    *,
    title: str | None = None,
    affirm: str = "OK",
    decline: str = "Cancel",
) -> bool:
    """Ask a yes-or-no question; block until answered, pumping throughout.

    Args:
        parent (Window): The window the dialog prompts for.
        message (str): The question.
        title (str | None): The dialog's title. Defaults to None,
            meaning "Confirm".
        affirm (str): The yes button's caption. Defaults to "OK".
        decline (str): The no button's caption. Defaults to "Cancel".

    Returns:
        True on the affirmative; False for the decline button,
        Escape, or the close box — a declined confirmation is a "no",
        so this family member answers bool rather than ``T | None``.
    """
    box = _MessageDialog(
        parent,
        message,
        title=title if title is not None else "Confirm",
        affirm=affirm,
        decline=decline,
    )
    return box.result() is True


async def async_confirm(
    parent: Window,
    message: str,
    /,
    *,
    title: str | None = None,
    affirm: str = "OK",
    decline: str = "Cancel",
) -> bool:
    """The awaitable :func:`confirm`: same dialog, no parked frame."""
    box = await _posted(
        parent,
        lambda: _MessageDialog(
            parent,
            message,
            title=title if title is not None else "Confirm",
            affirm=affirm,
            decline=decline,
        ),
    )
    return await box.wait() is True
