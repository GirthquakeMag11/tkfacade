"""Re-check every rule the ttk style options note states, one test each.

Run with::

    DISPLAY=:99 python -m experiments.ttk_style_probe.rules /tmp/ttkfb/Xvfb_screen0

The sweep in :mod:`~experiments.ttk_style_probe.probe` produces the per-widget
tables. The claims around those tables -- how a style name resolves, what beats
what, which things a style cannot reach at all -- are each pinned by one check
here, so a different Tk build or platform can be held against them without
re-reading anything. Every check prints its verdict, and the exit status is the
number that failed.

The expectations are those of Tk 8.6.14 under X11. A failure is a finding, not
necessarily a fault: it means that build does not behave the way the note says.
"""

import shutil
import subprocess
import sys
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from .capture import Framebuffer, count_diff

SKIP = "skip"


class Bench:
    """A Tk interpreter, a mapped toplevel, and the pointer out of the way."""

    def __init__(self, framebuffer: Framebuffer, theme: str = "clam") -> None:
        self.framebuffer = framebuffer
        self.root = tk.Tk()
        self.root.geometry(f"{framebuffer.width}x{framebuffer.height}+0+0")
        self.root.update()
        self.style = ttk.Style(self.root)
        self.style.theme_use(theme)
        self.park()

    def park(self) -> None:
        self.root.event_generate(
            "<Motion>", warp=True, x=self.framebuffer.width - 2, y=self.framebuffer.height - 2
        )
        self.sync()

    def sync(self) -> None:
        self.root.update()
        self.root.winfo_pointerx()

    def pixels(self, widget: tk.Widget) -> bytes:
        return self.framebuffer.region(
            widget.winfo_rootx(), widget.winfo_rooty(), widget.winfo_width(), widget.winfo_height()
        )

    def shot(self, build: Callable[[], tk.Widget], size: tuple[int, int] = (240, 90)) -> bytes:
        """Build a widget, place it, grab it, and take it away again."""
        widget = build()
        widget.place(x=20, y=20, width=size[0], height=size[1])
        self.sync()
        out = self.pixels(widget)
        widget.destroy()
        return out

    def close(self) -> None:
        self.root.destroy()


def check_style_accepts_anything(bench: Bench) -> tuple[bool, str]:
    """ttk.Style stores option names it has no use for, and hands them back."""
    bench.style.configure("Nonsense.TButton", nonsenseoption="hello")
    stored = bench.style.lookup("Nonsense.TButton", "nonsenseoption")
    drawn = bench.shot(lambda: ttk.Button(bench.root, text="B"))
    styled = bench.shot(lambda: ttk.Button(bench.root, text="B", style="Nonsense.TButton"))
    return stored == "hello" and drawn == styled, f"lookup gave {stored!r}, rendering unchanged"


def check_framebuffer_matches_xwd(bench: Bench) -> tuple[bool | str, str]:
    """The memory-mapped read agrees with xwd, which is what makes it usable."""
    if not shutil.which("xwd"):
        return SKIP, "xwd is not installed"
    frame = ttk.Frame(bench.root, style="TFrame")
    frame.place(x=0, y=0, width=200, height=100)
    bench.sync()
    dumped = subprocess.run(["xwd", "-root", "-silent"], capture_output=True, check=True).stdout
    mapped = bench.framebuffer.grab()
    frame.destroy()
    return dumped[-len(mapped) :] == mapped, f"{len(mapped)} bytes compared"


def check_name_resolution_strips_prefixes(bench: Bench) -> tuple[bool, str]:
    """A style name falls back by dropping leading components until one matches."""
    derived = bench.style.layout("Danger.TButton")
    plain = bench.style.layout("TButton")
    try:
        bench.style.layout("Danger")
    except tk.TclError:
        unknown_raises = True
    else:
        unknown_raises = False
    return derived == plain and unknown_raises, "Danger.TButton resolved, Danger did not"


def check_orientation_prefix_falls_back(bench: Bench) -> tuple[bool, str]:
    """A bare TProgressbar has no layout, and configuring it still reaches one."""
    try:
        bench.style.layout("TProgressbar")
    except tk.TclError:
        has_layout = False
    else:
        has_layout = True

    def build() -> tk.Widget:
        return ttk.Progressbar(bench.root, orient="horizontal", value=50)

    before = bench.shot(build, (240, 40))
    bench.style.configure("TProgressbar", background="#ff00ff", troughcolor="#00ff00")
    after = bench.shot(build, (240, 40))
    changed = count_diff(before, after)
    return not has_layout and changed > 0, f"no layout of its own, {changed} bytes changed"


def check_sublayouts_hang_off_widget_style(bench: Bench) -> tuple[bool, str]:
    """A treeview under Wide.Treeview takes headings from Wide.Treeview.Heading."""

    def build(name: str) -> Callable[[], tk.Widget]:
        def make() -> tk.Widget:
            tree = ttk.Treeview(bench.root, columns=("a",), style=name, height=4)
            tree.heading("#0", text="Name")
            tree.heading("a", text="A")
            tree.insert("", "end", text="row", values=("v",))
            return tree

        return make

    before = bench.shot(build("Wide.Treeview"), (340, 160))
    bench.style.configure("Wide.Treeview.Heading", background="#ff00ff")
    after = bench.shot(build("Wide.Treeview"), (340, 160))
    changed = count_diff(before, after)
    return changed > 0, f"{changed} bytes changed in the heading row"


def check_sash_is_looked_up_as_sash(bench: Bench) -> tuple[bool, str]:
    """The sash reads 'Sash', not the Horizontal.Sash name its layout is under."""

    def build() -> tk.Widget:
        paned = ttk.Panedwindow(bench.root, orient="horizontal")
        paned.add(ttk.Label(paned, text="left"))
        paned.add(ttk.Label(paned, text="right"))
        return paned

    before = bench.shot(build, (400, 120))
    bench.style.configure("Horizontal.Sash", sashthickness=30, gripcount=30)
    oriented = bench.shot(build, (400, 120))
    bench.style.configure("Sash", sashthickness=30, gripcount=30)
    bare = bench.shot(build, (400, 120))
    return (
        before == oriented and bare != before,
        f"Horizontal.Sash changed {count_diff(before, oriented)} bytes,"
        f" Sash changed {count_diff(before, bare)}",
    )


def check_map_beats_configure(bench: Bench) -> tuple[bool, str]:
    """A map on the root style overrides a configure on a far more specific one."""
    root_map = bench.style.map(".", "foreground")
    bench.style.configure("Quiet.TLabel", foreground="#ff00ff")
    bench.style.map("Mapped.TLabel", foreground=[("disabled", "#ff00ff")])

    def build(name: str, state: str | None) -> Callable[[], tk.Widget]:
        def make() -> tk.Widget:
            label = (
                ttk.Label(bench.root, text="Label", style=name)
                if name
                else (ttk.Label(bench.root, text="Label"))
            )
            if state:
                label.state([state])
            return label

        return make

    plain_normal = bench.shot(build("", None))
    plain_off = bench.shot(build("", "disabled"))
    configured_normal = bench.shot(build("Quiet.TLabel", None))
    configured_off = bench.shot(build("Quiet.TLabel", "disabled"))
    mapped_off = bench.shot(build("Mapped.TLabel", "disabled"))
    return (
        bool(root_map)
        and configured_normal != plain_normal
        and configured_off == plain_off
        and mapped_off != plain_off,
        f"root maps -foreground {root_map}; configure works normal, ignored disabled",
    )


def check_catch_all_map_kills_configure(bench: Bench) -> tuple[bool, str]:
    """A map entry with an empty state spec leaves configure no way in."""
    inherited = bench.style.map("TNotebook.Tab", "background")
    catch_all = any(len(spec) == 1 for spec in inherited)

    def build(name: str) -> Callable[[], tk.Widget]:
        def make() -> tk.Widget:
            notebook = ttk.Notebook(bench.root, style=name)
            for i in range(2):
                notebook.add(ttk.Frame(notebook), text=f"tab {i}")
            return notebook

        return make

    plain = bench.shot(build("Tabs.TNotebook"), (320, 160))
    bench.style.configure("Tabs.TNotebook.Tab", background="#ff00ff")
    configured = bench.shot(build("Tabs.TNotebook"), (320, 160))
    bench.style.map("Tabs.TNotebook.Tab", background=[("!disabled", "#ff00ff")])
    mapped = bench.shot(build("Tabs.TNotebook"), (320, 160))
    return (
        catch_all and configured == plain and mapped != plain,
        f"clam inherits {inherited}; configure inert, map works",
    )


def check_pointer_counts_as_state(bench: Bench) -> tuple[bool, str]:
    """A widget under the pointer is active, whatever else is true of it.

    The button is kept well short of the screen edge on purpose: a widget large
    enough to cover the corner leaves the pointer nowhere to be parked, and then
    it is permanently active -- which is the trap this check stands for.
    """
    button = ttk.Button(bench.root, text="Button")
    button.place(x=0, y=0, width=400, height=300)
    bench.root.event_generate("<Motion>", warp=True, x=100, y=100)
    bench.sync()
    hovered = set(button.state())
    bench.park()
    parked = set(button.state())
    button.destroy()
    return (
        "active" in hovered and "active" not in parked,
        f"under pointer {sorted(hovered)}, parked {sorted(parked) or 'no states'}",
    )


def check_widget_option_shadows_style(bench: Bench) -> tuple[bool, str]:
    """A widget option beats the style unless the widget's own value is empty."""
    bench.style.configure("Wide30.TButton", width=30)
    widths = []
    for own in ("", 4, 25):
        button = ttk.Button(bench.root, text="Button", style="Wide30.TButton")
        if own != "":
            button.configure(width=own)
        button.place(x=20, y=20)
        bench.sync()
        widths.append(button.winfo_reqwidth())
        button.destroy()
    empty, narrow, wide = widths
    return empty > wide > narrow, f"reqwidth for -width unset/4/25 was {widths}"


def check_text_never_comes_from_style(bench: Bench) -> tuple[bool, str]:
    """A style's -text is not drawn, even by a widget whose own -text is empty."""
    bench.style.configure("Shouty.TLabel", text="ZZZZZZZZ")
    label = ttk.Label(bench.root, text="", style="Shouty.TLabel")
    label.place(x=20, y=20)
    bench.sync()
    width = label.winfo_reqwidth()
    label.destroy()
    return width < 10, f"an empty label asked for {width}px with -text set in its style"


def check_underline_follows_the_shadow_rule(bench: Bench) -> tuple[bool, str]:
    """-underline is dead on a label, which owns one, and live on a heading, which does not."""
    bench.style.configure("Under.TLabel", underline=0)
    plain_label = bench.shot(lambda: ttk.Label(bench.root, text="Underline"))
    styled_label = bench.shot(lambda: ttk.Label(bench.root, text="Underline", style="Under.TLabel"))

    def tree(name: str) -> Callable[[], tk.Widget]:
        def make() -> tk.Widget:
            widget = ttk.Treeview(bench.root, columns=("a",), style=name, height=4)
            widget.heading("#0", text="Name")
            widget.heading("a", text="Alpha")
            widget.insert("", "end", text="row", values=("v",))
            return widget

        return make

    plain_tree = bench.shot(tree("Under.Treeview"), (340, 160))
    bench.style.configure("Under.Treeview.Heading", underline=0)
    styled_tree = bench.shot(tree("Under.Treeview"), (340, 160))
    return (
        plain_label == styled_label and plain_tree != styled_tree,
        f"label unchanged, heading changed {count_diff(plain_tree, styled_tree)} bytes",
    )


def check_treeview_rows_are_styled_by_tags(bench: Bench) -> tuple[bool, str]:
    """Row text comes from tags; only the row's height comes from the style."""

    def build(name: str, tagged: bool) -> Callable[[], tk.Widget]:
        def make() -> tk.Widget:
            tree = ttk.Treeview(bench.root, columns=("a",), style=name, height=4)
            for i in range(3):
                tree.insert("", "end", text=f"row {i}", values=(f"v{i}",), tags=("t",))
            if tagged:
                tree.tag_configure("t", foreground="#ff0000", background="#ffff00")
            return tree

        return make

    plain = bench.shot(build("Tagged.Treeview", False), (340, 160))
    bench.style.configure("Tagged.Treeview.Item", foreground="#ff0000", background="#ffff00")
    bench.style.configure("Tagged.Treeview.Cell", foreground="#ff0000")
    by_style = bench.shot(build("Tagged.Treeview", False), (340, 160))
    by_tag = bench.shot(build("Tagged.Treeview", True), (340, 160))
    bench.style.configure("Rows.Treeview", rowheight=40)
    tall = bench.shot(build("Rows.Treeview", False), (340, 160))
    return (
        by_style == plain and by_tag != plain and tall != plain,
        f"style inert, tag changed {count_diff(plain, by_tag)},"
        f" rowheight changed {count_diff(plain, tall)}",
    )


def check_combobox_popdown_is_a_listbox(bench: Bench) -> tuple[bool, str]:
    """The dropped-down list is a Tk listbox, reached through the option database."""
    bench.style.configure("Pop.TCombobox", fieldbackground="#ffff00", selectbackground="#00ff00")
    combo = ttk.Combobox(bench.root, style="Pop.TCombobox", values=["alpha", "beta"])
    combo.set("alpha")
    combo.place(x=40, y=40, width=200, height=36)
    bench.sync()
    combo.tk.call("ttk::combobox::Post", combo)
    bench.sync()
    popdown = combo.tk.call("ttk::combobox::PopdownWindow", combo)
    listbox = f"{popdown}.f.l"
    klass = combo.tk.call("winfo", "class", listbox)
    untouched = combo.tk.call(listbox, "cget", "-background")
    combo.tk.call("ttk::combobox::Unpost", combo)
    combo.destroy()

    bench.root.option_add("*TCombobox*Listbox.background", "#00ffff")
    other = ttk.Combobox(bench.root, values=["alpha", "beta"])
    other.set("alpha")
    other.place(x=40, y=40, width=200, height=36)
    bench.sync()
    other.tk.call("ttk::combobox::Post", other)
    bench.sync()
    popdown = other.tk.call("ttk::combobox::PopdownWindow", other)
    from_database = other.tk.call(f"{popdown}.f.l", "cget", "-background")
    other.tk.call("ttk::combobox::Unpost", other)
    other.destroy()
    return (
        klass == "Listbox" and untouched != "#ffff00" and from_database == "#00ffff",
        f"class {klass}, ttk style left it {untouched}, option database gave {from_database}",
    )


def check_entry_font_is_not_a_style_option(bench: Bench) -> tuple[bool, str]:
    """Entry.textarea declares -font and setting it in a style does nothing."""
    bench.style.configure("Big.TEntry", font="Helvetica 24 bold")
    styled = ttk.Entry(bench.root, style="Big.TEntry")
    styled.place(x=20, y=20, width=300, height=60)
    bench.sync()
    from_style = styled.winfo_reqheight()
    styled.configure(font="Helvetica 24 bold")
    bench.sync()
    from_widget = styled.winfo_reqheight()
    styled.destroy()
    declared = "font" in bench.style.element_options("Entry.textarea")
    return (
        declared and from_widget > from_style,
        f"declared by the element; reqheight {from_style} by style, {from_widget} by widget",
    )


CHECKS: list[Callable[[Bench], tuple[bool | str, str]]] = [
    check_framebuffer_matches_xwd,
    check_style_accepts_anything,
    check_name_resolution_strips_prefixes,
    check_orientation_prefix_falls_back,
    check_sublayouts_hang_off_widget_style,
    check_sash_is_looked_up_as_sash,
    check_map_beats_configure,
    check_catch_all_map_kills_configure,
    check_pointer_counts_as_state,
    check_widget_option_shadows_style,
    check_text_never_comes_from_style,
    check_underline_follows_the_shadow_rule,
    check_treeview_rows_are_styled_by_tags,
    check_combobox_popdown_is_a_listbox,
    check_entry_font_is_not_a_style_option,
]


def main(argv: list[str]) -> int:
    """Run every check and return how many failed."""
    if not argv:
        print(__doc__)
        return 2
    failed = 0
    with Framebuffer(argv[0]) as framebuffer:
        root = tk.Tk()
        print("Tk", root.tk.call("info", "patchlevel"))
        root.destroy()
        for check in CHECKS:
            bench = Bench(framebuffer)
            try:
                passed, detail = check(bench)
            except Exception as error:  # a broken check is a failed check
                passed, detail = False, f"raised {error!r}"
            finally:
                bench.close()
            if passed == SKIP:
                mark = "SKIP"
            elif passed:
                mark = "PASS"
            else:
                mark = "FAIL"
                failed += 1
            name = check.__name__.removeprefix("check_")
            print(f"  {mark}  {name:<40} {detail}")
    print(f"\n{failed} of {len(CHECKS)} checks failed")
    return failed


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
