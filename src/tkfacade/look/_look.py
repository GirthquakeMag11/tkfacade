"""The look: one bag of styling values, worn by any themed widget.

A :class:`Look` accepts the library's whole styling vocabulary — the
union of every option the style probe measured to act
(`experiments/ttk_style_probe/`) — and applies the compatible subset to
whatever widget it is handed, per the styling rulings (2026-08-27). One
look dresses a bevy of widgets of different kinds, or a single widget
given a look only it wears; a value the worn widget's kind ignores
simply does not apply there, while a name outside the vocabulary
entirely is refused — a typo is not a styling option.

What you set is what you see: every value is written through the
state-map layer with a match-everything entry carrying the base value,
so a theme's own state maps — which silently beat plain configuration
from anywhere up the style chain — can never override a caller's
setting. Situation values (``disabled``, ``active`` and the rest) ride
the same write, ahead of the catch-all.
"""

import itertools
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Any, Final, TypedDict, Unpack, cast

from .._params import (
    SashStyleOptions,
    TButtonStyleOptions,
    TCheckbuttonStyleOptions,
    TComboboxStyleOptions,
    TEntryStyleOptions,
    TFrameStyleOptions,
    TLabelframeLabelStyleOptions,
    TLabelframeStyleOptions,
    TLabelStyleOptions,
    TMenubuttonStyleOptions,
    TNotebookStyleOptions,
    TNotebookTabStyleOptions,
    TPanedwindowStyleOptions,
    TProgressbarStyleOptions,
    TreeviewCellStyleOptions,
    TreeviewHeadingStyleOptions,
    TreeviewItemStyleOptions,
    TreeviewStyleOptions,
    TScaleStyleOptions,
    TScrollbarStyleOptions,
    TSeparatorStyleOptions,
    TSizegripStyleOptions,
)
from .._types import (
    Anchor,
    Color,
    Compound,
    EdgePosition,
    FontSpec,
    ImageSpec,
    Justify,
    Padding,
    PadValue,
    Relief,
)


class LookOptions(TypedDict, total=False):
    """The whole styling vocabulary, as one keyword surface.

    The union of every option the style probe measured to act on some
    themed widget kind. A :class:`Look` accepts all of them; which
    ones act on a given widget is the wearing widget's kind's affair,
    routed by the measured sets in ``_params.py``.
    """

    anchor: Anchor
    arrowcolor: Color
    arrowpadding: Padding
    arrowsize: PadValue
    background: Color
    bordercolor: Color
    borderwidth: PadValue
    compound: Compound
    darkcolor: Color
    embossed: int
    expand: Padding
    fieldbackground: Color
    focuscolor: Color
    focusthickness: PadValue
    font: FontSpec
    foreground: Color
    gripcount: PadValue
    image: ImageSpec
    indent: PadValue
    indicatorbackground: Color
    indicatorforeground: Color
    indicatormargin: Padding
    indicatormargins: Padding
    indicatorsize: PadValue
    insertcolor: Color
    insertwidth: PadValue
    justify: Justify
    labelmargins: Padding
    labeloutside: bool
    lightcolor: Color
    lowerbordercolor: Color
    mintabwidth: PadValue
    padding: Padding
    relief: Relief
    rowheight: PadValue
    sashthickness: PadValue
    selectbackground: Color
    selectborderwidth: PadValue
    selectforeground: Color
    shiftrelief: PadValue
    sliderlength: PadValue
    space: PadValue
    tabmargins: Padding
    tabposition: EdgePosition
    troughcolor: Color
    underline: int
    upperbordercolor: Color
    width: int
    wraplength: PadValue


VOCABULARY: Final[frozenset[str]] = frozenset(LookOptions.__optional_keys__)
"""Every styling option name a look accepts."""

STYLE_OPTION_NAMES: Final[dict[str, frozenset[str]]] = {
    "Sash": frozenset(SashStyleOptions.__optional_keys__),
    "TButton": frozenset(TButtonStyleOptions.__optional_keys__),
    "TCheckbutton": frozenset(TCheckbuttonStyleOptions.__optional_keys__),
    "TCombobox": frozenset(TComboboxStyleOptions.__optional_keys__),
    "TEntry": frozenset(TEntryStyleOptions.__optional_keys__),
    "TFrame": frozenset(TFrameStyleOptions.__optional_keys__),
    "TLabel": frozenset(TLabelStyleOptions.__optional_keys__),
    "TLabelframe": frozenset(TLabelframeStyleOptions.__optional_keys__),
    "TLabelframe.Label": frozenset(TLabelframeLabelStyleOptions.__optional_keys__),
    "TMenubutton": frozenset(TMenubuttonStyleOptions.__optional_keys__),
    "TNotebook": frozenset(TNotebookStyleOptions.__optional_keys__),
    "TNotebook.Tab": frozenset(TNotebookTabStyleOptions.__optional_keys__),
    "TPanedwindow": frozenset(TPanedwindowStyleOptions.__optional_keys__),
    "TProgressbar": frozenset(TProgressbarStyleOptions.__optional_keys__),
    "Horizontal.TProgressbar": frozenset(TProgressbarStyleOptions.__optional_keys__),
    "Vertical.TProgressbar": frozenset(TProgressbarStyleOptions.__optional_keys__),
    "TRadiobutton": frozenset(TCheckbuttonStyleOptions.__optional_keys__),
    "TScale": frozenset(TScaleStyleOptions.__optional_keys__),
    "Horizontal.TScale": frozenset(TScaleStyleOptions.__optional_keys__),
    "Vertical.TScale": frozenset(TScaleStyleOptions.__optional_keys__),
    "TScrollbar": frozenset(TScrollbarStyleOptions.__optional_keys__),
    "Horizontal.TScrollbar": frozenset(TScrollbarStyleOptions.__optional_keys__),
    "Vertical.TScrollbar": frozenset(TScrollbarStyleOptions.__optional_keys__),
    "TSeparator": frozenset(TSeparatorStyleOptions.__optional_keys__),
    "TSizegrip": frozenset(TSizegripStyleOptions.__optional_keys__),
    "TSpinbox": frozenset(TComboboxStyleOptions.__optional_keys__),
    "Treeview": frozenset(TreeviewStyleOptions.__optional_keys__),
    "Treeview.Cell": frozenset(TreeviewCellStyleOptions.__optional_keys__),
    "Treeview.Heading": frozenset(TreeviewHeadingStyleOptions.__optional_keys__),
    "Treeview.Item": frozenset(TreeviewItemStyleOptions.__optional_keys__),
}
"""Per style name, the measured set of options that act on it.

Derived from the ``*StyleOptions`` dicts in ``_params.py`` — the probe's
verdicts as routing data. What a look applies to a widget is the
intersection of what the look holds and this set for the widget's kind.
"""

_SITUATIONS: Final[tuple[str, ...]] = (
    "active",
    "disabled",
    "focus",
    "pressed",
    "readonly",
    "selected",
)
"""The widget situations a look styles separately, in write order."""

_PARTS: Final[dict[str, tuple[tuple[str, str], ...]]] = {
    "TLabelframe": (("caption", "TLabelframe.Label"),),
    "TNotebook": (("tab", "TNotebook.Tab"),),
    "TPanedwindow": (("sash", "Sash"),),
    "Treeview": (
        ("heading", "Treeview.Heading"),
        ("item", "Treeview.Item"),
        ("cell", "Treeview.Cell"),
    ),
}
"""Per wearable kind, its part sections and the style names they write."""

_ORIENTED: Final[frozenset[str]] = frozenset({"TProgressbar", "TScale", "TScrollbar"})
"""Kinds whose bare style has no layout: worn under the oriented spelling."""

_COUNTER = itertools.count(1)
"""Source of each look's unique style prefix."""


class LookState:
    """One layer of styling values: what holds in one situation.

    The base layer's values hold in every situation not overridden;
    a situation layer's values hold only there, written ahead of the
    base in the state map so they win exactly where they claim to.
    Every attribute of the vocabulary (:class:`LookOptions`) can be
    read and assigned; an unset option reads None, and assigning None
    unsets. A name outside the vocabulary is refused with a raise —
    a misspelling must not become a value nothing will ever read.
    """

    if TYPE_CHECKING:
        anchor: Anchor | None
        arrowcolor: Color | None
        arrowpadding: Padding | None
        arrowsize: PadValue | None
        background: Color | None
        bordercolor: Color | None
        borderwidth: PadValue | None
        compound: Compound | None
        darkcolor: Color | None
        embossed: int | None
        expand: Padding | None
        fieldbackground: Color | None
        focuscolor: Color | None
        focusthickness: PadValue | None
        font: FontSpec | None
        foreground: Color | None
        gripcount: PadValue | None
        image: ImageSpec | None
        indent: PadValue | None
        indicatorbackground: Color | None
        indicatorforeground: Color | None
        indicatormargin: Padding | None
        indicatormargins: Padding | None
        indicatorsize: PadValue | None
        insertcolor: Color | None
        insertwidth: PadValue | None
        justify: Justify | None
        labelmargins: Padding | None
        labeloutside: bool | None
        lightcolor: Color | None
        lowerbordercolor: Color | None
        mintabwidth: PadValue | None
        padding: Padding | None
        relief: Relief | None
        rowheight: PadValue | None
        sashthickness: PadValue | None
        selectbackground: Color | None
        selectborderwidth: PadValue | None
        selectforeground: Color | None
        shiftrelief: PadValue | None
        sliderlength: PadValue | None
        space: PadValue | None
        tabmargins: Padding | None
        tabposition: EdgePosition | None
        troughcolor: Color | None
        underline: int | None
        upperbordercolor: Color | None
        width: int | None
        wraplength: PadValue | None

    __slots__ = ("_look", "_values")

    def __init__(self, look: Look | None, /, **options: Unpack[LookOptions]) -> None:
        """Create the layer, seeded with ``options``.

        Args:
            look (Look | None): The owning look, notified on every
                change so worn widgets follow live; None while the
                look itself is under construction, when it owns
                itself.
            **options (Unpack[LookOptions]): Starting values, any of
                the vocabulary.
        """
        object.__setattr__(self, "_values", {})
        object.__setattr__(self, "_look", look)
        for name, value in options.items():
            setattr(self, name, value)

    def __setattr__(self, name: str, value: object) -> None:
        """Set a vocabulary option, or refuse a name that is not one.

        Raises:
            AttributeError: If ``name`` is not a styling option.
        """
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        if name not in VOCABULARY:
            raise AttributeError(f"{name!r} is not a styling option")
        held: dict[str, Any] = self._values
        if value is None:
            held.pop(name, None)
        else:
            held[name] = value
        owner: Look | None = self._look
        if owner is not None:
            owner._rewrite()

    def __getattr__(self, name: str) -> Any:
        """Answer a vocabulary option's held value, None while unset."""
        if name in VOCABULARY:
            values: dict[str, Any] = object.__getattribute__(self, "_values")
            return values.get(name)
        raise AttributeError(name)


class LookPart(LookState):
    """A dressable region: base values plus its situation layers.

    The look itself is one (the widget's main region), and each
    separately-dressed part of a compound widget is another — a tab
    bar's tabs, a table's headings. Situations hang off every part:
    ``look.tab.disabled.foreground`` is the tabs' text colour while
    the widget is disabled.
    """

    __slots__ = ("_sections",)

    def __init__(self, look: Look | None, /, **options: Unpack[LookOptions]) -> None:
        object.__setattr__(self, "_sections", {})
        super().__init__(look, **options)

    def _section(self, name: str, /) -> LookState:
        """The situation layer called ``name``, created on first touch."""
        held: dict[str, LookState] = self._sections
        section = held.get(name)
        if section is None:
            owner: Look | None = self._look
            section = held[name] = LookState(owner if owner is not None else None)
        return section

    @property
    def active(self) -> LookState:
        """Values holding while the pointer is over the widget."""
        return self._section("active")

    @property
    def disabled(self) -> LookState:
        """Values holding while the widget is disabled."""
        return self._section("disabled")

    @property
    def focus(self) -> LookState:
        """Values holding while the widget has keyboard focus."""
        return self._section("focus")

    @property
    def pressed(self) -> LookState:
        """Values holding while the widget is being pressed."""
        return self._section("pressed")

    @property
    def readonly(self) -> LookState:
        """Values holding while the widget is read-only."""
        return self._section("readonly")

    @property
    def selected(self) -> LookState:
        """Values holding while the widget is selected or ticked on."""
        return self._section("selected")


class Look(LookPart):
    """One shared appearance, worn by any number of themed widgets.

    Define values once — the whole vocabulary is accepted — and hand
    the look to widgets through their ``look`` property; each takes
    the subset measured to act on its own kind and ignores the rest,
    so one look keeps a bevy of different widgets consistent, and a
    look given to a single widget styles that widget alone. Editing a
    worn look repaints every wearer at once. Values hold in every
    situation unless a situation layer says otherwise, whatever the
    theme's own state maps would prefer — what you set is what you
    see.

    Parts of compound widgets are dressed through the part sections:
    :attr:`tab` (a tab bar's tabs), :attr:`heading`, :attr:`item` and
    :attr:`cell` (trees and tables), :attr:`caption` (a label frame's
    caption). :attr:`sash` is the one global part — Tk resolves every
    pane divider through a single style name, so the last look worn
    by any paned widget dresses all sashes on the interpreter.

    A look serves one Tk interpreter at a time, bound on first wear
    and rebound only after that interpreter dies, the transport rule
    observables follow.
    """

    __slots__ = ("_minted", "_prefix", "_style", "_written")

    def __init__(self, **options: Unpack[LookOptions]) -> None:
        """Create the look, seeded with base-layer ``options``.

        Args:
            **options (Unpack[LookOptions]): Starting values for the
                main region's base layer, any of the vocabulary.
        """
        object.__setattr__(self, "_prefix", f"Look{next(_COUNTER)}")
        object.__setattr__(self, "_style", None)
        object.__setattr__(self, "_minted", set())
        object.__setattr__(self, "_written", {})
        super().__init__(None, **options)
        object.__setattr__(self, "_look", self)

    def _part(self, name: str, /) -> LookPart:
        """The part section called ``name``, created on first touch."""
        held: dict[str, LookState] = self._sections
        section = held.get(name)
        if section is None:
            section = held[name] = LookPart(self)
        assert isinstance(section, LookPart)  # parts and situations share the cache, keys disjoint
        return section

    @property
    def tab(self) -> LookPart:
        """The tabs of a tab bar (a :class:`~tkfacade.TabFrame`'s)."""
        return self._part("tab")

    @property
    def heading(self) -> LookPart:
        """The column headings of a tree or table."""
        return self._part("heading")

    @property
    def item(self) -> LookPart:
        """The expand/collapse indicator region of a tree or table row."""
        return self._part("item")

    @property
    def cell(self) -> LookPart:
        """The cell region of a tree or table."""
        return self._part("cell")

    @property
    def caption(self) -> LookPart:
        """The caption of a label frame."""
        return self._part("caption")

    @property
    def sash(self) -> LookPart:
        """The divider between panes — Tk's one global part.

        Every paned widget on the interpreter reads the same style
        name for its sashes, so these values are not per-look in
        effect: the look most recently worn by any paned widget
        decides every sash.
        """
        return self._part("sash")

    # -----------
    # The wearing
    # -----------

    def _wear(self, widget: tk.Widget, /) -> str | None:
        """Dress ``widget``'s kind and answer the style name it should wear.

        Args:
            widget (tk.Widget): The themed Tk widget about to wear
                this look.

        Returns:
            The minted style name for the widget's kind, or None when
            the kind is not a themed one the measurements cover —
            nothing to dress, per the ruling that an incompatible
            setting simply does not apply.

        Raises:
            RuntimeError: If the look is already serving another live
                interpreter.
        """
        kind = widget.winfo_class()
        if kind not in STYLE_OPTION_NAMES:
            return None
        self._bind(widget)
        minted: set[str] = self._minted
        if kind not in minted:
            minted.add(kind)
            self._write(kind)
        if kind in _ORIENTED:
            orient = str(widget.cget("orient")).capitalize()
            return f"{self._prefix}.{orient}.{kind}"
        return f"{self._prefix}.{kind}"

    def _bind(self, widget: tk.Misc, /) -> None:
        """Bind to ``widget``'s interpreter, or refuse a second live one.

        Raises:
            RuntimeError: If the held interpreter is alive and is not
                ``widget``'s.
        """
        held: ttk.Style | None = self._style
        if held is not None:
            master = held.master
            if master.tk is widget.tk:
                return
            try:
                alive = bool(master.winfo_exists())
            except tk.TclError:
                alive = False
            if alive:
                raise RuntimeError("this look is already serving another interpreter")
            self._minted.clear()
            self._written.clear()
        object.__setattr__(self, "_style", ttk.Style(widget))

    def _rewrite(self) -> None:
        """Re-dress every minted kind after a value changes; wearers follow."""
        if self._style is None:
            return
        for kind in tuple(self._minted):
            self._write(kind)

    def _write(self, kind: str, /) -> None:
        """Write this look's state for one wearable kind, parts included."""
        self._write_style(f"{self._prefix}.{kind}", kind, self)
        if kind in _ORIENTED:
            for orient in ("Horizontal", "Vertical"):
                oriented = f"{orient}.{kind}"
                self._write_style(f"{self._prefix}.{oriented}", oriented, self)
        for section_name, sub in _PARTS.get(kind, ()):
            held: dict[str, LookState] = self._sections
            part = held.get(section_name)
            source = part if isinstance(part, LookPart) else _EMPTY_PART
            # Sash is Tk's one global name, written bare (`hazards/tkinter.md`, *Styling*)
            target = sub if sub == "Sash" else f"{self._prefix}.{sub}"
            self._write_style(target, sub, source)

    def _write_style(self, name: str, key: str, source: LookPart, /) -> None:
        """Write one style name from one part's layers, clearing what left.

        Every value rides the map layer: situation entries first, then
        a match-everything entry carrying the base value, so the base
        holds wherever no situation claims — including situations the
        theme's own maps would otherwise win. The base is also
        configured plainly, for any option consulted outside the map
        path. Options written before and cleared since are reset to
        the theme's own answer.
        """
        style: ttk.Style | None = self._style
        if style is None:
            return
        allowed = STYLE_OPTION_NAMES[key]
        base: dict[str, Any] = source._values
        sections: dict[str, LookState] = source._sections
        config: dict[str, Any] = {}
        maps: dict[str, list[tuple[str, Any]]] = {}
        for option in allowed:
            entries: list[tuple[str, Any]] = []
            for situation in _SITUATIONS:
                layer = sections.get(situation)
                if layer is not None and option in layer._values:
                    entries.append((situation, layer._values[option]))
            if option in base:
                config[option] = base[option]
                entries.append(("", base[option]))
            if entries:
                maps[option] = entries
        written: dict[str, frozenset[str]] = self._written
        previous = written.get(name, frozenset())
        current = frozenset(maps)
        for option in previous - current:
            config[option] = ""
            maps[option] = []
        if config:
            style.configure(name, **config)
        if maps:
            # cast: every value is a list of (state, value) pairs, the shape map's kwargs take
            style.map(name, **cast(dict[str, Any], maps))
        written[name] = current


_EMPTY_PART: Final[LookPart] = LookPart(None)
"""The stand-in written for a part the look never touched, clearing nothing."""
