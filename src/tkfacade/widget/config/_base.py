"""The deferred-config contract: accumulate, merge, replay."""

import copy
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from .._widget import Widget  # ruff: ignore[unused-import]


class AbstractConfig[TargetT](ABC):
    """A deferred bundle of geometry options, mergeable and replayable.

    Subclasses accumulate options without touching any widget;
    :meth:`visit` replays them onto a live target in one pass — a
    master for the container-side configs, the placed widget itself
    for the slave-side ones, which is what the type parameter names.
    Two merge directions cover both composition orders:
    :meth:`hard_update` lets later settings override earlier ones,
    :meth:`soft_update` fills only the gaps.
    """

    __slots__ = ()

    @abstractmethod
    def __copy__(self) -> Self:
        """Return an independent copy one level deep; leaf values are shared."""

    @abstractmethod
    def __deepcopy__(self, memo: dict[int, object]) -> Self:
        """Return a fully independent copy; option values are deep-copied too."""

    def __or__(self, other: Self) -> Self:
        """Return a new config: a copy of ``self`` hard-updated with ``other``.

        Neither operand is mutated.
        """
        return self.copy().hard_update(other)

    def __ior__(self, other: Self) -> Self:
        """Hard-update ``self`` with ``other`` in place; ``other`` is unchanged."""
        return self.hard_update(other)

    @abstractmethod
    def hard_update(self, other: Self, /) -> Self:
        """Merge ``other`` into ``self``, ``other`` winning on conflicts.

        Returns:
            ``self``, mutated in place.
        """

    @abstractmethod
    def soft_update(self, other: Self, /) -> Self:
        """Merge ``other`` into ``self``, ``self`` winning on conflicts.

        Returns:
            ``self``, mutated in place.
        """

    @abstractmethod
    def visit(self, target: TargetT, /) -> None:
        """Apply the accumulated options to a live target.

        Args:
            target (TargetT): The wrapper that receives the options —
                the master for container-side configs, the placed
                widget for slave-side ones.
        """

    def copy(self) -> Self:
        """Return a shallow copy via :meth:`__copy__`."""
        return copy.copy(self)

    def deepcopy(self) -> Self:
        """Return a deep copy via :meth:`__deepcopy__`."""
        return copy.deepcopy(self)


class AbstractSetConfig(AbstractConfig["Widget"]):
    """A slave-side config: one manager's placement options, held sparsely.

    The composable twin of one ``*SetOptions`` dict — the options that
    place a widget *inside* its master, where :class:`AbstractConfig`'s
    other children hold what a manager takes on the master itself.
    Options live in one sparse table; subclasses declare a property per
    option (None reads unset, assigning None clears) and a
    :meth:`visit` that replays the table through the widget's own
    placement method, so Tk's incremental merge and the wrapper's
    first-placement defaults ride the same path keyword arguments do.
    """

    if TYPE_CHECKING:
        _options: dict[str, Any]

    __slots__ = ("_options",)

    def __init__(self, **options: Any) -> None:
        """Start from ``options``; subclasses type the surface.

        Args:
            **options (Any): Starting placement options, typed by each
                subclass as its manager's ``*SetOptions``.
        """
        self._options = dict(options)

    def __copy__(self) -> Self:
        """Return an independent copy one level deep; leaf values are shared."""
        new = type(self)()
        new._options = dict(self._options)
        return new

    def __deepcopy__(self, memo: dict[int, object]) -> Self:
        """Return a fully independent copy; option values are deep-copied too."""
        new = type(self)()
        memo[id(self)] = new
        new._options = copy.deepcopy(self._options, memo)
        return new

    def hard_update(self, other: Self, /) -> Self:
        """Merge ``other`` into ``self``, ``other`` winning on conflicts.

        An option ``other`` never set does not clear this one's.

        Returns:
            ``self``, mutated in place.
        """
        self._options |= other._options
        return self

    def soft_update(self, other: Self, /) -> Self:
        """Merge ``other`` into ``self``, ``self`` winning on conflicts.

        Returns:
            ``self``, mutated in place.
        """
        for name, value in other._options.items():
            self._options.setdefault(name, value)
        return self

    def _get(self, name: str, /) -> Any:
        """Answer one held option, None while unset."""
        return self._options.get(name)

    def _set(self, name: str, value: Any, /) -> None:
        """Hold one option, or clear it when ``value`` is None."""
        if value is None:
            self._options.pop(name, None)
        else:
            self._options[name] = value
