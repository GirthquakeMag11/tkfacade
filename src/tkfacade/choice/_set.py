"""The choosing core: the face every presentation of an exclusive choice wears."""

from collections.abc import Sequence
from typing import TYPE_CHECKING

from ..observable import ObservableStr

NOTHING_CHOSEN = ""
"""What :attr:`ChoiceSet.chosen` holds while no option has been picked."""


def check_option(value: str, options: Sequence[str], /) -> None:
    """Raise unless ``value`` is one of ``options`` or the no-choice value.

    Raises:
        ValueError: If ``value`` is neither.
    """
    if value != NOTHING_CHOSEN and value not in options:
        raise ValueError(f"{value!r} is not one of the options: {tuple(options)!r}")


class ChoiceSet:
    """One value chosen from a set of options, however the set is drawn.

    The face every presentation of an exclusive choice wears:
    :class:`~tkfacade.ChoiceBox` shows the set as a dropdown,
    :class:`~tkfacade.ChoiceSpinner` as a step-through,
    :class:`~tkfacade.ChoiceButtons` as a bank of themed radiobuttons,
    and a menu's :meth:`~tkfacade.MenuBase.insert_choices` answers a
    :class:`~tkfacade.ChoiceRows` of seated rows — one concept in four
    presentations, so choosing reads and writes the same way wherever a
    set of exclusive choices comes out.

    The chosen value is a shared :class:`~tkfacade.ObservableStr`;
    ``""`` is the value meaning nothing has been chosen, which is a
    real state rather than an error. Tk enforces no domain anywhere a
    choice is drawn, so :attr:`chosen` enforces it here — and a caller
    driving the shared observable directly reaches the widget without
    passing that check, the escape every wearer documents.
    """

    if TYPE_CHECKING:
        _chosen: ObservableStr

        @property
        def options(self) -> tuple[str, ...]:
            """The values that may be chosen; each wearer answers its own."""

    __slots__ = ()

    @property
    def chosen(self) -> str:
        """The chosen value, or ``""`` while nothing has been chosen.

        Assigning chooses, whatever state the presentation is in: the
        write goes through :attr:`chosen_observable`.

        Raises:
            ValueError: If the value is neither ``""`` nor one of
                :attr:`options`.
        """
        return self._chosen.value

    @chosen.setter
    def chosen(self, value: str) -> None:
        check_option(value, self.options)
        self._chosen.value = value

    @property
    def chosen_observable(self) -> ObservableStr:
        """The observable holding the choice, for watching or sharing.

        Every change passes through it, picked or assigned, so a
        watcher on it sees both — and a write straight to it reaches
        the widget without the domain check :attr:`chosen` applies.
        """
        return self._chosen
