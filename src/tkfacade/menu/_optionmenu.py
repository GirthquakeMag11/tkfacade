"""The OptionMenu wrapper: a menubutton whose label is the chosen value."""

import tkinter as tk
from collections.abc import Sequence

from .._subscription import Subscription
from .._types import Command, MenuDirection
from ..choice import NOTHING_CHOSEN, ChoiceSet, check_option
from ..events import Destroyed, Event
from ..look import Look
from ..observable import ObservableStr
from ..widget import BaseWidget
from ._menubutton import Menubutton
from ._rows import ChoiceRow, ChoiceRows


class OptionMenu(Menubutton, ChoiceSet):
    """A menubutton wearing its chosen value as its label.

    The worn :class:`~tkfacade.ChoiceSet` — one value chosen from a
    set, in a shared :class:`~tkfacade.ObservableStr` — presented the
    way ``ttk.OptionMenu`` presents it: a :class:`~tkfacade.Menubutton`
    whose menu is seeded with one choice row per option and whose text
    is whatever is currently chosen. Picking a row, calling a row's
    :meth:`~tkfacade.ChoiceRow.choose`, or driving the observable all
    repaint the label; ``""`` shows an empty button, the honest face of
    nothing chosen.

    Because the label is the chosen value, an assigned :attr:`text`
    lasts only until the next choice repaints it.

    The whole menu-building surface is inherited and stays, as
    tkinter's own option menu leaves its menu reachable: the seeded
    choice rows come first, and anything inserted after them is the
    caller's own business. The choice set itself is born whole from
    ``options``, like every set in the family.

    Appearance comes from the ``TMenubutton`` style, inherited.
    """

    __slots__ = ("_choices", "_chosen", "_label_watch")

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        /,
        options: Sequence[str],
        *,
        chosen: str | ObservableStr = NOTHING_CHOSEN,
        direction: MenuDirection = "below",
        command: Command | None = None,
        enabled: bool = True,
        width: int | None = None,
        look: Look | None = None,
    ) -> None:
        """Create the menubutton and seed its menu with the choice set.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the
                option menu is created inside.
            options (Sequence[str]): The values that may be chosen,
                one row per value.
            chosen (str | ObservableStr): The starting value, or the
                observable already holding it, shared with whatever
                else watches or drives that choice. Defaults to ``""``,
                meaning nothing chosen yet.
            direction (MenuDirection): Where the menu appears relative
                to the button. Defaults to ``"below"``.
            command (Command | None): Run when a choice is chosen — a
                plain callable on the mainloop, a coroutine function on
                the root's async core. Each row holds its own, so one
                can be swapped without the rest. Defaults to None,
                nothing beside the write.
            enabled (bool): Whether the button and its rows start
                choosable. Defaults to True.
            width (int | None): Width in characters. Defaults to None,
                leaving Tk to size to the label.
            look (Look | None): The look to wear from the start; see
                :attr:`~tkfacade.widget.Widget.look`. Defaults to None,
                the library's base style.

        Raises:
            ValueError: If ``options`` is empty, or if ``chosen`` is a
                plain string that is neither ``""`` nor one of
                ``options``.
        """
        offered = tuple(options)
        if not offered:
            raise ValueError("a choice set needs at least one option")
        if not isinstance(chosen, ObservableStr):
            check_option(chosen, offered)
        super().__init__(parent, direction=direction, width=width, enabled=enabled)
        self._choices: ChoiceRows = self.insert_choices(
            offered, chosen=chosen, command=command, enabled=enabled
        )
        self._chosen = self._choices.chosen_observable
        self._label_watch: Subscription = self._chosen.watch(self._show_chosen)
        self.bind(Destroyed(), self._stop_label_watch)
        if look is not None:
            self.look = look

    def _show_chosen(self, value: str, /) -> None:
        """Paint the chosen value onto the button."""
        self._tk.configure(text=value)

    def _stop_label_watch(self, _event: Event) -> None:
        """Cancel the label watch; the button is done.

        Guardless, the route the choice box proved: the binding hears
        the menu's Destroy as well as the button's, and a repeat cancel
        is harmless where a label write on a destroyed button would
        raise from inside a watcher.
        """
        self._label_watch.cancel()

    @property
    def options(self) -> tuple[str, ...]:
        """The values that may be chosen, one per seated row.

        A value is choosable exactly while its row is seated, as the
        set it delegates to answers.
        """
        return self._choices.options

    @property
    def rows(self) -> tuple[ChoiceRow, ...]:
        """The seeded choice rows, in option order."""
        return self._choices.rows
