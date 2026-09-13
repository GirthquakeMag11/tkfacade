"""Witness what `tk.Menu` and the `-menu` option do, one check per claim.

Run with::

    xvfb-run -a uv run python -m experiments.menu_probe.probe

The menubar rebuild rests on
what Tk's menubar mechanism actually is, as against the analogy that a
menubar is a composition of menubuttons. Each check here pins one fact
the design turns on: what the option accepts, that the bar is served by
a hidden clone rather than by the menu handed to it, how entries are
addressed and where that addressing breaks, what the bar does to a
window's geometry, and what dies with what. Nothing here imports
tkfacade.

The expectations coded below are the behaviour witnessed on Tk 8.6.14,
x11, under Xvfb with no window manager — see the README. A failure is a
finding, not necessarily a fault: menubars are native on macOS and
Windows, so several of these should be expected to fail there, and that
failure is the measurement. Every check prints its verdict; the exit
status is the number that failed.
"""

import sys
import tkinter as tk
from tkinter import ttk

Report = tuple[bool, str]


def bench(geometry: str = "400x300") -> tk.Tk:
    """Return a mapped root of a known size, ready for geometry reads."""
    root = tk.Tk()
    root.geometry(geometry)
    root.update()
    return root


def filled(master: tk.Misc, *labels: str) -> tk.Menu:
    """Return a tearoff-free menu carrying one cascade per label."""
    menu = tk.Menu(master, tearoff=False)
    for label in labels:
        menu.add_cascade(label=label, menu=tk.Menu(menu, tearoff=False))
    return menu


def tcl_children(root: tk.Tk, path: str = ".") -> tuple[str, ...]:
    """Return Tcl's own child list, which unlike tkinter's includes clones."""
    return tuple(str(child) for child in root.tk.splitlist(root.tk.call("winfo", "children", path)))


def clones(root: tk.Tk) -> list[str]:
    """Return the menubar clones Tk has built under the root."""
    return [child for child in tcl_children(root) if "#" in child]


# --- what the option accepts -------------------------------------------------


def check_menu_option_is_toplevel_and_menubutton_only() -> Report:
    """Only toplevels and menubuttons carry -menu; everything else raises."""
    root = bench()
    menu = filled(root, "File")
    takes, refuses = [], []
    candidates = (
        ("Tk", root),
        ("Toplevel", tk.Toplevel(root)),
        ("tk.Menubutton", tk.Menubutton(root)),
        ("ttk.Menubutton", ttk.Menubutton(root)),
        ("tk.Frame", tk.Frame(root)),
        ("ttk.Frame", ttk.Frame(root)),
        ("tk.Label", tk.Label(root)),
        ("tk.Canvas", tk.Canvas(root)),
        ("ttk.Notebook", ttk.Notebook(root)),
        ("tk.Menu", tk.Menu(root)),
    )
    for name, widget in candidates:
        try:
            widget["menu"] = str(menu)
            takes.append(name)
        except tk.TclError:
            refuses.append(name)
    root.destroy()
    expected = ["Tk", "Toplevel", "tk.Menubutton", "ttk.Menubutton"]
    return takes == expected, f"takes {takes}, refuses {len(refuses)} others"


def check_the_option_value_is_never_validated() -> Report:
    """A Frame's path, a dead path and a bare word are all accepted silently."""
    root = bench()
    accepted = []
    for value in (str(tk.Frame(root)), ".no.such.menu", "nosuchwidget"):
        try:
            root["menu"] = value
            root.update()
            accepted.append(str(root["menu"]))
        except tk.TclError as error:  # pragma: no cover - the finding is that it does not
            root.destroy()
            return False, f"raised on {value!r}: {error}"
    root.destroy()
    return len(accepted) == 3, f"all three accepted, last reads {accepted[-1]!r}"


def check_none_does_not_clear_the_bar() -> Report:
    """config(menu=None) is a no-op; only the empty string clears it."""
    root = bench()
    menu = filled(root, "File")
    root["menu"] = str(menu)
    root.update()
    root.configure(menu=None)
    after_none = str(root["menu"])
    root.configure(menu="")
    root.update()
    after_empty = str(root["menu"])
    root.destroy()
    return (after_none == str(menu) and after_empty == ""), (
        f"None leaves {after_none!r}, '' leaves {after_empty!r}"
    )


# --- the clone ---------------------------------------------------------------


def check_the_bar_is_served_by_a_clone() -> Report:
    """Assignment builds a second menu widget; the original never maps."""
    root = bench()
    menu = filled(root, "File")
    root["menu"] = str(menu)
    root.update()
    built = clones(root)
    original_mapped = menu.winfo_ismapped()
    root.destroy()
    return (len(built) == 1 and original_mapped == 0), (
        f"clone {built}, original ismapped={original_mapped}"
    )


def check_the_clone_is_invisible_to_tkinter() -> Report:
    """nametowidget raises on the clone and winfo_children drops it."""
    root = bench()
    menu = filled(root, "File")
    root["menu"] = str(menu)
    root.update()
    clone = clones(root)[0]
    listed = clone in [str(child) for child in root.winfo_children()]
    try:
        root.nametowidget(clone)
        reachable = True
    except KeyError:
        reachable = False
    root.destroy()
    return (
        not listed and not reachable
    ), f"in winfo_children={listed}, nametowidget ok={reachable}"


def check_configuring_the_clone_writes_through_to_the_original() -> Report:
    """The clone is not a copy: configure crosses back to the caller's object."""
    root = bench()
    menu = filled(root, "File")
    root["menu"] = str(menu)
    root.update()
    root.tk.call(clones(root)[0], "configure", "-background", "#abcdef")
    seen = str(menu["background"])
    root.destroy()
    return seen == "#abcdef", f"original background reads {seen!r}"


def check_a_dead_menu_leaves_the_option_naming_it() -> Report:
    """Destroying the assigned menu does not clear -menu."""
    root = bench()
    menu = filled(root, "File")
    path = str(menu)
    root["menu"] = path
    root.update()
    menu.destroy()
    root.update()
    still = str(root["menu"])
    root.destroy()
    return still == path, f"option still reads {still!r} for a destroyed widget"


def check_a_dead_menu_does_return_the_geometry() -> Report:
    """The option and the geometry disagree: the strip goes, the string stays."""
    root = bench()
    menu = filled(root, "File")
    root["menu"] = str(menu)
    root.update()
    with_bar = root.winfo_rooty()
    menu.destroy()
    root.update()
    without = root.winfo_rooty()
    root.destroy()
    return with_bar > without, f"rooty {with_bar} -> {without} while the option stands"


def check_a_path_from_another_interpreter_resolves_locally() -> Report:
    """Paths are interpreter-relative, so a foreign path names a local widget."""
    first, second = bench("300x200"), bench("300x200")
    here = filled(first, "FROM-A")
    there = filled(second, "FROM-B")
    same_path = str(here) == str(there)
    first["menu"] = str(there)
    first.update()
    resolved = first.nametowidget(first["menu"])
    label = str(resolved.entrycget(0, "label"))
    first.destroy()
    second.destroy()
    return (same_path and label == "FROM-A"), (
        f"paths collide={same_path}, bar shows {label!r} after asking for the other"
    )


# --- addressing an entry -----------------------------------------------------


def check_label_lookup_is_glob_matching() -> Report:
    """index() runs Tcl glob matching, so a wildcard reaches the wrong entry."""
    root = bench()
    menu = filled(root, "File", "Edit", "View", "Help")
    hit = menu.index("*e*")
    root.destroy()
    return hit == 0, f"index('*e*') answered {hit} in File/Edit/View/Help"


def check_reserved_words_beat_labels() -> Report:
    """An entry labelled 'end' cannot be addressed by its own label."""
    root = bench()
    menu = filled(root, "Alpha", "end", "Beta")
    hit = menu.index("end")
    root.destroy()
    return hit == 2, f"index('end') answered {hit}, which is the last entry not the labelled one"


def check_an_out_of_range_index_clamps_on_write() -> Report:
    """entryconfigure past the end silently rewrites the last entry."""
    root = bench()
    menu = filled(root, "File", "Edit", "View")
    menu.entryconfigure(99, label="CLOBBERED")
    last = str(menu.entrycget(2, "label"))
    root.destroy()
    return last == "CLOBBERED", f"entry 2 now reads {last!r} after writing to index 99"


def check_an_out_of_range_index_does_not_clamp_on_delete() -> Report:
    """delete past the end is a silent no-op, unlike entryconfigure."""
    root = bench()
    menu = filled(root, "File", "Edit", "View")
    menu.delete(99)
    remaining = menu.index("end")
    root.destroy()
    return remaining == 2, f"index('end') is {remaining} after delete(99) on a 0..2 menu"


def check_index_end_types_differ_on_empty_menus() -> Report:
    """index('end') is None without a tearoff and 0 with one."""
    root = bench()
    without = tk.Menu(root, tearoff=False).index("end")
    with_tearoff = tk.Menu(root, tearoff=True).index("end")
    root.destroy()
    return (without is None and with_tearoff == 0), (
        f"tearoff=False gives {without!r}, tearoff=True gives {with_tearoff!r}"
    )


def check_the_tearoff_entry_occupies_index_zero_of_a_bar() -> Report:
    """A tearoff menu used as a bar puts a phantom entry ahead of the first."""
    root = bench()
    menu = tk.Menu(root, tearoff=True)
    menu.add_cascade(label="File", menu=tk.Menu(menu, tearoff=False))
    root["menu"] = str(menu)
    root.update()
    kind = str(menu.type(0))
    root.destroy()
    return kind == "tearoff", f"index 0 of the bar is a {kind!r} entry, not the first cascade"


# --- entry behaviour ---------------------------------------------------------


def check_invoke_fires_a_cascades_command_without_posting() -> Report:
    """invoke() is not a simulated click: on a cascade the two disagree."""
    root = bench()
    menu = tk.Menu(root, tearoff=False)
    fired = []
    menu.add_cascade(
        label="File", menu=tk.Menu(menu, tearoff=False), command=lambda: fired.append(1)
    )
    root["menu"] = str(menu)
    root.update()
    menu.invoke(0)
    root.destroy()
    return fired == [1], f"cascade -command fired={bool(fired)} on invoke"


def check_deleting_a_cascade_leaks_its_submenu() -> Report:
    """The submenu widget outlives the entry that named it."""
    root = bench()
    menu = filled(root, "File")
    sub = root.nametowidget(menu.entrycget(0, "menu"))
    menu.delete(0)
    alive = sub.winfo_exists()
    root.destroy()
    return bool(alive), f"submenu winfo_exists={alive} after its cascade was deleted"


def check_destroying_a_submenu_leaves_the_cascade_live() -> Report:
    """The entry stays configurable and does nothing when invoked."""
    root = bench()
    menu = filled(root, "File")
    root.nametowidget(menu.entrycget(0, "menu")).destroy()
    menu.entryconfigure(0, label="Renamed")
    label = str(menu.entrycget(0, "label"))
    root.destroy()
    return label == "Renamed", f"orphaned cascade still renames to {label!r}"


def check_configuring_type_after_creation_is_inert() -> Report:
    """The option is accepted and reads back changed while nothing changes."""
    root = bench()
    menu = tk.Menu(root, tearoff=False)
    menu.add_command(label="A")
    menu.configure(type="menubar")
    reads = str(menu["type"])
    menu.post(50, 50)
    posted = menu.winfo_ismapped()
    menu.unpost()
    root.destroy()
    return (reads == "menubar" and posted == 1), (
        f"type reads {reads!r} yet the menu still posted (mapped={posted})"
    )


def check_cget_type_is_not_a_string() -> Report:
    """Menu options come back as Tcl_Obj, which compares unequal to the string."""
    root = bench()
    menu = tk.Menu(root, tearoff=False)
    value = menu["type"]
    root.destroy()
    return (not isinstance(value, str)) and str(value) == "normal", (
        f"type is {type(value).__name__}, equal to 'normal'={value == 'normal'}"
    )


def check_a_foreign_menu_on_a_menubutton_is_accepted() -> Report:
    """Parentage is enforced at click time, not at configure time."""
    root = bench()
    button = ttk.Menubutton(root, text="Pick")
    stranger = tk.Menu(root, tearoff=False)
    stranger.add_command(label="A")
    button["menu"] = str(stranger)
    accepted = str(button["menu"]) == str(stranger)
    try:
        root.tk.call("tk::MbPost", str(button))
        refused = False
    except tk.TclError:
        refused = True
    root.destroy()
    return (accepted and refused), f"configure accepted={accepted}, posting refused={refused}"


# --- geometry and lifetime ---------------------------------------------------


def check_a_program_set_geometry_keeps_its_interior() -> Report:
    """The bar grows the outer window rather than taking the interior."""
    root = bench()
    before = root.winfo_height()
    menu = filled(root, "File")
    root["menu"] = str(menu)
    root.update()
    after = root.winfo_height()
    moved = root.winfo_rooty()
    root.destroy()
    return (before == after == 300 and moved > 0), (
        f"interior {before} -> {after}, window pushed down by {moved}"
    )


def check_the_bars_height_depends_on_the_windows_width() -> Report:
    """The top row wraps, so a narrower window has a taller bar."""
    root = bench("600x200")
    menu = filled(root, *[f"Menu{n}" for n in range(10)])
    root["menu"] = str(menu)
    root.update()
    wide = root.winfo_rooty()
    root.geometry("150x200")
    root.update()
    narrow = root.winfo_rooty()
    root.destroy()
    return narrow > wide, f"bar height {wide} at 600px wide, {narrow} at 150px"


def check_a_menu_mastered_elsewhere_survives_its_bar_window() -> Report:
    """Only a menu owned by the toplevel dies with it."""
    root = bench()
    holder = tk.Toplevel(root)
    borrowed = filled(root, "File")
    owned = filled(holder, "Edit")
    holder["menu"] = str(borrowed)
    root.update()
    holder.destroy()
    root.update()
    survived, died = borrowed.winfo_exists(), owned.winfo_exists()
    root.destroy()
    return (bool(survived) and not died), f"borrowed exists={survived}, owned exists={died}"


CHECKS = (
    ("-menu is toplevels and menubuttons only", check_menu_option_is_toplevel_and_menubutton_only),
    ("the option value is never validated", check_the_option_value_is_never_validated),
    ("menu=None does not clear the bar", check_none_does_not_clear_the_bar),
    ("the bar is served by a hidden clone", check_the_bar_is_served_by_a_clone),
    ("the clone is invisible to tkinter", check_the_clone_is_invisible_to_tkinter),
    (
        "configuring the clone writes through",
        check_configuring_the_clone_writes_through_to_the_original,
    ),
    ("a dead menu leaves the option naming it", check_a_dead_menu_leaves_the_option_naming_it),
    ("a dead menu does return the geometry", check_a_dead_menu_does_return_the_geometry),
    ("a foreign path resolves locally", check_a_path_from_another_interpreter_resolves_locally),
    ("label lookup is glob matching", check_label_lookup_is_glob_matching),
    ("reserved words beat labels", check_reserved_words_beat_labels),
    ("a stale index clamps on write", check_an_out_of_range_index_clamps_on_write),
    ("a stale index no-ops on delete", check_an_out_of_range_index_does_not_clamp_on_delete),
    ("index('end') types differ when empty", check_index_end_types_differ_on_empty_menus),
    ("a tearoff takes index 0 of a bar", check_the_tearoff_entry_occupies_index_zero_of_a_bar),
    ("invoke fires a cascade's command", check_invoke_fires_a_cascades_command_without_posting),
    ("deleting a cascade leaks its submenu", check_deleting_a_cascade_leaks_its_submenu),
    ("a dead submenu leaves its cascade live", check_destroying_a_submenu_leaves_the_cascade_live),
    ("configure(type=...) is inert", check_configuring_type_after_creation_is_inert),
    ("cget('type') is not a str", check_cget_type_is_not_a_string),
    ("a foreign menubutton menu is accepted", check_a_foreign_menu_on_a_menubutton_is_accepted),
    ("a set geometry keeps its interior", check_a_program_set_geometry_keeps_its_interior),
    ("bar height depends on window width", check_the_bars_height_depends_on_the_windows_width),
    (
        "a borrowed menu outlives its window",
        check_a_menu_mastered_elsewhere_survives_its_bar_window,
    ),
)


def main() -> int:
    """Run every check, print each verdict, and return the failure count."""
    probe = tk.Tk()
    print(
        f"Tk {probe.tk.call('info', 'patchlevel')}, "
        f"windowingsystem {probe.tk.call('tk', 'windowingsystem')}, "
        f"{sys.platform}"
    )
    probe.destroy()
    failures = 0
    for name, check in CHECKS:
        try:
            ok, detail = check()
        except Exception as error:  # a raise is itself a finding about this build
            ok, detail = False, f"raised {type(error).__name__}: {error}"
        failures += 0 if ok else 1
        print(f"{name:42s} {'ok  ' if ok else 'FAIL'}  {detail}")
    return failures


if __name__ == "__main__":
    sys.exit(main())
