"""Menu rows as live handles, which is the identity Tk refuses to keep.

A `tk.Menu` addresses its entries by index or by label, and neither
survives contact with an ordinary menu: indices shift the moment an
earlier row is deleted, and two rows may carry the same label, which
``index`` answers for the first of them only. A facade addressing rows
that way has to forbid duplicate text to stay coherent, which is a rule
Tk never imposed and a caller never asked for.

So the handle is the identity. Every row-seating ``insert_*`` answers
one, the menu holding it keeps them in order, and a row's index is
wherever it sits in that list right now. Renaming cannot break
addressing, duplicate text is ordinary, and a handle held across other
rows' deletion still names its own row.
"""

import concurrent.futures
import tkinter as tk
from typing import TYPE_CHECKING, Any, cast

from .._command import dispatch_command
from .._subscription import Subscription
from .._types import Command, ImageSpec
from ..choice import ChoiceSet
from ..events import ACTIVATED
from ..media import ImageInput, ImageWrapper, PhotoImage
from ..observable import ObservableBool, ObservableStr
from ..widget import BaseWidget

if TYPE_CHECKING:
    from ..input import Chord
    from ._menu import MenuBase


class MenuPart:
    """One entry of a menu, whatever kind: a row, or a rule's bare seat.

    Never built by a caller — a menu's ``insert_*`` calls answer the
    right row kind, and seat a bare part internally to hold a rule's
    position, never handing it out. The handle stays valid as rows
    around it come and go, answers :attr:`deleted` once gone, and reads
    its row surface live from Tk, so a row reconfigured behind the
    facade's back still answers truthfully.
    """

    __slots__ = ("_owner", "_photo")

    def __init__(self, owner: MenuBase, photo: PhotoImage | None = None, /) -> None:
        """Hold the menu this sits in, and any image it keeps alive.

        Args:
            owner (MenuBase): The menu holding this entry.
            photo (PhotoImage | None): The decoded image, retained
                here because Tk drops one nothing references.
        """
        self._owner = owner
        self._photo = photo

    def __repr__(self) -> str:
        """Name the class and where it currently sits, or that it is gone."""
        if self.deleted:
            return f"<{type(self).__name__} deleted>"
        return f"<{type(self).__name__} at index {self.index}>"

    @property
    def index(self) -> int:
        """Where this entry currently sits in its menu, counting from 0.

        Read live off the menu's order rather than remembered, so an
        entry deleted above this one moves it without anything to
        update.

        Raises:
            LookupError: If the entry has been deleted.
        """
        for position, part in enumerate(self._owner._parts):
            if part is self:
                return position
        raise LookupError("this entry has been deleted")

    @property
    def deleted(self) -> bool:
        """Whether this entry is gone from its menu."""
        return not any(part is self for part in self._owner._parts)

    def delete(self) -> None:
        """Remove this entry from its menu.

        Deleting twice is not an error: the second call has nothing to
        do and does nothing, which is what lets a caller drop an entry
        without first asking whether something else already did.
        """
        if self.deleted:
            return
        position = self.index
        self._owner._tk_menu.delete(position)
        del self._owner._parts[position]
        self._release()

    def _release(self) -> None:
        """Give back whatever this entry borrowed; nothing, by default."""

    @property
    def text(self) -> str:
        """The text drawn on the row.

        Assigning renames what is drawn and nothing else — the row is
        addressed by this handle, not by its text, so two rows may
        carry the same words without either becoming unreachable.
        """
        return str(self._owner._tk_menu.entrycget(self.index, "label"))

    @text.setter
    def text(self, value: str) -> None:
        self._owner._tk_menu.entryconfigure(self.index, label=value)

    @property
    def enabled(self) -> bool:
        """Whether the row can be chosen; read live from Tk."""
        return str(self._owner._tk_menu.entrycget(self.index, "state")) != "disabled"

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._owner._tk_menu.entryconfigure(self.index, state="normal" if value else "disabled")

    @property
    def image(self) -> ImageSpec | None:
        """The picture drawn beside the text, or None where there is none.

        Answers Tk's own handle for the image, the stratum this relays
        verbatim; assign any :data:`~tkfacade.ImageInput` to replace it,
        or None to take it away.
        """
        held = str(self._owner._tk_menu.entrycget(self.index, "image"))
        return held or None

    @image.setter
    def image(self, value: ImageInput | None) -> None:
        photo = ImageWrapper(value).photo_for(self._owner._tk_menu) if value is not None else None
        self._owner._tk_menu.entryconfigure(self.index, image="" if photo is None else photo)
        self._photo = photo

    def invoke(self) -> None:
        """Do what choosing the row does.

        A disabled row does nothing, Tk's own guard rather than a
        second one written here.
        """
        self._owner._tk_menu.invoke(self.index)

    def _emitter(self) -> BaseWidget:
        """The wrapper this row's facade unit emits activations on.

        A row can sit menus deep: every non-widget owner is a
        :class:`Submenu` — a row and a menu at once — so the walk
        climbs owners until it reaches the menubutton or menubar that
        carries the event surface.
        """
        owner: object = self._owner
        while not isinstance(owner, BaseWidget):
            owner = cast(MenuPart, owner)._owner
        return owner


class CommandRow(MenuPart):
    """A row that is nothing but its command, and its siblings' base.

    Nothing but its command the way a :class:`~tkfacade.Button` is, and
    the command-holding base the stateful row kinds extend.

    The command is a row's user-choice channel: menus close Tk's
    event route (`hazards/tkinter.md`, *Menus*), so what a user does arrives
    only here or through a row's observable. The command itself is
    dual-kind — a plain callable runs on the mainloop, a coroutine
    function is scheduled fire-and-forget on the root's async core —
    and Tk is given the row's own dispatcher rather than the caller's
    callable, so assigning :attr:`command` swaps what runs without
    touching the seated entry.

    A real keyboard shortcut is the :attr:`chord` property: hand it a
    :class:`~tkfacade.Chord` and the row draws accelerator text
    derived from the chord's own set and invokes on its edge — one
    source of truth, where Tk's ``-accelerator`` is display text
    nothing checks (`hazards/tkinter.md`, *Menus*).
    """

    __slots__ = ("_chord", "_chord_subscription", "_command", "_command_tasks")

    def __init__(
        self,
        owner: MenuBase,
        photo: PhotoImage | None,
        command: Command | None,
        /,
    ) -> None:
        """Hold the menu, the image, and what choosing the row runs.

        Args:
            owner (MenuBase): The menu holding this row.
            photo (PhotoImage | None): The decoded image, if any.
            command (Command | None): What choosing runs,
                of either kind; None is nothing.
        """
        super().__init__(owner, photo)
        self._command = command
        self._command_tasks: set[concurrent.futures.Future[Any]] = set()
        self._chord: Chord | None = None
        self._chord_subscription: Subscription | None = None

    def _run_command(self) -> None:
        """Run the held command, then emit the activation; None runs nothing.

        The emission lands on the facade unit's wrapper — the
        menubutton or menubar this row's menu chain hangs off — with
        the row itself in the payload, since menus close Tk's event
        route and the wrapper is where subscribers can stand.
        """
        held = self._command
        if held is not None:
            dispatch_command(
                self._owner._tk_menu, held, self._command_tasks, f"the command of {self!r}"
            )
        self._emitter().emit(ACTIVATED, {"row": self})

    @property
    def command(self) -> Command | None:
        """What choosing the row runs; None is nothing.

        Assigning swaps what future choices run. Coroutine runs
        already in flight from the old command are left to finish —
        death narrows the future, never the present.
        """
        return self._command

    @command.setter
    def command(self, value: Command | None) -> None:
        self._command = value

    @property
    def chord(self) -> Chord | None:
        """The key combination that invokes this row; None is none.

        Assign a :class:`~tkfacade.Chord` and the row derives its
        drawn accelerator text from the chord's
        :attr:`~tkfacade.Chord.caption` and subscribes its own
        :meth:`invoke` to the chord's edge — the full activation, Tk's
        disabled guard and the :data:`~tkfacade.ACTIVATED` emission
        included, exactly as a click. The chord may live before, and
        beyond, this row: assigning a different chord (or None), or
        deleting the row, detaches only the row's own subscription,
        and a chord shared with other listeners keeps them all.

        The chord stays root-global; the *row* is windowed. Its edge
        invokes only while the window holding this row's menu has the
        input focus, so the same combination can mean different rows
        in different windows.

        The one honest edge: the chord is the caller's, so a caller
        cancelling it leaves this row drawing text for a binding that
        will never fire again — clear :attr:`chord` (or assign a live
        one) when retiring a chord a row still wears.
        """
        return self._chord

    @chord.setter
    def chord(self, value: Chord | None) -> None:
        if self._chord_subscription is not None:
            self._chord_subscription.cancel()
            self._chord_subscription = None
        self._chord = value
        caption = "" if value is None else value.caption
        self._owner._tk_menu.entryconfigure(self.index, accelerator=caption)
        if value is not None:
            self._chord_subscription = value.subscribe(self._accelerated_invoke)

    def _accelerated_invoke(self) -> None:
        """Invoke on the chord's edge — while this row's window is focused.

        The row's toplevel is found off the widget its menu chain
        hangs from, stepping off any ``tk.Menu`` first: Tk answers a
        *menu* as its own top-of-hierarchy window, so a menubar's menu
        must be resolved through its master. Focus answering nothing —
        another application's turn, or an exotic holder like a posted
        menu's clone — invokes nothing.
        """
        anchor: tk.Misc = self._emitter()._tk
        while isinstance(anchor, tk.Menu) and anchor.master is not None:
            anchor = anchor.master
        toplevel = anchor.winfo_toplevel()
        try:
            focused = toplevel.focus_get()
        except KeyError, tk.TclError:
            return
        if focused is None or focused.winfo_toplevel() is not toplevel:
            return
        self.invoke()

    def _release(self) -> None:
        """Detach the accelerator subscription; the chord is the caller's."""
        if self._chord_subscription is not None:
            self._chord_subscription.cancel()
            self._chord_subscription = None
        self._chord = None


class CheckboxRow(CommandRow):
    """A row carrying a tick that turns on and off.

    The tick is an :class:`~tkfacade.ObservableBool` — the row's own
    unless one was passed in, shared with whatever else watches or
    drives that value, so one tick can be a menu row and a checkbutton
    at once. The command runs beside the toggle, on user choice only.
    """

    __slots__ = ("_observable",)

    def __init__(
        self,
        owner: MenuBase,
        photo: PhotoImage | None,
        held: ObservableBool,
        command: Command | None,
        /,
    ) -> None:
        """Hold the menu, the image, the tick's observable, and the command.

        Args:
            owner (MenuBase): The menu holding this row.
            photo (PhotoImage | None): The decoded image, if any.
            held (ObservableBool): The observable carrying the tick.
            command (Command | None): Run when the tick is
                chosen, of either kind; None is nothing extra.
        """
        super().__init__(owner, photo, command)
        self._observable = held

    @property
    def checked(self) -> bool:
        """Whether the tick is on.

        Assigning writes through :attr:`checked_observable`, so every
        watcher hears it.
        """
        return self._observable.value

    @checked.setter
    def checked(self, value: bool) -> None:
        self._observable.value = value

    @property
    def checked_observable(self) -> ObservableBool:
        """The observable holding the tick, for watching or sharing."""
        return self._observable

    def _release(self) -> None:
        """Give back the transport ride this row took, and the base's holdings."""
        super()._release()
        self._observable.release_transport()


class ChoiceRow(CommandRow):
    """One row of a set, of which exactly one is chosen.

    Never made alone — :meth:`~tkfacade.MenuBase.insert_choices` builds
    a whole set at once, because a lone choice bound to a group nothing
    else shares is permanently chosen and says nothing. Each row holds
    its own command, so swapping one row's changes that row alone.
    """

    __slots__ = ("_group", "_value")

    def __init__(
        self,
        owner: MenuBase,
        photo: PhotoImage | None,
        group: ObservableStr,
        value: str,
        command: Command | None,
        /,
    ) -> None:
        """Hold the menu, the image, the set's observable, and this row's value.

        Args:
            owner (MenuBase): The menu holding this row.
            photo (PhotoImage | None): The decoded image, if any.
            group (ObservableStr): The observable the whole set shares.
            value (str): What choosing this row writes to it.
            command (Command | None): Run when this row is
                chosen, of either kind; None is nothing extra.
        """
        super().__init__(owner, photo, command)
        self._group = group
        self._value = value

    @property
    def value(self) -> str:
        """What choosing this row writes into the set's observable."""
        return self._value

    @property
    def group(self) -> ObservableStr:
        """The observable this row's set shares; what makes it a set."""
        return self._group

    @property
    def chosen(self) -> bool:
        """Whether this row is the one currently chosen."""
        return self._group.value == self._value

    def choose(self) -> None:
        """Make this the chosen row, as picking it would."""
        self._group.value = self._value

    def _release(self) -> None:
        """Give back the set's transport ride, and the base's holdings."""
        super()._release()
        self._group.release_transport()


class ChoiceRows(ChoiceSet):
    """The set of choice rows a menu grew in one call.

    The worn :class:`~tkfacade.ChoiceSet` — one value chosen from a
    set, in a shared :class:`~tkfacade.ObservableStr` — seated as menu
    rows: the set-level thing the rows share, where before this only
    the observable tied them together. Answered by
    :meth:`~tkfacade.MenuBase.insert_choices`, never built by a caller.

    The observable is reachable back off the set as
    :attr:`~tkfacade.ChoiceSet.chosen_observable`, so sharing the
    choice with a widget no longer requires supplying an observable up
    front — grow the rows, then hand what they share to whatever else
    should speak it.
    """

    __slots__ = ("_chosen", "_rows")

    def __init__(self, chosen: ObservableStr, rows: tuple[ChoiceRow, ...], /) -> None:
        """Hold the shared observable and the rows the one call seated.

        Args:
            chosen (ObservableStr): The observable the set shares.
            rows (tuple[ChoiceRow, ...]): The seated rows, in option
                order.
        """
        self._chosen = chosen
        self._rows = rows

    @property
    def rows(self) -> tuple[ChoiceRow, ...]:
        """The set's rows, in option order.

        Every handle the call seated, deleted ones included — a
        deleted row keeps its place here and answers
        :attr:`~tkfacade.MenuPart.deleted`, the way any held handle
        does.
        """
        return self._rows

    @property
    def options(self) -> tuple[str, ...]:
        """The values that may be chosen, one per seated row.

        A value is choosable exactly while its row is seated, so a
        deleted row's value drops out of the domain here.
        """
        return tuple(row.value for row in self._rows if not row.deleted)
