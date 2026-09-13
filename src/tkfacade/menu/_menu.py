"""The menu-building face, and the submenu that is a row and a menu at once."""

import tkinter as tk
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Protocol, cast

from .._types import Command
from ..choice import NOTHING_CHOSEN, check_option
from ..media import ImageInput, ImageWrapper, PhotoImage
from ..observable import ObservableBool, ObservableStr
from ._rows import CheckboxRow, ChoiceRow, ChoiceRows, CommandRow, MenuPart


class _MenuCommands(Protocol):
    """The two menu subcommands typeshed leaves undeclared.

    ``tkinter`` types the per-kind spellings — ``add_command``,
    ``insert_cascade`` and the rest — but not the general ``add`` and
    ``insert`` they are written on top of.
    """

    def add(self, itemType: str, /, **options: Any) -> None:
        """Append an entry of the named kind."""

    def insert(self, index: int, itemType: str, /, **options: Any) -> None:
        """Put an entry of the named kind at a position."""


class MenuBase:
    """A menu a caller adds rows to, wherever that menu is drawn.

    Worn by :class:`~tkfacade.Menubar`, whose rows are a window's top
    row, and — through :class:`CommandMenu` and :class:`RuledMenu` — by
    :class:`~tkfacade.Menubutton` and every :class:`Submenu`, so a
    caller fills any of them without naming the menu inside it and the
    same call builds at every depth.

    Rows are handed back as handles rather than addressed by text
    afterwards (`_rows.py`), which is what lets two rows of one menu
    carry the same words.
    """

    if TYPE_CHECKING:
        _tk_menu: tk.Menu
        _parts: list[MenuPart]

    __slots__ = ()

    def _seat(self, index: int | None, kind: str, /, **options: object) -> int:
        """Put one entry of ``kind`` at ``index``, appending where None.

        Args:
            index (int | None): Where it goes; None appends.
            kind (str): Tk's own word — ``command``, ``checkbutton``,
                ``radiobutton``, ``cascade`` or ``separator``.
            **options (object): Passed to Tk verbatim.

        Returns:
            The index the entry landed at.

        Raises:
            IndexError: If ``index`` is outside the menu.
        """
        end = len(self._parts)
        if index is None:
            index = end
        elif not 0 <= index <= end:
            raise IndexError(f"index {index} is outside a menu of {end}")
        # add rather than insert at the end: Tk's insert refuses the position one past the last
        commands = cast(_MenuCommands, self._tk_menu)
        if index == end:
            commands.add(kind, **options)
        else:
            commands.insert(index, kind, **options)
        return index

    def _decode(self, image: ImageInput | None, /) -> PhotoImage | None:
        """Decode an image before anything is written, so a bad one writes nothing."""
        if image is None:
            return None
        return ImageWrapper(image).photo_for(self._tk_menu)

    def insert_checkbox(
        self,
        text: str,
        /,
        *,
        index: int | None = None,
        checked: bool | ObservableBool = False,
        command: Command | None = None,
        image: ImageInput | None = None,
        enabled: bool = True,
    ) -> CheckboxRow:
        """Put a row carrying a tick that turns on and off at ``index``.

        Args:
            text (str): The text drawn on the row.
            index (int | None): Where the row goes. Defaults to None,
                appending.
            checked (bool | ObservableBool): The starting state, or the
                observable already holding it, shared with whatever
                else watches or drives that value. Defaults to False.
            command (Command | None): Run when the tick is
                chosen — a plain callable on the mainloop, a coroutine
                function on the root's async core. Defaults to None,
                nothing beside the toggle.
            image (ImageInput | None): Picture drawn beside the text.
            enabled (bool): Whether the row starts choosable.

        Returns:
            The row's handle.

        Raises:
            IndexError: If ``index`` is outside the menu.
        """
        photo = self._decode(image)
        held = checked if isinstance(checked, ObservableBool) else ObservableBool(checked)
        row = CheckboxRow(self, photo, held, command)
        at = self._seat(
            index,
            "checkbutton",
            label=text,
            variable=held.transport_for(self._tk_menu),
            command=row._run_command,
            image="" if photo is None else photo,
            state="normal" if enabled else "disabled",
        )
        self._parts.insert(at, row)
        return row

    def insert_choices(
        self,
        options: Sequence[str],
        /,
        *,
        index: int | None = None,
        chosen: str | ObservableStr = NOTHING_CHOSEN,
        command: Command | None = None,
        enabled: bool = True,
    ) -> ChoiceRows:
        """Put a whole set of rows, of which exactly one is chosen, at ``index``.

        The answer is the set itself, its rows in order on
        :attr:`~tkfacade.ChoiceRows.rows`.

        Args:
            options (Sequence[str]): The rows' texts, each also the
                value choosing it writes.
            index (int | None): Where the first row goes. Defaults to
                None, appending.
            chosen (str | ObservableStr): The starting value, or the
                observable already holding it, shared with whatever
                else watches or drives that choice. Defaults to ``""``,
                meaning nothing chosen yet; the observable the set
                shares is reachable back off the answer either way.
            command (Command | None): Run when a choice is
                chosen — a plain callable on the mainloop, a coroutine
                function on the root's async core. Each row holds its
                own, so one can be swapped without the rest. Defaults
                to None, nothing beside the write.
            enabled (bool): Whether the rows start choosable.

        Returns:
            The set's handle, holding one row per option.

        Raises:
            ValueError: If ``options`` is empty, or if ``chosen`` is a
                plain string that is neither ``""`` nor one of
                ``options``.
            IndexError: If ``index`` is outside the menu.
        """
        if not options:
            raise ValueError("a choice set needs at least one option")
        if not isinstance(chosen, ObservableStr):
            check_option(chosen, tuple(options))
        held = chosen if isinstance(chosen, ObservableStr) else ObservableStr(chosen)
        rows: list[ChoiceRow] = []
        for offset, option in enumerate(options):
            row = ChoiceRow(self, None, held, option, command)
            at = self._seat(
                None if index is None else index + offset,
                "radiobutton",
                label=option,
                variable=held.transport_for(self._tk_menu),
                value=option,
                command=row._run_command,
                state="normal" if enabled else "disabled",
            )
            self._parts.insert(at, row)
            rows.append(row)
        return ChoiceRows(held, tuple(rows))

    def insert_submenu(
        self,
        text: str,
        /,
        *,
        index: int | None = None,
        image: ImageInput | None = None,
        enabled: bool = True,
    ) -> Submenu:
        """Put a row that opens a menu at ``index``, and answer that menu.

        The same call at every depth: a submenu of a submenu is made by
        calling this on what this answers.

        Args:
            text (str): The text drawn on the row.
            index (int | None): Where the row goes. Defaults to None,
                appending.
            image (ImageInput | None): Picture drawn beside the text.
            enabled (bool): Whether the row starts choosable.

        Returns:
            The submenu, which is both the row and a menu to fill.

        Raises:
            IndexError: If ``index`` is outside the menu.
        """
        photo = self._decode(image)
        sub = Submenu(self, photo)
        at = self._seat(
            index,
            "cascade",
            label=text,
            menu=sub._tk_menu,
            image="" if photo is None else photo,
            state="normal" if enabled else "disabled",
        )
        self._parts.insert(at, sub)
        return sub

    def clear(self) -> None:
        """Delete every entry, and everything under them."""
        for part in tuple(self._parts):
            part.delete()

    def _release_deeply(self) -> None:
        """Give back every transport under this menu, submenus included."""
        for part in self._parts:
            part._release()


class CommandMenu(MenuBase):
    """A menu that seats command rows, which a window's bar does not.

    The split exists for the menubar: a command seated in a bar's top
    row is indistinguishable from a menu — Tk draws the two
    identically (`hazards/tkinter.md`, *Menus*) — so the bar wears
    :class:`MenuBase` and this call is simply not on it, refused by
    absence rather than by a raise from a method that promised to
    work. A menu drawn as a column — a menubutton, a submenu — wears
    this or a subclass.
    """

    __slots__ = ()

    def insert_command(
        self,
        text: str,
        /,
        *,
        index: int | None = None,
        command: Command | None = None,
        image: ImageInput | None = None,
        enabled: bool = True,
    ) -> CommandRow:
        """Put a row that runs ``command`` when chosen at ``index``.

        Args:
            text (str): The text drawn on the row. Need not be unique.
            index (int | None): Where the row goes. Defaults to None,
                appending.
            command (Command | None): Run when the row is
                chosen — a plain callable on the mainloop, a coroutine
                function on the root's async core. Defaults to None,
                leaving the row inert.
            image (ImageInput | None): Picture drawn beside the text.
                Defaults to None.
            enabled (bool): Whether the row starts choosable. Defaults
                to True.

        Returns:
            The row's handle.

        Raises:
            IndexError: If ``index`` is outside the menu.
        """
        photo = self._decode(image)
        row = CommandRow(self, photo, command)
        at = self._seat(
            index,
            "command",
            label=text,
            command=row._run_command,
            image="" if photo is None else photo,
            state="normal" if enabled else "disabled",
        )
        self._parts.insert(at, row)
        return row


class RuledMenu(CommandMenu):
    """A menu that can hold a horizontal rule as well as rows.

    Every menu takes rows; only a menu that is *drawn* as a column can
    show a rule between them. A window's menubar is drawn as a row and
    renders a separator as nothing at all, so it wears
    :class:`MenuBase` and this call is simply not on it — refused by
    absence rather than by a raise from a method that promised to work.
    """

    __slots__ = ()

    def insert_separator(self, *, index: int | None = None) -> None:
        """Put a horizontal rule at ``index``.

        Nothing comes back: a rule carries no text, no state, and no
        command. The seated rule leaves with
        :meth:`~tkfacade.MenuBase.clear` or with its menu.

        Args:
            index (int | None): Where the rule goes. Defaults to None,
                appending.

        Raises:
            IndexError: If ``index`` is outside the menu.
        """
        at = self._seat(index, "separator")
        self._parts.insert(at, MenuPart(self))


class Submenu(MenuPart, RuledMenu):
    """A row that opens a menu, and that menu.

    Both at once, because Tk makes them two things and a caller thinks
    of them as one: everything :class:`~tkfacade.MenuPart` offers acts
    on the row that opens it, so a submenu in hand renames or disables
    itself, while the ``insert_*`` calls fill what it opens.
    """

    __slots__ = ("_parts", "_tk_menu")

    def __init__(self, owner: MenuBase, photo: PhotoImage | None, /) -> None:
        """Hold the menu this row sits in, and build the menu it opens.

        Args:
            owner (MenuBase): The menu holding this row.
            photo (PhotoImage | None): The decoded image, if any.
        """
        super().__init__(owner, photo)
        self._tk_menu = tk.Menu(owner._tk_menu, tearoff=False)
        self._parts: list[MenuPart] = []

    def _release(self) -> None:
        """Give back what everything under this submenu borrowed."""
        self._release_deeply()
