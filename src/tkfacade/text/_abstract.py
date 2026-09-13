"""The text-input contract: one read-only rule for every text input.

An :class:`AbstractTextInterface` holds editable text under a
read-only mode that locks out the user and leaves the program alone.
:class:`~tkfacade.TextBox` is the multi-line implementation,
:class:`~tkfacade.Entry` the single-line one, and :class:`~tkfacade.TitleEntry`
the single-line one carrying a title.
"""

from abc import ABC, abstractmethod

from ..widget import Widget


class AbstractTextInterface(Widget, ABC):
    """A text input whose read-only mode locks out the user, not the program.

    Read-only — ``read_only`` at construction, :meth:`disable`
    afterwards — refuses typing, pasting and deleting, while assigning
    :attr:`text` works in either mode. Reading is never restricted: a
    read-only input keeps its place in keyboard focus traversal, its
    content stays selectable, and :meth:`copy_selection` works
    throughout.
    """

    __slots__ = ()

    @property
    @abstractmethod
    def disabled(self) -> bool:
        """Whether the GUI is locked out of editing; read live from Tk."""

    @property
    @abstractmethod
    def is_empty(self) -> bool:
        """Whether the input holds no text."""

    @property
    @abstractmethod
    def text(self) -> str:
        """The whole content.

        Assigning replaces it, and works while read-only.
        """

    @text.setter
    @abstractmethod
    def text(self, value: str) -> None:
        """Replace the whole content.

        Args:
            value (str): What the input holds from now on.
        """

    @property
    @abstractmethod
    def selection(self) -> str:
        """The selected text; ``""`` when nothing is selected."""

    @abstractmethod
    def disable(self) -> None:
        """Lock the GUI out of editing; the content is left alone."""

    @abstractmethod
    def enable(self) -> None:
        """Let the GUI edit again; the content is left alone."""

    @abstractmethod
    def select_all(self) -> None:
        """Select the whole content, replacing any existing selection."""

    @abstractmethod
    def select_none(self) -> None:
        """Clear the selection; a no-op when nothing is selected."""

    @abstractmethod
    def copy_selection(self) -> str:
        """Copy the selection to the clipboard.

        Works while read-only, since copying only reads.

        Returns:
            The text copied, or ``""`` when nothing was selected — in
            which case the clipboard is left untouched.
        """
