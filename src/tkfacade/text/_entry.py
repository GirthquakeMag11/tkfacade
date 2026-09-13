"""The Entry wrapper: the single-line text input, read-only or editable."""

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, ClassVar, Final

from .._types import Anchor, Arrangement, Justify
from ..events import Destroyed, Event
from ..look import Look
from ..observable import ObservableStr
from ..widget import BaseWidget
from ._abstract import AbstractTextInterface

_GAP: Final[int] = 6
"""Pixels between a side-by-side title and its entry; stacked titles get none."""


def _astral_width(widget: tk.Misc, text: str, /) -> int:
    """What one astral character costs in ``widget``'s entry indices.

    Tk's entry indices count whatever unit its Tcl stores strings in, and
    that unit is not fixed: Tcl 8.6 stores UTF-16, so an astral character
    — an emoji, anything past the BMP — spends two of them where Python
    spends one, while Tcl 9 stores codepoints and the two agree. Both
    ship behind the same tkinter API under the same Python floor, so the
    interpreter is the only thing that can say which it is, and it is
    asked rather than inferred from a version number. Text holding no
    astral character is answered without asking, the two units differing
    nowhere else.

    Args:
        widget (tk.Misc): Any widget on the interpreter to measure.
        text (str): The content the conversion is for.

    Returns:
        2 on a UTF-16 Tcl, 1 on a codepoint Tcl or for text no astral
        character appears in.
    """
    if not any(ord(char) > 0xFFFF for char in text):
        return 1
    return int(widget.tk.call("string", "length", "\U0001f600"))


def _to_python_index(text: str, tcl_index: int, /, *, astral: int) -> int:
    """Convert a Tcl entry index into an index into the Python string.

    Where an astral character costs two entry indices, every index after
    one is higher than the Python index a caller works with; where it
    costs one the conversion is the identity. The walk pays each
    character's Tcl width until the Tcl index is spent.

    Args:
        text (str): The entry's content, as Python holds it.
        tcl_index (int): An index as Tk reported it.
        astral (int): What one astral character costs in Tk's indices,
            from :func:`_astral_width`.

    Returns:
        The corresponding index into ``text``; past-the-end clamps to
        ``len(text)``, as Tk's own indices do.
    """
    consumed = 0
    for python_index, char in enumerate(text):
        if consumed >= tcl_index:
            return python_index
        consumed += astral if ord(char) > 0xFFFF else 1
    return len(text)


def _to_tcl_index(text: str, python_index: int, /, *, astral: int) -> int:
    """Convert an index into the Python string into a Tcl entry index.

    The other direction of :func:`_to_python_index`, for handing a
    caller's index to Tk.

    Args:
        text (str): The entry's content, as Python holds it.
        python_index (int): An index into ``text``.
        astral (int): What one astral character costs in Tk's indices,
            from :func:`_astral_width`.

    Returns:
        The corresponding Tcl index; past-the-end clamps to the Tcl
        length.
    """
    return sum(astral if ord(char) > 0xFFFF else 1 for char in text[:python_index])


class Entry(AbstractTextInterface):
    """A themed single-line text input, editable or read-only.

    A read-only entry still takes keyboard focus, so its content can
    be selected and copied, and assigning :attr:`text` still works;
    only GUI editing is locked out. :attr:`text_observable` can be
    watched to follow the content, typed or assigned.

    Appearance comes from the ``TEntry`` style rather than from
    per-widget options, with one exception: no style reaches ``font``
    on this family, so a different one is set on the widget directly.
    """

    if TYPE_CHECKING:
        _tk: ttk.Entry
        _observable: ObservableStr

    __slots__ = ("_observable",)

    _widget_type: ClassVar[type[ttk.Entry]] = ttk.Entry
    """The Tk widget this wrapper drives.

    The one seam the entry family is built on. Everything else in
    construction — the transport wiring, the parking that ties the
    observable's life to the widget's, the teardown binding — is the
    same for every input over a ``ttk.Entry``, so a subclass over one
    of its subclasses names its widget here and inherits the rest.
    :class:`~tkfacade.Combobox` is the standing example.
    """

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        /,
        text: str | ObservableStr = "",
        *,
        read_only: bool = False,
        width: int = 20,
        justify: Justify = "left",
        mask: str = "",
        look: Look | None = None,
    ) -> None:
        """Create the entry, and the observable behind it if none is given.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the
                entry is created inside.
            text (str | ObservableStr): The content — a starting
                string, or the observable already holding it, shared
                with whatever else watches or drives that value.
                Defaults to ``""``, an empty entry with an observable
                of its own.
            read_only (bool): Whether to start disabled, locking the
                GUI out of editing. Defaults to False.
            width (int): Width in characters. Defaults to 20.
            justify (Justify): How the content aligns within the entry.
                Defaults to ``"left"``.
            mask (str): Character to display in place of each real one.
                Defaults to ``""``, showing the content itself.
            look (Look | None): The look to wear from the start; see
                :attr:`~tkfacade.widget.Widget.look`. Defaults to None,
                the library's base style.
        """
        master = self._as_master(parent)
        self._observable = text if isinstance(text, ObservableStr) else ObservableStr(text)
        self._tk = self._widget_type(
            master,
            textvariable=self._observable.transport_for(master),
            width=width,
            justify=justify,
            show=mask,
            state="readonly" if read_only else "normal",
        )
        self._tk._observables = (self._observable,)  # type: ignore[attr-defined]
        super().__init__()
        self.bind(Destroyed(), self._give_back_transport)
        if look is not None:
            self.look = look

    def _give_back_transport(self, _event: Event) -> None:
        """Release the transport ride construction took; the widget is done.

        Bound to :class:`~tkfacade.events.Destroyed` so a shared
        observable never counts a dead widget among its riders
        (`hazards/tkinter.md`, *Variables*: a `tk.Variable` pins its
        interpreter).
        """
        self._observable.release_transport()

    @property
    def disabled(self) -> bool:
        """Whether the GUI is locked out of editing; read live from Tk."""
        return self._tk.instate(["readonly"])

    @property
    def is_empty(self) -> bool:
        """Whether the entry holds no text."""
        return not self._observable.value

    @property
    def text(self) -> str:
        """The entry's whole content.

        Assigning replaces it, and works even while disabled: the write
        goes through :attr:`text_observable`, which Tk honours while it
        ignores GUI edits.
        """
        return self._observable.value

    @text.setter
    def text(self, value: str) -> None:
        self._observable.value = value

    @property
    def text_observable(self) -> ObservableStr:
        """The observable holding the content, for watching or sharing.

        The entry's own unless one was passed to the constructor. Every
        change to the content passes through it, typed or assigned, so
        a watcher on it sees both.
        """
        return self._observable

    @property
    def justify(self) -> Justify:
        """How the content aligns within the entry."""
        return str(self._tk.cget("justify"))  # type: ignore[return-value]

    @justify.setter
    def justify(self, value: Justify) -> None:
        self._tk.configure(justify=value)

    @property
    def mask(self) -> str:
        """Character displayed in place of each real one; ``""`` shows the content.

        Masking is display only. :attr:`text`, :attr:`selection` and
        :meth:`copy_selection` all answer with the real content.
        """
        return str(self._tk.cget("show"))

    @mask.setter
    def mask(self, value: str) -> None:
        self._tk.configure(show=value)

    @property
    def selection(self) -> str:
        """The selected text; ``""`` when this entry has nothing selected."""
        if not self._tk.selection_present():
            return ""
        text = self.text
        astral = _astral_width(self._tk, text)
        first = _to_python_index(text, self._tk.index("sel.first"), astral=astral)
        last = _to_python_index(text, self._tk.index("sel.last"), astral=astral)
        return text[first:last]

    @property
    def cursor(self) -> int:
        """Where the insertion cursor sits, as an index into :attr:`text`.

        Movable while disabled, though only an editable entry draws it.
        An index past the end lands at the end.
        """
        text = self.text
        index = self._tk.index("insert")
        return _to_python_index(text, index, astral=_astral_width(self._tk, text))

    @cursor.setter
    def cursor(self, index: int) -> None:
        text = self.text
        self._tk.icursor(_to_tcl_index(text, index, astral=_astral_width(self._tk, text)))

    def disable(self) -> None:
        """Lock the GUI out of editing; the content is left alone."""
        self._tk.configure(state="readonly")

    def enable(self) -> None:
        """Let the GUI edit again; the content is left alone."""
        self._tk.configure(state="normal")

    def select_all(self) -> None:
        """Select the whole content, replacing any existing selection."""
        self._tk.selection_range(0, "end")

    def select_none(self) -> None:
        """Clear the selection; a no-op when nothing is selected."""
        self._tk.selection_clear()

    def copy_selection(self) -> str:
        """Copy the selection to the clipboard.

        Works while disabled, since copying only reads, and copies the
        real content even while :attr:`mask` is set.

        Returns:
            The text copied, or ``""`` when nothing was selected — in
            which case the clipboard is left untouched.
        """
        selected = self.selection
        if selected:
            self._tk.clipboard_clear()
            self._tk.clipboard_append(selected)
        return selected


class TitleEntryTitle:
    """The title one :class:`TitleEntry` displays, as a live view over its label.

    Reached as :attr:`TitleEntry.title`, never built directly, and
    holding no state of its own: two views of one entry are
    interchangeable.

    :attr:`justify` and :attr:`wraplength` settle the title's own
    lines. What the entry's content does is :attr:`TitleEntry.justify`,
    a separate option on a separate widget.
    """

    __slots__ = ("_owner",)

    def __init__(self, owner: TitleEntry, /) -> None:
        """Bind to the title of ``owner``.

        Args:
            owner (TitleEntry): The entry whose title this views.
        """
        self._owner: TitleEntry = owner

    @property
    def value(self) -> str:
        """The displayed title; ``""`` when none is set."""
        return self._owner._title_observable.value

    @property
    def justify(self) -> Justify:
        """How the lines of a multi-line title align against each other.

        Says nothing about where the block sits in the label, which is
        :attr:`anchor`.
        """
        return str(self._owner._title_label.cget("justify"))  # type: ignore[return-value]

    @justify.setter
    def justify(self, value: Justify) -> None:
        self._owner._title_label.configure(justify=value)

    @property
    def wraplength(self) -> int:
        """The width in pixels at which a line wraps; 0 wraps only on newlines."""
        pixels = str(self._owner._title_label.cget("wraplength"))
        return int(pixels) if pixels else 0

    @wraplength.setter
    def wraplength(self, pixels: int) -> None:
        self._owner._title_label.configure(wraplength=pixels)

    @property
    def anchor(self) -> Anchor:
        """Where the title sits within the label.

        The member that moves a one-line title, :attr:`justify` only
        settling a second line against the first — but only while the
        title is stacked above or below the entry, where the label
        stretches to the entry's width whatever the title's length. Set
        beside the entry the label's cell is its own natural size, so
        there is nothing for the title to move within and this changes
        nothing. Defaults to ``"w"``, which is the label's own default
        rather than anything set here.
        """
        return str(self._owner._title_label.cget("anchor"))  # type: ignore[return-value]

    @anchor.setter
    def anchor(self, value: Anchor) -> None:
        self._owner._title_label.configure(anchor=value)

    def set(self, value: str, /) -> None:
        """Display ``value`` in place of whatever title is there now.

        The write goes through :attr:`TitleEntry.title_observable`, so
        a title shared between entries changes on every one of them,
        and lands whatever the entry's state — the title is chrome, not
        editable content.

        Args:
            value (str): The title to display; ``""`` clears it.
        """
        self._owner._title_observable.value = value


class TitleEntry(AbstractTextInterface):
    """An :class:`~tkfacade.Entry` and a title label, laid out as one widget.

    A frame holds a themed label against a themed entry on whichever
    side :attr:`arrangement` names, and that frame is what a caller lays
    out. Spare width goes to the entry and the title keeps its natural
    size; no row is weighted, so the pair keeps its natural height.

    The text-input members carry the same contract as
    :class:`~tkfacade.Entry`'s. The title is not part of that content: it
    has its own observable, reached through :attr:`title` for its text
    and drawing, and through :attr:`title_observable` for watching or
    sharing.

    Appearance comes from the ``TLabel`` and ``TEntry`` styles — the
    title wears the former, the entry the latter. The entry's ``font``
    is the one exception, as :class:`~tkfacade.Entry` states: no style
    reaches it on this family, so a different one is set on the widget
    directly.
    """

    if TYPE_CHECKING:
        _tk: ttk.Frame
        _title_observable: ObservableStr
        _title_label: ttk.Label
        _text_observable: ObservableStr
        _entry: ttk.Entry

    __slots__ = ("_entry", "_text_observable", "_title_label", "_title_observable")

    def _look_targets(self) -> tuple[tk.Misc, ...]:
        """The entry and the title label: both halves of the pair dress."""
        return (self._entry, self._title_label)

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        /,
        *,
        title: str | ObservableStr = "",
        text: str | ObservableStr = "",
        read_only: bool = False,
        width: int = 20,
        justify: Justify = "left",
        mask: str = "",
        arrangement: Arrangement = "top-bottom",
        look: Look | None = None,
    ) -> None:
        """Create the frame, the label, the entry, and any missing observables.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the
                frame is created inside.
            title (str | ObservableStr): The title — a starting string,
                or the observable already holding it, shared with
                whatever else watches or drives that value. Defaults to
                ``""``, an empty label with an observable of its own.
            text (str | ObservableStr): The content, in the same two
                forms. Defaults to ``""``, an empty entry with an
                observable of its own.
            read_only (bool): Whether to start disabled, locking the
                GUI out of editing. Defaults to False.
            width (int): The entry's width in characters. Defaults
                to 20.
            justify (Justify): How the content aligns within the entry.
                Defaults to ``"left"``.
            mask (str): Character to display in place of each real one.
                Defaults to ``""``, showing the content itself.
            arrangement (Arrangement): Which side of the entry the title
                sits on, named as ``"<title>-<entry>"``. Defaults to
                ``"top-bottom"``, stacking the title above.
            look (Look | None): The look to wear from the start; see
                :attr:`~tkfacade.widget.Widget.look`. Defaults to None,
                the library's base style.
        """
        master = self._as_master(parent)
        self._tk = ttk.Frame(master)
        self._title_observable = title if isinstance(title, ObservableStr) else ObservableStr(title)
        self._title_label = ttk.Label(
            self._tk, textvariable=self._title_observable.transport_for(master)
        )
        self._text_observable = text if isinstance(text, ObservableStr) else ObservableStr(text)
        self._entry = ttk.Entry(
            self._tk,
            textvariable=self._text_observable.transport_for(master),
            width=width,
            justify=justify,
            show=mask,
            state="readonly" if read_only else "normal",
        )
        self._arrange(arrangement)
        self._tk._observables = (self._title_observable, self._text_observable)  # type: ignore[attr-defined]
        super().__init__()
        self._route_events(self._entry, self._title_label)
        self.bind(Destroyed(), self._give_back_transports)
        if look is not None:
            self.look = look

    def _give_back_transports(self, _event: Event) -> None:
        """Release both transport rides construction took; the widget is done.

        Bound to :class:`~tkfacade.events.Destroyed` so a shared
        observable never counts a dead widget among its riders
        (`hazards/tkinter.md`, *Variables*: a `tk.Variable` pins its
        interpreter).
        """
        self._title_observable.release_transport()
        self._text_observable.release_transport()

    def _arrange(self, arrangement: Arrangement, /) -> None:
        """Grid the label and the entry as ``arrangement`` names them.

        Writes the whole layout rather than the part that changed:
        ``grid`` merges into what is already in place, so the cell, the
        column weight and the gap a previous arrangement left behind are
        all cleared by being written over.

        Args:
            arrangement (Arrangement): Which side of the entry the title
                sits on, named as ``"<title>-<entry>"``.
        """
        title_first = arrangement in ("top-bottom", "left-right")
        title_index, entry_index = (0, 1) if title_first else (1, 0)
        if arrangement in ("left-right", "right-left"):
            gap = (0, _GAP) if title_first else (_GAP, 0)
            self._title_label.grid(row=0, column=title_index, sticky="ew", padx=gap)
            self._entry.grid(row=0, column=entry_index, sticky="ew")
            entry_column = entry_index
        else:
            self._title_label.grid(row=title_index, column=0, sticky="ew", padx=0)
            self._entry.grid(row=entry_index, column=0, sticky="ew")
            entry_column = 0
        self._tk.grid_columnconfigure(entry_column, weight=1)
        self._tk.grid_columnconfigure(1 - entry_column, weight=0)

    @property
    def disabled(self) -> bool:
        """Whether the GUI is locked out of editing; read live from Tk."""
        return self._entry.instate(["readonly"])

    @property
    def is_empty(self) -> bool:
        """Whether the entry holds no text; the title does not count."""
        return not self._text_observable.value

    @property
    def text(self) -> str:
        """The entry's whole content.

        Assigning replaces it, and works even while disabled: the write
        goes through :attr:`text_observable`, which Tk honours while it
        ignores GUI edits.
        """
        return self._text_observable.value

    @text.setter
    def text(self, value: str) -> None:
        self._text_observable.value = value

    @property
    def title(self) -> TitleEntryTitle:
        """A live view of the entry's title, and of how it is drawn.

        Not a string and not assignable: reading the text is
        :attr:`TitleEntryTitle.value`, writing it is
        :meth:`TitleEntryTitle.set`, and the view carries the title's
        justification, wrapping and anchor beside them.
        """
        return TitleEntryTitle(self)

    @property
    def text_observable(self) -> ObservableStr:
        """The observable holding the content, for watching or sharing.

        The wrapper's own unless one was passed to the constructor.
        Every change to the content passes through it, typed or
        assigned, so a watcher on it sees both.
        """
        return self._text_observable

    @property
    def title_observable(self) -> ObservableStr:
        """The observable holding the title, for watching or sharing.

        The wrapper's own unless one was passed to the constructor.
        Every change to the title passes through it,
        :meth:`TitleEntryTitle.set` included, so a watcher on it sees
        them all.
        """
        return self._title_observable

    @property
    def arrangement(self) -> Arrangement:
        """Which side of the entry the title sits on, as ``"<title>-<entry>"``.

        Assigning re-places both widgets inside the frame; nothing else
        about either of them changes, so the content, the title and the
        entry's state all survive the move.
        """
        title, entry = self._title_label.grid_info(), self._entry.grid_info()
        if title["row"] == entry["row"]:
            return "left-right" if title["column"] < entry["column"] else "right-left"
        return "top-bottom" if title["row"] < entry["row"] else "bottom-top"

    @arrangement.setter
    def arrangement(self, value: Arrangement) -> None:
        self._arrange(value)

    @property
    def justify(self) -> Justify:
        """How the content aligns within the entry."""
        return str(self._entry.cget("justify"))  # type: ignore[return-value]

    @justify.setter
    def justify(self, value: Justify) -> None:
        self._entry.configure(justify=value)

    @property
    def mask(self) -> str:
        """Character displayed in place of each real one; ``""`` shows the content.

        Masking is display only. :attr:`text`, :attr:`selection` and
        :meth:`copy_selection` all answer with the real content, and
        the title is never masked.
        """
        return str(self._entry.cget("show"))

    @mask.setter
    def mask(self, value: str) -> None:
        self._entry.configure(show=value)

    @property
    def selection(self) -> str:
        """The selected text; ``""`` when this entry has nothing selected."""
        if not self._entry.selection_present():
            return ""
        text = self.text
        astral = _astral_width(self._entry, text)
        first = _to_python_index(text, self._entry.index("sel.first"), astral=astral)
        last = _to_python_index(text, self._entry.index("sel.last"), astral=astral)
        return text[first:last]

    @property
    def cursor(self) -> int:
        """Where the insertion cursor sits, as an index into :attr:`text`.

        Movable while disabled, though only an editable entry draws it.
        An index past the end lands at the end.
        """
        text = self.text
        index = self._entry.index("insert")
        return _to_python_index(text, index, astral=_astral_width(self._entry, text))

    @cursor.setter
    def cursor(self, index: int) -> None:
        text = self.text
        self._entry.icursor(_to_tcl_index(text, index, astral=_astral_width(self._entry, text)))

    def disable(self) -> None:
        """Lock the GUI out of editing; the content is left alone."""
        self._entry.configure(state="readonly")

    def enable(self) -> None:
        """Let the GUI edit again; the content is left alone."""
        self._entry.configure(state="normal")

    def select_all(self) -> None:
        """Select the whole content, replacing any existing selection."""
        self._entry.selection_range(0, "end")

    def select_none(self) -> None:
        """Clear the selection; a no-op when nothing is selected."""
        self._entry.selection_clear()

    def copy_selection(self) -> str:
        """Copy the selection to the clipboard.

        Works while disabled, since copying only reads, and copies the
        real content even while :attr:`mask` is set.

        Returns:
            The text copied, or ``""`` when nothing was selected — in
            which case the clipboard is left untouched.
        """
        selected = self.selection
        if selected:
            self._entry.clipboard_clear()
            self._entry.clipboard_append(selected)
        return selected
