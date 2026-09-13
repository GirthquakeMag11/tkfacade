"""File Save/Create: Tk's dialog recreated, the first case.

The claims pinned: the listing draws directories first (marked with a
trailing slash) and files through the chosen type filter; descending
and ascending redraw the listing and the ancestor row; a selected
file fills the name entry and Save resolves it against the current
directory, the default extension joining a bare name; an existing
target is gated by the nested confirm, driven here exactly as a user
would — through the grab-holding window's own buttons; the function
surface blocks and answers None on Escape; and the async twin
marshals its build to the interpreter thread under a real mainloop
and lands the answer on a coroutine.
"""

import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import pytest

import tkfacade
from conftest import Pump
from tkfacade import dialog
from tkfacade.dialog._file import (
    _DirectoryOpenDialog,
    _DirectorySaveDialog,
    _FileDialog,
    _FileOpenDialog,
    _FileSaveDialog,
)
from tkfacade.window import Root

pytestmark = pytest.mark.gui


def _tree(tmp_path: Path) -> Path:
    """A small mixed tree: two directories, text and image files."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "media").mkdir()
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.png").write_text("b")
    (tmp_path / "notes.txt").write_text("n")
    (tmp_path / "docs" / "inner.txt").write_text("i")
    return tmp_path


def _box(window: tkfacade.Window, where: Path, **overrides: object) -> _FileSaveDialog:
    """A save dialog over ``where``, text-filtered, overridable per test."""
    options: dict[str, object] = {
        "title": None,
        "initial_directory": where,
        "initial_name": "",
        "filters": (dialog.FileFilter("Text", ("*.txt",)),),
        "default_extension": None,
        "confirm_overwrite": True,
    }
    options.update(overrides)
    return _FileSaveDialog(window, **options)  # type: ignore[arg-type]


def _select(box: _FileDialog, text: str) -> None:
    """Select the listing row showing ``text``, the widget's own way."""
    tree = box._entries._treeview
    iids = tree.get_children("")
    texts = [str(tree.item(iid, "text")) for iid in iids]
    tree.selection_set(iids[texts.index(text)])


def _push(window: tkfacade.Window, caption: str) -> None:
    """Press the ``caption`` button inside the grab-holding window."""
    path = window._tk.tk.eval("grab current")
    assert path, "no grab holder to drive"
    holder = window._tk.nametowidget(path)
    stack: list[tk.Misc] = [holder]
    while stack:
        candidate = stack.pop()
        if isinstance(candidate, ttk.Button) and str(candidate.cget("text")) == caption:
            candidate.invoke()
            return
        stack.extend(candidate.winfo_children())
    raise AssertionError(f"no {caption!r} button under {path}")


def test_the_listing_draws_dirs_first_and_filters_files(
    window: tkfacade.Window, pump: Pump, tmp_path: Path
) -> None:
    """Directories lead with their slash; files obey the chosen type."""
    where = _tree(tmp_path)
    box = _box(window, where)

    assert list(box._entries) == ["docs/", "media/", "a.txt", "notes.txt"]

    types = box._types
    assert types is not None
    types.chosen = "All files (*)"
    assert list(box._entries) == ["docs/", "media/", "a.txt", "b.png", "notes.txt"]
    box.cancel()


def test_descending_and_ascending_redraw_the_dialog(
    window: tkfacade.Window, pump: Pump, tmp_path: Path
) -> None:
    """A directory double-click descends; the up button climbs back."""
    where = _tree(tmp_path)
    box = _box(window, where)
    box.show()
    pump(window)

    _select(box, "docs/")
    pump(window)
    box._open_selection(None)

    assert box._directory == where / "docs"
    assert list(box._entries) == ["inner.txt"]
    assert box._ancestors.chosen == str(where / "docs")

    box._ascend()
    assert box._directory == where
    assert "docs/" in list(box._entries)
    box.cancel()


def test_selection_fills_the_name_and_save_answers_the_path(
    window: tkfacade.Window, pump: Pump, tmp_path: Path
) -> None:
    """A picked file lands in the entry; Save resolves it to a Path."""
    where = _tree(tmp_path)
    box = _box(window, where, confirm_overwrite=False)
    box.show()
    pump(window)

    _select(box, "a.txt")
    pump(window)
    assert box._name.text == "a.txt"

    _select(box, "docs/")
    pump(window)
    assert box._name.text == "a.txt"  # a directory never overwrites the name

    box._commit()
    assert box.result() == where / "a.txt"


def test_the_default_extension_joins_only_a_bare_name(
    window: tkfacade.Window, pump: Pump, tmp_path: Path
) -> None:
    """A suffixless name takes the extension, dot supplied where missing."""
    where = _tree(tmp_path)
    bare = _box(window, where, confirm_overwrite=False, default_extension="txt")
    bare._name.text = "report"
    bare._commit()
    assert bare.result() == where / "report.txt"

    suffixed = _box(window, where, confirm_overwrite=False, default_extension="txt")
    suffixed._name.text = "picture.png"
    suffixed._commit()
    assert suffixed.result() == where / "picture.png"

    empty = _box(window, where, confirm_overwrite=False)
    empty._commit()
    assert not empty.done  # an empty name saves nothing
    empty.cancel()


def test_the_overwrite_gate_blocks_and_allows(
    window: tkfacade.Window, pump: Pump, tmp_path: Path
) -> None:
    """An existing target asks first: declining holds, accepting answers.

    The nested confirm is driven through the grab-holding window's own buttons — the same route a pointer takes — while the outer save flow stands parked in its nested wait, the probe's LIFO unwind.
    """
    where = _tree(tmp_path)
    box = _box(window, where)
    box.show()
    pump(window)
    box._name.text = "a.txt"

    window._tk.after(150, lambda: _push(window, "Cancel"))
    box._commit()
    assert not box.done  # declined: the dialog stays open

    window._tk.after(150, lambda: _push(window, "Replace"))
    box._commit()
    assert box.result() == where / "a.txt"


def test_the_function_blocks_and_escape_answers_none(
    window: tkfacade.Window, pump: Pump, tmp_path: Path
) -> None:
    """``dialog.file_save`` parks its caller; Escape dismisses to None."""
    where = _tree(tmp_path)

    def escape() -> None:
        path = window._tk.tk.eval("grab current")
        assert path
        window._tk.tk.call("event", "generate", path, "<Escape>")

    window._tk.after(200, escape)
    answer = dialog.file_save(window, initial_directory=where)

    assert answer is None


def test_the_async_twin_marshals_and_lands(
    window: tkfacade.Window, pump: Pump, root: Root, tmp_path: Path
) -> None:
    """Under a real mainloop, a coroutine gets its dialog and its answer.

    The build is marshalled to the interpreter thread (the off-thread
    crossing needs the mainloop live — the probe's fact), the posted
    dialog is driven through its own Save button, and the path lands
    back on the coroutine.
    """
    where = _tree(tmp_path)
    landed: list[Path | None] = []

    async def macro(_value: bool) -> None:
        landed.append(
            await dialog.async_file_save(
                window,
                initial_directory=where,
                initial_name="from-async",
                default_extension=".txt",
                confirm_overwrite=False,
            )
        )

    starter = tkfacade.ObservableBool(False)
    starter.transport_for(window._tk)
    subscription = starter.watch(macro)

    def drive(round: int = 0) -> None:
        path = window._tk.tk.eval("grab current")
        if path:
            _push(window, "Save")
            return
        if round < 100:
            window._tk.after(50, drive, round + 1)

    def watch_landing(round: int = 0) -> None:
        if landed or round >= 100:
            window._tk.quit()
            return
        window._tk.after(50, watch_landing, round + 1)

    window._tk.after(50, drive)
    window._tk.after(75, watch_landing)
    window._tk.mainloop()

    assert landed == [where / "from-async.txt"]
    subscription.cancel()
    starter.release_transport()
    deadline = time.monotonic() + 0.3
    while time.monotonic() < deadline:
        pump(window)
        time.sleep(0.01)


def _open_box(window: tkfacade.Window, where: Path) -> _FileOpenDialog:
    """An unfiltered open dialog over ``where``."""
    return _FileOpenDialog(window, title=None, initial_directory=where, initial_name="", filters=())


def test_open_commits_a_double_clicked_file_and_still_descends(
    window: tkfacade.Window, pump: Pump, tmp_path: Path
) -> None:
    """Double-click means descend on a directory and choose on a file."""
    where = _tree(tmp_path)
    box = _open_box(window, where)
    box.show()
    pump(window)

    _select(box, "docs/")
    pump(window)
    box._open_selection(None)
    assert box._directory == where / "docs"

    _select(box, "inner.txt")
    pump(window)
    box._open_selection(None)

    assert box.result() == where / "docs" / "inner.txt"


def test_open_takes_only_an_existing_file(
    window: tkfacade.Window, pump: Pump, tmp_path: Path
) -> None:
    """A missing name holds the dialog open; so does a directory's.

    Tk's own refusal, minus the bell: the open dialog completes for an existing file alone, a directory's name being navigation's business rather than an answer.
    """
    where = _tree(tmp_path)
    box = _open_box(window, where)
    box.show()
    pump(window)

    box._name.text = "missing.txt"
    box._commit()
    assert not box.done

    box._name.text = "docs"
    box._commit()
    assert not box.done

    box._name.text = "a.txt"
    box._commit()
    assert box.result() == where / "a.txt"


def test_the_open_function_blocks_and_escape_answers_none(
    window: tkfacade.Window, pump: Pump, tmp_path: Path
) -> None:
    """``dialog.file_open`` parks its caller; Escape dismisses to None."""
    where = _tree(tmp_path)

    def escape() -> None:
        path = window._tk.tk.eval("grab current")
        assert path
        window._tk.tk.call("event", "generate", path, "<Escape>")

    window._tk.after(200, escape)
    answer = dialog.file_open(window, initial_directory=where)

    assert answer is None


def _dir_box(window: tkfacade.Window, where: Path) -> _DirectorySaveDialog:
    """A directory-save dialog over ``where``."""
    return _DirectorySaveDialog(window, title=None, initial_directory=where, initial_name="")


def test_the_directory_mode_lists_directories_alone(
    window: tkfacade.Window, pump: Pump, tmp_path: Path
) -> None:
    """No files, no type row — Tk's chooseDir shape."""
    where = _tree(tmp_path)
    box = _dir_box(window, where)

    assert list(box._entries) == ["docs/", "media/"]
    assert box._types is None
    box.cancel()


def test_directory_save_answers_current_novel_and_never_a_file(
    window: tkfacade.Window, pump: Pump, tmp_path: Path
) -> None:
    """Empty means here; a novel name answers uncreated; a file refuses."""
    where = _tree(tmp_path)

    here = _dir_box(window, where)
    here._commit()
    assert here.result() == where

    novel = _dir_box(window, where)
    novel._name.text = "brand-new"
    novel._commit()
    assert novel.result() == where / "brand-new"
    assert not (where / "brand-new").exists()  # answered, never created

    refused = _dir_box(window, where)
    refused._name.text = "a.txt"  # an existing *file* is not a directory
    refused._commit()
    assert not refused.done
    refused.cancel()


def test_the_directory_save_function_blocks_and_escape_answers_none(
    window: tkfacade.Window, pump: Pump, tmp_path: Path
) -> None:
    """``dialog.directory_save`` parks its caller; Escape dismisses to None."""
    where = _tree(tmp_path)

    def escape() -> None:
        path = window._tk.tk.eval("grab current")
        assert path
        window._tk.tk.call("event", "generate", path, "<Escape>")

    window._tk.after(200, escape)
    answer = dialog.directory_save(window, initial_directory=where)

    assert answer is None


def test_directory_open_takes_only_an_existing_directory(
    window: tkfacade.Window, pump: Pump, tmp_path: Path
) -> None:
    """Empty means here; an existing name answers; anything else holds."""
    where = _tree(tmp_path)

    box = _DirectoryOpenDialog(window, title=None, initial_directory=where, initial_name="")
    box._name.text = "not-there"
    box._commit()
    assert not box.done

    box._name.text = "a.txt"  # a file's name is not a directory
    box._commit()
    assert not box.done

    box._name.text = "docs"
    box._commit()
    assert box.result() == where / "docs"

    here = _DirectoryOpenDialog(window, title=None, initial_directory=where, initial_name="")
    here._commit()
    assert here.result() == where


def test_the_directory_open_function_blocks_and_escape_answers_none(
    window: tkfacade.Window, pump: Pump, tmp_path: Path
) -> None:
    """``dialog.directory_open`` parks its caller; Escape dismisses to None."""
    where = _tree(tmp_path)

    def escape() -> None:
        path = window._tk.tk.eval("grab current")
        assert path
        window._tk.tk.call("event", "generate", path, "<Escape>")

    window._tk.after(200, escape)
    answer = dialog.directory_open(window, initial_directory=where)

    assert answer is None
