"""A one-window tour of tkfacade's widget suite, nothing of the toolkit but it.

Ten tabs — a form of small widgets, a page of choice widgets, a page of
numeric widgets, the split label, a text box, a list, a split view
holding a tree, a card stack, a media player, and a sortable table —
every one built and wired through the facade. Beyond being a live demo,
the file is the standing proof of the demonstration requirement: it
imports tkfacade and the stdlib alone, no tkinter, and
``tests/test_examples_gate.py`` holds it (and every example beside it)
to that.

Run it directly::

    uv run python examples/showcase.py
"""

import base64

import tkfacade

LOREM = (
    "A read-only box still takes focus, so its content can be selected\n"
    "and copied; only GUI editing is locked out. This one is editable:\n"
    "type away.\n"
)

COVERAGE = (
    ("Entry", "wrapped"),
    ("Frame", "wrapped"),
    ("Label", "split into TextLabel and ImageLabel"),
    ("Notebook", "wrapped as TabFrame"),
    ("Treeview", "wrapped as Tree and Table"),
    ("Button", "wrapped"),
    ("Checkbutton", "wrapped"),
    ("Scrollbar", "wrapped"),
    ("Scale", "wrapped as FloatScale and IntScale"),
    ("Combobox", "wrapped as Combobox and ChoiceBox"),
    ("Spinbox", "wrapped as FloatSpinbox, IntSpinbox and ChoiceSpinner"),
    ("Listbox", "wrapped over a themed Treeview"),
    ("LabelFrame", "wrapped"),
    ("PanedWindow", "wrapped as PanedFrame"),
    ("Separator", "wrapped"),
    ("Sizegrip", "wrapped as Window(sizegrip=True)"),
    ("Menubutton", "wrapped"),
    ("OptionMenu", "wrapped, seeded by a choice set"),
    ("Radiobutton", "wrapped as ChoiceButtons, the set the buttons compose"),
    ("LabeledScale", "ruled out; superseded by show_value"),
    ("Text", "wrapped as TextBox"),
    ("Menu", "wrapped as the menu family: Menubar, Menubutton, Submenu"),
    ("Progressbar", "wrapped as the two progress bars, split by what they count"),
    ("Message", "ruled out (2026-08-27); TextLabel's wraplength is the answer"),
    ("Canvas", "deferred to a future version by ruling (2026-08-27)"),
    ("ScrolledText", "ruled out; folds into TextBox, whose bars are the facade's own"),
)


_SAMPLE_ANIMATION = (
    # A four-frame 48x48 GIF, held as text so the showcase ships no media
    # files: the media page decodes it on demand and hands the bytes to
    # the player, which resolves bytes as an image by construction.
    "R0lGODlhMAAwAIEAAMg8PAAAAAAAAAAAACH/C05FVFNDQVBFMi4wAwEAAAAh+QQA"
    "GQAAACwAAAAAMAAwAAAITwABCBxIsKDBgwgTKlzIsKHDhxAjSpxIsaLFixgzatzI"
    "saPHjyBDihxJsqTJkyhTqlzJsqXLlzBjypxJs6bNmzhz6tzJs6fPn0CDCh2qMSAA"
    "IfkEARkAAQAsAAAAADAAMACBPKA8AAAAAAAAAAAACE8AAQgcSLCgwYMIEypcyLCh"
    "w4cQI0qcSLGixYsYM2rcyLGjx48gQ4ocSbKkyZMoU6pcybKly5cwY8qcSbOmzZs4"
    "c+rcybOnz59AgwodqjEgACH5BAEZAAEALAAAAAAwADAAgTxayAAAAAAAAAAAAAhP"
    "AAEIHEiwoMGDCBMqXMiwocOHECNKnEixosWLGDNq3Mixo8ePIEOKHEmypMmTKFOq"
    "XMmypcuXMGPKnEmzps2bOHPq3Mmzp8+fQIMKHaoxIAAh+QQBGQABACwAAAAAMAAw"
    "AIHctCgAAAAAAAAAAAAITwABCBxIsKDBgwgTKlzIsKHDhxAjSpxIsaLFixgzatzI"
    "saPHjyBDihxJsqTJkyhTqlzJsqXLlzBjypxJs6bNmzhz6tzJs6fPn0CDCh2qMSAA"
    "Ow=="
)


def build_form_page(
    page: tkfacade.Frame, on_top: tkfacade.ObservableBool, clicks: tkfacade.ObservableInt
) -> None:
    """Fill one page with the text inputs, a watched name, and a click tally.

    The name entry and the greeting under it share one observable, so
    typing re-greets without a single callback registered on the entry;
    the counter label handles its own left-clicks through the facade's
    bind and shares ``clicks`` with the Count buttons; the checkbutton
    shares ``on_top`` with the Actions menubutton and the File menu's
    row, one tick drawn in several places; and the sound group is a
    label frame whose caption is a widget rather than a string, the one
    place a plain caption is not all a frame takes.

    Args:
        page (tkfacade.Frame): The tab page to build into.
        on_top (tkfacade.ObservableBool): The tick shared with the
            Actions menubutton and the File menu.
        clicks (tkfacade.ObservableInt): The tally shared with the
            Count buttons and the Actions menubutton.
    """
    page.padding = 12
    tkfacade.TextLabel(page, text="The form widgets, imperative style:").grid(
        row=0, column=0, sticky="w", pady=(0, 8)
    )
    name = tkfacade.ObservableStr("Ada")
    tkfacade.TitleEntry(page, title="Name", text=name, arrangement="left-right").grid(
        row=1, column=0, sticky="w", pady=2
    )
    tkfacade.Entry(page, "A plain entry", width=32).grid(row=2, column=0, sticky="w", pady=2)
    tkfacade.Entry(page, "read-only, still copyable", read_only=True, width=32).grid(
        row=3, column=0, sticky="w", pady=2
    )
    greeting = tkfacade.TextLabel(page, text="")
    greeting.grid(row=4, column=0, sticky="w", pady=(10, 2))

    def greet(value: str) -> None:
        greeting.text = f"Hello, {value}!" if value else "Hello?"

    name.watch(greet)
    counter = tkfacade.TextLabel(page, text="")
    counter.grid(row=5, column=0, sticky="w", pady=2)
    counter.bind(
        tkfacade.Press(tkfacade.MouseButton.LEFT),
        lambda _event: setattr(clicks, "value", clicks.value + 1),
    )

    def recount(count: int) -> None:
        counter.text = f"clicked {count} times — click me"

    clicks.watch(recount)
    tkfacade.Button(
        page, "Count one more", command=lambda: setattr(clicks, "value", clicks.value + 1)
    ).grid(row=6, column=0, sticky="w", pady=2)
    tkfacade.Checkbutton(
        page, "Keep on top (one tick with the Actions menu's)", checked=on_top
    ).grid(row=7, column=0, sticky="w", pady=(10, 2))
    sound_on = tkfacade.Checkbutton(page, "Sound", checked=True)
    sound = tkfacade.LabelFrame(page, caption=sound_on, padding=8)
    sound.grid(row=8, column=0, sticky="w", pady=(10, 2))
    tkfacade.TextLabel(sound, text="A group whose caption is a widget, not a string.").grid(
        row=0, column=0, sticky="w"
    )


def build_choices_page(
    page: tkfacade.Frame, on_top: tkfacade.ObservableBool, clicks: tkfacade.ObservableInt
) -> None:
    """Fill one page with one value chosen five ways, and a menu of actions.

    One size is chosen five ways — the choice box, the bank of
    radiobuttons under it, the option menu and the spinner beside them,
    and the Actions menubutton's Text size rows all share a single
    observable, so picking anywhere moves everywhere. The whole size
    family wears one shared accent look. The two dropdowns below it are
    the pair ttk keeps in one class: the choice box holds one of its
    options and nothing else, the combobox suggests and lets anything
    be typed. The Actions menubutton fills its own menu through the
    imperative facade; its count row shares ``clicks`` with the Form
    page and its tick shares ``on_top``.

    Args:
        page (tkfacade.Frame): The tab page to build into.
        on_top (tkfacade.ObservableBool): The tick shared with the Form
            page's checkbutton.
        clicks (tkfacade.ObservableInt): The tally shared with the Form
            page's counter.
    """
    page.padding = 12
    tkfacade.TextLabel(page, text="One value, chosen five ways at once:").grid(
        row=0, column=0, sticky="w", pady=(0, 8)
    )
    size = tkfacade.ObservableStr("Medium")
    accent = tkfacade.Look(foreground="#1a5fb4", arrowcolor="#1a5fb4")
    accent.disabled.foreground = "#93b5d6"
    tkfacade.ChoiceBox(page, ("Small", "Medium", "Large"), chosen=size, width=12, look=accent).grid(
        row=1, column=0, sticky="w", pady=2
    )
    tkfacade.ChoiceButtons(
        page, ("Small", "Medium", "Large"), chosen=size, orient="horizontal", look=accent
    ).grid(row=2, column=0, sticky="w", pady=2)
    tkfacade.OptionMenu(
        page, ("Small", "Medium", "Large"), chosen=size, width=10, look=accent
    ).grid(row=3, column=0, sticky="w", pady=2)
    tkfacade.ChoiceSpinner(
        page, ("Small", "Medium", "Large"), chosen=size, width=10, look=accent
    ).grid(row=4, column=0, sticky="w", pady=2)
    tkfacade.Combobox(page, "monospace", suggestions=("monospace", "serif", "sans"), width=18).grid(
        row=5, column=0, sticky="w", pady=2
    )
    tkfacade.IntSpinbox(page, minimum=1, maximum=99, value=3, width=6).grid(
        row=6, column=0, sticky="w", pady=2
    )
    actions = tkfacade.Menubutton(page, "Actions")
    actions.grid(row=7, column=0, sticky="w", pady=(10, 2))
    actions.insert_command(
        "Count one more", command=lambda: setattr(clicks, "value", clicks.value + 1)
    )
    actions.insert_checkbox("Keep on top (the same tick again)", checked=on_top)
    actions.insert_separator()
    sizes = actions.insert_submenu("Text size")
    sizes.insert_choices(("Small", "Medium", "Large"), chosen=size)


def build_values_page(page: tkfacade.Frame) -> None:
    """Fill one page with the numeric widgets and the progress bars.

    The gain scale and the spinbox after it share one float, so dragging
    and typing are two hands on one value; the volume scale shows its own
    value beside itself, the capability tkinter keeps in a separate
    ``LabeledScale`` class this library rules out; and the two progress
    bars below count two things — a percentage, or items toward a
    maximum — the item bar's tally read back as text beside it.

    Args:
        page (tkfacade.Frame): The tab page to build into.
    """
    page.padding = 12
    tkfacade.TextLabel(page, text="The numeric widgets:").grid(
        row=0, column=0, sticky="w", pady=(0, 8)
    )
    gain = tkfacade.ObservableFloat(2.5)
    tkfacade.FloatScale(
        page,
        start=0.0,
        end=10.0,
        value=gain,
        length=200,
        show_value=True,
        arrangement="left-right",
        value_format="gain {:.1f}",
    ).grid(row=1, column=0, sticky="w", pady=(10, 2))
    tkfacade.FloatSpinbox(page, minimum=0.0, maximum=10.0, value=gain, step=0.5, width=6).grid(
        row=2, column=0, sticky="w", pady=2
    )
    volume = tkfacade.IntScale(
        page,
        start=0,
        end=11,
        value=7,
        length=200,
        show_value=True,
        arrangement="left-right",
        value_format="volume {}",
    )
    volume.grid(row=3, column=0, sticky="w", pady=(10, 2))
    percent = tkfacade.PercentageBasedProgressBar(
        page, orient="horizontal", length=240, current=40.0
    )
    percent.grid(row=4, column=0, sticky="w", pady=(10, 2))
    items = tkfacade.ItemBasedProgressBar(
        page, orient="horizontal", length=240, maximum=8, current=3
    )
    items.grid(row=5, column=0, sticky="w", pady=2)
    tkfacade.TextLabel(page, text=f"{items.current} of {items.maximum} items done").grid(
        row=6, column=0, sticky="w"
    )


def build_labels_page(page: tkfacade.Frame) -> None:
    """Fill one page with the split Label, demonstrated live.

    A fixed-width ``TextLabel`` whose ``justify`` a button cycles through
    left, centre and right — the text visibly moves inside the label,
    which is the behavior the split exists to make honest — and an
    ``ImageLabel`` over the sample animation, driven by its own
    play/pause/stop.

    Args:
        page (tkfacade.Frame): The tab page to build into.
    """
    page.padding = 12
    tkfacade.TextLabel(page, text="The split Label, in both halves:").grid(
        row=0, column=0, sticky="w", pady=(0, 8)
    )
    justify_demo = tkfacade.TextLabel(page, text="watch this text move", width=24, justify="left")
    justify_demo.grid(row=1, column=0, sticky="w", pady=(12, 2))
    justify_readout = tkfacade.TextLabel(page, text="justify = left")
    justify_readout.grid(row=3, column=0, sticky="w", pady=(0, 2))
    justifies: tuple[tkfacade.Justify, ...] = ("left", "center", "right")
    justify_step: list[int] = [0]

    def cycle_justify() -> None:
        justify_step[0] = (justify_step[0] + 1) % len(justifies)
        justify_demo.justify = justifies[justify_step[0]]
        justify_readout.text = (
            f"justify = {justify_demo.justify!r} (anchor {justify_demo.anchor!r})"
        )

    tkfacade.Button(page, "Cycle justify", command=cycle_justify).grid(
        row=2, column=0, sticky="w", pady=2
    )
    sample = tkfacade.ImageLabel(page, image=base64.b64decode(_SAMPLE_ANIMATION))
    sample.grid(row=4, column=0, sticky="w", pady=(12, 2))
    sample_controls = tkfacade.Frame(page)
    sample_controls.grid(row=5, column=0, sticky="w", pady=(0, 2))
    tkfacade.Button(sample_controls, "Play image", command=sample.play).grid(
        row=0, column=0, padx=(0, 6)
    )
    tkfacade.Button(sample_controls, "Pause image", command=sample.pause).grid(
        row=0, column=1, padx=(0, 6)
    )
    tkfacade.Button(sample_controls, "Stop image", command=sample.stop).grid(row=0, column=2)


def build_text_page(page: tkfacade.Frame) -> None:
    """Fill one page with a scrolling text box and buttons that navigate it.

    The box owns its scrollbar, so nothing here wires one — the spec
    says what kind of bar to build, here an auto-hiding one on the
    left, the ordinary layout in right-to-left interfaces. The bar's
    facet answers the same settings live afterwards, but nothing here
    needs it: the buttons navigate the box itself, which is what a
    scrollable widget offers — four directions, and no mention of the
    bars that also happen to do it. A separator rules the two apart,
    which is the whole of what a separator is for.

    Args:
        page (tkfacade.Frame): The tab page to build into.
    """
    box = tkfacade.TextBox(
        page,
        LOREM,
        width=64,
        height=12,
        vertical_scrollbar=tkfacade.ScrollbarSpec(auto_hide=True, placement="left"),
    )
    box.grid(row=0, column=0, sticky="nsew")
    page.grid_rowconfigure(0, weight=1)
    page.grid_columnconfigure(0, weight=1)
    tkfacade.Separator(page).grid(row=1, column=0, sticky="ew", pady=(8, 0))
    buttons = tkfacade.Frame(page)
    buttons.grid(row=2, column=0, sticky="w", pady=(6, 0))
    tkfacade.Button(buttons, "Page up", command=lambda: box.scroll_up(1, unit="pages")).grid(
        row=0, column=0, padx=(0, 6)
    )
    tkfacade.Button(buttons, "Page down", command=lambda: box.scroll_down(1, unit="pages")).grid(
        row=0, column=1, padx=(0, 6)
    )
    tkfacade.Button(buttons, "Back to the top", command=lambda: box.scroll_to(y=0.0)).grid(
        row=0, column=2
    )


def build_list_page(page: tkfacade.Frame) -> None:
    """Fill one page with a list of strings, read as a Python sequence.

    The list is a themed tree underneath, because the classic listbox
    takes no ttk styling; what a caller sees is a MutableSequence, so
    the buttons below it append and drop with ordinary list methods
    rather than a widget vocabulary. The tally underneath stays live
    by subscribing to the list's selection event.

    Args:
        page (tkfacade.Frame): The tab page to build into.
    """
    items = tkfacade.Listbox(page, ("alpha", "beta", "gamma"), height=8)
    items.grid(row=0, column=0, sticky="nsew")
    page.grid_rowconfigure(0, weight=1)
    page.grid_columnconfigure(0, weight=1)
    counter = tkfacade.TextLabel(page, text="")
    counter.grid(row=2, column=0, sticky="w", pady=(6, 0))

    def restate() -> None:
        chosen = items.selected_items or ("(none)",)
        counter.text = f"{len(items)} items; selected {', '.join(chosen)}"

    def add_one() -> None:
        items.append(f"item {len(items)}")
        restate()

    def drop_last() -> None:
        if items:
            items.pop()
        restate()

    buttons = tkfacade.Frame(page)
    buttons.grid(row=1, column=0, sticky="w", pady=(6, 0))
    tkfacade.Button(buttons, "Add one", command=add_one).grid(row=0, column=0, padx=(0, 6))
    tkfacade.Button(buttons, "Drop the last", command=drop_last).grid(row=0, column=1, padx=(0, 6))
    items.bind(tkfacade.Virtual(tkfacade.VirtualEvent.TREEVIEW_SELECT), lambda _event: restate())
    restate()


def build_split_page(page: tkfacade.Frame) -> None:
    """Fill one page with two panes the user can resize against each other.

    The split makes each pane and hands it back to fill, so nothing
    here places one — which is what stops the two footguns tkinter
    leaves open, a pane that is not a child and a pane gridded on top
    of the pane management. The left pane holds the hierarchical tree —
    rows nested under rows, the shape the Table page flattens into
    records — with the tree column shown and no value columns at all.

    Args:
        page (tkfacade.Frame): The tab page to build into.
    """
    split = tkfacade.PanedFrame(page, width=600, height=360)
    split.grid(row=0, column=0, sticky="nsew")
    page.grid_rowconfigure(0, weight=1)
    page.grid_columnconfigure(0, weight=1)

    left = split.add("left", weight=1)
    tkfacade.TextLabel(left, text="Drag the sash between these panes.").grid(
        row=0, column=0, sticky="nw", padx=6, pady=6
    )
    outline = tkfacade.Tree(left, show_tree_column=True, show_column_headings=False, height=10)
    outline.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
    left.grid_rowconfigure(1, weight=1)
    left.grid_columnconfigure(0, weight=1)
    for chapter in ("One", "Two"):
        row = outline.insert(text=f"Chapter {chapter}", is_open=True)
        for section in ("a", "b"):
            leaf = outline.insert(text=f"Section {chapter}.{section}", parent=row)
            outline.insert(text="a nested note", parent=leaf)
    right = split.add("right", weight=2)
    notes = tkfacade.TextBox(right, "This pane has twice the weight of its neighbour.", height=8)
    notes.grid(row=0, column=0, sticky="nsew")
    right.grid_rowconfigure(0, weight=1)
    right.grid_columnconfigure(0, weight=1)


def build_table_page(page: tkfacade.Frame) -> None:
    """Fill one page with a click-to-sort table of the coverage roster.

    Args:
        page (tkfacade.Frame): The tab page to build into.
    """
    table = tkfacade.Table(
        page,
        columns=(
            tkfacade.TreeColumnSpec(name="widget"),
            tkfacade.TreeColumnSpec(name="standing"),
        ),
        height=10,
    )
    for widget, standing in COVERAGE:
        table.insert(widget=widget, standing=standing)
    table.grid(row=0, column=0, sticky="nsew")
    page.grid_rowconfigure(0, weight=1)
    page.grid_columnconfigure(0, weight=1)


def build_stack_page(page: tkfacade.Frame) -> None:
    """Fill one page with a card stack shown one card at a time.

    The stack owns which card is mapped; the bank of buttons above it
    drives that through its own chosen observable — a watch on the
    shared value calls ``show``, so switching cards is the same wiring
    as choosing a size on the form page, pointed at a container.

    Args:
        page (tkfacade.Frame): The tab page to build into.
    """
    cards = ("first", "second", "third")
    chooser = tkfacade.ChoiceButtons(page, cards, chosen="first", orient="horizontal")
    chooser.grid(row=0, column=0, sticky="w", pady=(0, 6))
    stack = tkfacade.StackFrame(page, relief="groove")
    stack.grid(row=1, column=0, sticky="nsew")
    page.grid_rowconfigure(1, weight=1)
    page.grid_columnconfigure(0, weight=1)
    for key in cards:
        card = stack.add(key)
        card.padding = 12
        tkfacade.TextLabel(card, text=f"The {key} card. Its siblings share this cell.").grid(
            row=0, column=0, sticky="nw"
        )
    chooser.chosen_observable.watch(stack.show)


def build_media_page(page: tkfacade.Frame) -> None:
    """Fill one page with the media player and two ways to feed it.

    The player is both displays and the bar as one widget: each source
    is resolved to an image or a video and seated on that medium's
    display, and the video half — libmpv with it — is not built until
    a video source arrives, so this page opens on any machine. The
    sample button plays the animation embedded above as text; the
    entry takes any path or URL on this machine and plays whatever it
    resolves to.

    Args:
        page (tkfacade.Frame): The tab page to build into.
    """
    player = tkfacade.MediaPlayer(page, width=480, height=240)
    player.grid(row=0, column=0, sticky="nsew")
    page.grid_rowconfigure(0, weight=1)
    page.grid_columnconfigure(0, weight=1)
    feeds = tkfacade.Frame(page)
    feeds.grid(row=1, column=0, sticky="ew", pady=(6, 0))
    tkfacade.Button(
        feeds,
        "Play the sample animation",
        command=lambda: player.play(base64.b64decode(_SAMPLE_ANIMATION)),
    ).grid(row=0, column=0, padx=(0, 12))
    source = tkfacade.Entry(feeds, width=36)
    source.grid(row=0, column=1, padx=(0, 6))
    tkfacade.Button(
        feeds,
        "Play this path or URL",
        command=lambda: player.play(source.text) if source.text else None,
    ).grid(row=0, column=2)


def census(window: tkfacade.Window) -> str:
    """Count the wrappers in the window by walking the facade's own tree.

    Traversal through the facade alone: each widget's ``grid_slaves``,
    ``pack_slaves`` and ``place_slaves`` answer wrappers, and the
    containers whose pages ride their own managers — the tab stack and
    the split view — hand theirs back through their mapping faces. The
    walk names no tkinter type and never meets the composites'
    internals: what the facade did not build, it does not name.

    Args:
        window (tkfacade.Window): The window whose tree is walked.

    Returns:
        A one-line census, wrappers counted by kind.
    """
    counts: dict[str, int] = {}
    seen: set[int] = set()
    pending = [*window.grid_slaves(), *window.pack_slaves(), *window.place_slaves()]
    while pending:
        widget = pending.pop()
        if id(widget) in seen:
            continue
        seen.add(id(widget))
        kind = type(widget).__name__
        counts[kind] = counts.get(kind, 0) + 1
        pending.extend((*widget.grid_slaves(), *widget.pack_slaves(), *widget.place_slaves()))
        if isinstance(widget, (tkfacade.AbstractMultiFrame, tkfacade.PanedFrame)):
            pending.extend(widget.values())
    return f"{sum(counts.values())} wrappers of {len(counts)} kinds"


def build_menubar(
    bar: tkfacade.Menubar, window: tkfacade.Window, on_top: tkfacade.ObservableBool
) -> None:
    """Fill the window's top row with a File menu.

    The bar takes no command and no separator of its own — a command in
    a top row is indistinguishable from a menu, and a rule there draws
    nothing — so both sit inside the File menu, an ordinary menu that
    takes them. "Census" is a command: it walks the window's own widget
    tree through the facade and puts the count in the title.

    The keep-on-top row wears a real accelerator: a chord from the
    root's input observer, whose derived caption is the drawn text —
    press Ctrl+T anywhere in the window and the row invokes, toggling
    the tick every one of its four surfaces shares.

    "Save as..." posts the library's own file dialog — Tk's design
    recreated on the Dialog foundation — and puts the chosen path in
    the title; nothing is written.

    Args:
        bar (tkfacade.Menubar): The window's menu bar.
        window (tkfacade.Window): The window the census walks.
        on_top (tkfacade.ObservableBool): The tick shared with the form
            page's checkbutton and the Actions menubutton.
    """
    file_menu = bar.insert_submenu("File")
    keep = file_menu.insert_checkbox("Keep on top (the same tick a fourth time)", checked=on_top)
    keep.chord = tkfacade.get_root().inputs.chord("Control", "t")
    file_menu.insert_separator()
    recent = file_menu.insert_submenu("Recent")
    recent.insert_command("notes.txt")
    recent.insert_command("notes.txt")
    file_menu.insert_separator()

    def save_somewhere() -> None:
        chosen = tkfacade.dialog.file_save(
            window,
            filters=(tkfacade.dialog.FileFilter("Text", ("*.txt", "*.md")),),
            default_extension="txt",
        )
        window.title = f"tkfacade showcase — save to {chosen}" if chosen else "tkfacade showcase"

    def open_something() -> None:
        chosen = tkfacade.dialog.file_open(window)
        window.title = f"tkfacade showcase — open {chosen}" if chosen else "tkfacade showcase"

    def choose_folder() -> None:
        chosen = tkfacade.dialog.directory_open(window)
        window.title = f"tkfacade showcase — folder {chosen}" if chosen else "tkfacade showcase"

    # ASCII dots, not U+2026: the ellipsis rendered as a missing-glyph
    # box on some machines.
    def take_a_note() -> None:
        noted = tkfacade.dialog.textbox(window, title="Note", message="What's on your mind?")
        window.title = (
            f"tkfacade showcase — noted {len(noted)} chars"
            if noted is not None
            else "tkfacade showcase"
        )

    file_menu.insert_command("Open...", command=open_something)
    file_menu.insert_command("Save as...", command=save_somewhere)
    file_menu.insert_command("Choose folder...", command=choose_folder)

    def share_details() -> None:
        given = tkfacade.dialog.data_fields(
            window,
            title="Details",
            message="Who is running the showcase?",
            fields=(tkfacade.dialog.DataField("Name"), tkfacade.dialog.DataField("Email")),
        )
        window.title = (
            f"tkfacade showcase — hello {given['Name'] or 'stranger'}"
            if given is not None
            else "tkfacade showcase"
        )

    def about() -> None:
        tkfacade.dialog.message(
            window,
            "Every widget the library offers, in one window.\nNothing here imports tkinter.",
            title="About the showcase",
        )

    def quit() -> None:
        if tkfacade.dialog.confirm(window, "Exit the tkfacade showcase?"):
            window.destroy()

    file_menu.insert_command("Note...", command=take_a_note)
    file_menu.insert_command("Details...", command=share_details)
    file_menu.insert_separator()
    file_menu.insert_command("About...", command=about)
    file_menu.insert_separator()
    file_menu.insert_command("Quit", command=quit)
    file_menu.insert_command(
        "Census", command=lambda: setattr(window, "title", f"tkfacade showcase — {census(window)}")
    )


def build(window: tkfacade.Window) -> None:
    """Build the whole showcase into ``window``.

    Args:
        window (tkfacade.Window): The window to build into.
    """
    on_top = tkfacade.ObservableBool(False)
    clicks = tkfacade.ObservableInt(0)
    if window.menubar is not None:
        build_menubar(window.menubar, window, on_top)
    tabs = tkfacade.TabFrame(window)
    tabs.grid(row=0, column=0, sticky="nsew")
    window.grid_rowconfigure(0, weight=1)
    window.grid_columnconfigure(0, weight=1)
    build_form_page(tabs.add("form", title="Form"), on_top, clicks)
    build_choices_page(tabs.add("choices", title="Choices"), on_top, clicks)
    build_values_page(tabs.add("values", title="Values"))
    build_labels_page(tabs.add("labels", title="Labels"))
    build_text_page(tabs.add("text", title="Text"))
    build_list_page(tabs.add("list", title="List"))
    build_split_page(tabs.add("split", title="Split"))
    build_stack_page(tabs.add("stack", title="Stack"))
    build_media_page(tabs.add("media", title="Media"))
    build_table_page(tabs.add("table", title="Table"))


def main() -> None:
    """Open the showcase window and run it until it is closed."""
    window = tkfacade.Window(
        title="tkfacade showcase", width=720, height=520, sizegrip=True, menubar=True
    )
    build(window)
    window.run_mainloop()


if __name__ == "__main__":
    main()
