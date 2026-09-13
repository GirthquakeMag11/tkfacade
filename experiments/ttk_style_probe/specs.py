"""What the probe renders, what it sets, and the states it tries.

Each :class:`Spec` names a style, says how to build a widget that shows it, and
fixes the size that widget is placed at. The size is fixed on purpose: an option
that changes the widget's requested size is caught by comparing requested sizes,
so the rendered box can stay a constant rectangle and be compared byte for byte.

Widgets are built with content that gives their options something to act on -- a
treeview with an open branch and a selection, a notebook with three tabs, a
scrollbar with a thumb. An option that has nothing to act on reads as inert, and
that is a fact about the probe rather than about ttk.
"""

from collections.abc import Callable
from tkinter import ttk

COLOURS = ["#ff00ff", "#00ff00"]
RELIEFS = ["sunken", "raised", "groove"]
PADDINGS: list[str | int] = ["18 18 18 18", 0]

#: Values to try per option, in order, until one changes the rendering. Two
#: differing values are given wherever a default might coincide with the first.
#: ``@PHOTO@`` stands for an image the probe creates against its own interpreter.
VALUES: dict[str, list[object]] = {
    # declared by an element of some layout in some theme
    "anchor": ["se", "nw"],
    "arrowcolor": COLOURS,
    "arrowpadding": [12, 0],
    "arrowsize": [30, 4],
    "background": COLOURS,
    "barsize": [60, 5],
    "bordercolor": COLOURS,
    "borderwidth": [8, 0],
    "compound": ["image", "right", "none"],
    "darkcolor": COLOURS,
    "default": ["active", "disabled", "normal"],
    "diameter": [30, 4],
    "direction": ["left", "above", "right"],
    "embossed": [1, 0],
    "fieldbackground": COLOURS,
    "focuscolor": COLOURS,
    "focusthickness": [6, 0],
    "font": ["Helvetica 24 bold", "Helvetica 6"],
    "foreground": COLOURS,
    "gripcount": [12, 0],
    "groovewidth": [14, 1],
    "handlepad": [20, 0],
    "handlesize": [20, 2],
    "highlightcolor": COLOURS,
    "highlightthickness": [8, 0],
    "image": ["@PHOTO@"],
    "indicatorbackground": COLOURS,
    "indicatorcolor": COLOURS,
    "indicatordiameter": [20, 3],
    "indicatorforeground": COLOURS,
    "indicatorheight": [24, 4],
    "indicatormargin": PADDINGS,
    "indicatormargins": PADDINGS,
    "indicatorrelief": RELIEFS,
    "indicatorsize": [24, 4],
    "indicatorwidth": [24, 4],
    "justify": ["right", "center"],
    "lightcolor": COLOURS,
    "lowerbordercolor": COLOURS,
    "orient": ["vertical", "horizontal"],
    "padding": PADDINGS,
    "pbarrelief": RELIEFS,
    "relief": RELIEFS,
    "rownumber": [3, 1],
    "sashpad": [8, 0],
    "sashrelief": RELIEFS,
    "sashthickness": [14, 2],
    "shadecolor": COLOURS,
    "shiftrelief": [6, 0],
    "sliderlength": [60, 10],
    "sliderrelief": RELIEFS,
    "sliderthickness": [30, 6],
    "space": [20, 0],
    "stipple": ["gray50", "gray25"],
    "text": ["ZZZZZZZZ", "i"],
    "thickness": [30, 3],
    "troughborderwidth": [8, 0],
    "troughcolor": COLOURS,
    "troughrelief": RELIEFS,
    "underline": [0, -1],
    "upperbordercolor": COLOURS,
    "width": [30, 2],
    "wraplength": [20, 0],
    # declared by no element anywhere, but read by some widget directly
    "expand": ["8 8 8 8", 0],
    "indent": [60, 4],
    "insertcolor": COLOURS,
    "insertwidth": [6, 1],
    "labelmargins": PADDINGS,
    "labeloutside": [1, 0],
    "mintabwidth": [140, 4],
    "postoffset": ["20 20 60 0", "0 0 0 0"],
    "rowheight": [40, 12],
    "selectbackground": COLOURS,
    "selectborderwidth": [6, 0],
    "selectforeground": COLOURS,
    "stripedbackground": COLOURS,
    "tabmargins": PADDINGS,
    "tabposition": ["se", "wn"],
}

#: States to put the widget in, tried in order. The plain state comes first
#: because almost every option that works, works there.
STATES: list[tuple[str, ...]] = [
    (),
    ("focus",),
    ("selected",),
    ("active",),
    ("pressed",),
    ("disabled",),
    ("readonly",),
    ("alternate",),
    ("invalid",),
]

#: Options that need an image beside the text before they can show themselves.
NEEDS_COMPOUND = {"space", "compound"}

#: Options that need more than one line of text before they can show themselves.
NEEDS_MULTILINE = {"justify", "wraplength"}

Build = Callable[[ttk.Widget, str], ttk.Widget]


class Spec:
    """One style to probe, and how to get a widget on screen that shows it.

    Attributes:
        style: The style name whose layout declares the options under test.
        build: Builds the widget, given a parent and a style name.
        size: The width and height the widget is placed at.
        sub: Suffix when the probe targets a sub-style, e.g. ``".Heading"``.
        states: Whether widget states are worth trying for this style.
        scope: ``"probe"`` when a per-widget style name reaches the options,
            ``"global"`` when only one fixed name does.
        configure_as: The style name the widget actually looks options up under,
            which is ``style`` for everything but the panedwindow sash.
        note: What is unusual about this style, for the results file.
    """

    def __init__(
        self,
        style: str,
        build: Build,
        size: tuple[int, int] = (240, 90),
        sub: str | None = None,
        states: bool = True,
        scope: str = "probe",
        note: str = "",
        configure_as: str | None = None,
    ) -> None:
        self.style = style
        self.build = build
        self.size = size
        self.sub = sub
        self.states = states
        self.scope = scope
        self.note = note
        self.configure_as = configure_as or style

    @property
    def widget_style(self) -> str:
        """The style name handed to the widget, which a sub-style hangs off."""
        return self.style[: -len(self.sub)] if self.sub else self.style


def _tree(parent: ttk.Widget, stylename: str) -> ttk.Widget:
    tree = ttk.Treeview(parent, columns=("a", "b"), style=stylename, height=5)
    tree.heading("#0", text="Name")
    tree.heading("a", text="A")
    tree.heading("b", text="B")
    for i in range(3):
        node = tree.insert("", "end", text=f"row {i}", values=(f"a{i}", f"b{i}"))
        tree.insert(node, "end", text=f"child {i}", values=("x", "y"))
    tree.item(tree.get_children()[0], open=True)  # so -indent has something to indent
    tree.selection_set(tree.get_children()[1])
    return tree


def _notebook(parent: ttk.Widget, stylename: str) -> ttk.Widget:
    notebook = ttk.Notebook(parent, style=stylename)
    for i in range(3):
        notebook.add(ttk.Frame(notebook), text=f"tab {i}")
    return notebook


def _paned(orient: str) -> Build:
    def build(parent: ttk.Widget, stylename: str) -> ttk.Widget:
        paned = ttk.Panedwindow(parent, orient=orient, style=stylename)
        paned.add(ttk.Label(paned, text="one"))
        paned.add(ttk.Label(paned, text="two"))
        return paned

    return build


def _labelframe(parent: ttk.Widget, stylename: str) -> ttk.Widget:
    frame = ttk.Labelframe(parent, text="Group", style=stylename)
    ttk.Label(frame, text="inside").pack(padx=10, pady=10)
    return frame


def _entry(parent: ttk.Widget, stylename: str) -> ttk.Widget:
    entry = ttk.Entry(parent, style=stylename)
    entry.insert(0, "entry text")
    entry.selection_range(0, 5)
    return entry


def _combo(parent: ttk.Widget, stylename: str) -> ttk.Widget:
    combo = ttk.Combobox(parent, style=stylename, values=["one", "two", "three"])
    combo.set("one")
    return combo


def _spin(parent: ttk.Widget, stylename: str) -> ttk.Widget:
    spin = ttk.Spinbox(parent, style=stylename, from_=0, to=10)
    spin.set(3)
    return spin


def _scrollbar(orient: str) -> Build:
    def build(parent: ttk.Widget, stylename: str) -> ttk.Widget:
        bar = ttk.Scrollbar(parent, orient=orient, style=stylename)
        bar.set(0.25, 0.6)  # without a thumb there is nothing to colour
        return bar

    return build


def _check(parent: ttk.Widget, stylename: str) -> ttk.Widget:
    box = ttk.Checkbutton(parent, text="Check", style=stylename)
    box.state(["!alternate"])  # a fresh checkbutton starts tri-state
    return box


def _radio(parent: ttk.Widget, stylename: str) -> ttk.Widget:
    button = ttk.Radiobutton(parent, text="Radio", style=stylename)
    button.state(["!alternate"])
    return button


_SASH_NOTE = "layout is <orient>.Sash, but options are looked up under 'Sash'"

#: Every style the probe covers, including the sub-styles of compound widgets.
SPECS: list[Spec] = [
    Spec("TButton", lambda p, s: ttk.Button(p, text="Button", style=s)),
    Spec("Toolbutton", lambda p, s: ttk.Button(p, text="Toolbutton", style=s)),
    Spec("TCheckbutton", _check),
    Spec("TRadiobutton", _radio),
    Spec("TMenubutton", lambda p, s: ttk.Menubutton(p, text="Menubutton", style=s)),
    Spec("TEntry", _entry, size=(240, 40)),
    Spec("TCombobox", _combo, size=(240, 40)),
    Spec("TSpinbox", _spin, size=(240, 40)),
    Spec("TFrame", lambda p, s: ttk.Frame(p, style=s)),
    Spec("TLabel", lambda p, s: ttk.Label(p, text="Label", style=s)),
    Spec("TLabelframe", _labelframe, size=(240, 120)),
    Spec("TLabelframe.Label", _labelframe, size=(240, 120), sub=".Label"),
    Spec("TNotebook", _notebook, size=(320, 160)),
    Spec("TNotebook.Tab", _notebook, size=(320, 160), sub=".Tab"),
    Spec("Horizontal.TPanedwindow", _paned("horizontal"), size=(320, 120)),
    Spec("Vertical.TPanedwindow", _paned("vertical"), size=(160, 200)),
    Spec(
        "Horizontal.Sash",
        _paned("horizontal"),
        size=(320, 120),
        scope="global",
        configure_as="Sash",
        note=_SASH_NOTE,
    ),
    Spec(
        "Vertical.Sash",
        _paned("vertical"),
        size=(160, 200),
        scope="global",
        configure_as="Sash",
        note=_SASH_NOTE,
    ),
    Spec(
        "Horizontal.TProgressbar",
        lambda p, s: ttk.Progressbar(p, orient="horizontal", style=s, value=50),
        size=(240, 40),
    ),
    Spec(
        "Vertical.TProgressbar",
        lambda p, s: ttk.Progressbar(p, orient="vertical", style=s, value=50),
        size=(40, 200),
    ),
    Spec(
        "Horizontal.TScale",
        lambda p, s: ttk.Scale(p, orient="horizontal", style=s, from_=0, to=100, value=40),
        size=(240, 50),
    ),
    Spec(
        "Vertical.TScale",
        lambda p, s: ttk.Scale(p, orient="vertical", style=s, from_=0, to=100, value=40),
        size=(50, 200),
    ),
    Spec("Horizontal.TScrollbar", _scrollbar("horizontal"), size=(240, 40)),
    Spec("Vertical.TScrollbar", _scrollbar("vertical"), size=(40, 200)),
    Spec(
        "Horizontal.TSeparator",
        lambda p, s: ttk.Separator(p, orient="horizontal", style=s),
        size=(240, 30),
    ),
    Spec(
        "Vertical.TSeparator",
        lambda p, s: ttk.Separator(p, orient="vertical", style=s),
        size=(30, 200),
    ),
    Spec("TSizegrip", lambda p, s: ttk.Sizegrip(p, style=s), size=(60, 60)),
    Spec("Treeview", _tree, size=(360, 220)),
    Spec("Treeview.Heading", _tree, size=(360, 220), sub=".Heading"),
    Spec("Treeview.Item", _tree, size=(360, 220), sub=".Item"),
    Spec("Treeview.Cell", _tree, size=(360, 220), sub=".Cell"),
    Spec("Treeview.Row", _tree, size=(360, 220), sub=".Row"),
]
