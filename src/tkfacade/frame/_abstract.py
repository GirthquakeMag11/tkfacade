"""The multi-frame contract: sibling pages share one region of a window.

An :class:`AbstractMultiFrame` gives one region of a window multiple
switchable pages, addressed by key. Pages come back as
:class:`~tkfacade.Frame` wrappers for the caller to build content
inside; the container owns their placement. How pages are hosted and
revealed belongs to the implementations: :class:`StackFrame` grids
every page into one shared cell and maps one at a time, while
:class:`TabFrame` hands them to a ``ttk.Notebook`` so the user can
switch pages too.
"""

from abc import ABC, abstractmethod
from collections.abc import Hashable, Iterator, Mapping

from ..widget import Widget
from ._frame import Frame


class AbstractMultiFrame(Widget, Mapping[Hashable, Frame], ABC):
    """A card stack of sibling frames sharing one region.

    Pages are addressed by key and handed back as :class:`~tkfacade.Frame`
    wrappers to build content in; the container places them, so a caller
    lays out the container and leaves the pages alone. A page is a frame
    like any other apart from that: it takes a padding and a relief of
    its own, and can be destroyed through its own surface.

    The mapping face is those pages, keyed as they were added, and is
    read-only: a page comes only from :meth:`add`. A page destroyed out
    from under the container leaves the mapping, freeing its key to
    :meth:`add` again, and :attr:`showing` never answers a destroyed
    page. Containers compare by identity.
    """

    __slots__ = ()

    @abstractmethod
    def __getitem__(self, key: Hashable) -> Frame:
        """Return the page frame at ``key``.

        Args:
            key (Hashable): The page's key.

        Returns:
            The page frame at ``key``.

        Raises:
            KeyError: If ``key`` names no existing page.
        """

    @abstractmethod
    def __iter__(self) -> Iterator[Hashable]:
        """Iterate over the page keys, in the order the pages were added."""

    @abstractmethod
    def __len__(self) -> int:
        """The number of pages the container holds."""

    def __eq__(self, other: object) -> bool:
        """Equal only to itself: identity, not contents."""
        return self is other

    def __hash__(self) -> int:
        """Hash consistently with :meth:`__eq__`."""
        return id(self)

    @property
    @abstractmethod
    def showing(self) -> Frame | None:
        """The page currently shown, or ``None`` before any show."""

    @abstractmethod
    def add(self, key: Hashable, /) -> Frame:
        """Create a page under ``key`` and return its frame.

        The first page added is the one initially shown, unless
        :meth:`show` intervenes.

        Args:
            key (Hashable): Key for the new page. ``None`` is refused:
                it is the container's own nothing-shown sentinel.

        Returns:
            The new page frame.

        Raises:
            ValueError: If ``key`` names an existing page, or is None.
        """

    @abstractmethod
    def show(self, key: Hashable, /) -> None:
        """Bring the page at ``key`` into view.

        Exactly one page is mapped at a time: hidden pages report
        ``winfo_ismapped() == False``. How the container sizes is
        implementation-dependent: :class:`StackFrame` sizes to the
        shown page, while a Notebook-backed container such as
        :class:`TabFrame` sizes to the largest page.

        Args:
            key (Hashable): The page's key.

        Raises:
            KeyError: If ``key`` names no existing page.
        """
