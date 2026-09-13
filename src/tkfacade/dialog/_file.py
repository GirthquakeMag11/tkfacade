"""The file dialogs: Tk's design recreated on the Dialog foundation.

A directory row over an entry listing, a name row, a type row —
recreated from the library's own widgets on :class:`~tkfacade.Dialog`,
wrapping nothing.
"""

import fnmatch
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ..button import Button
from ..choice import ChoiceBox
from ..events import Event, Key, Press, Virtual, VirtualEvent
from ..label import TextLabel
from ..listbox import Listbox
from ..text import Entry
from ..window import Window
from ._dialog import Dialog, _posted
from ._message import _MessageDialog


@dataclass(frozen=True, slots=True)
class FileFilter:
    """One choosable file-type filter: a label over glob patterns.

    An inert declaration the dialog applies: carrying it constructs
    nothing and filters nothing until a dialog wears it.

    Args:
        label (str): What the type row calls this filter, e.g.
            ``"Images"``.
        patterns (tuple[str, ...]): The glob patterns a shown file
            must match one of, e.g. ``("*.png", "*.jpg")``.
    """

    label: str
    patterns: tuple[str, ...]

    @property
    def caption(self) -> str:
        """The filter as the type row draws it: label, then patterns."""
        return f"{self.label} ({' '.join(self.patterns)})"


_ALL_FILES = FileFilter("All files", ("*",))
"""The filter every dialog offers last, whatever was asked for."""


class _FileDialog(Dialog[Path]):
    """The recreated Tk file dialog skeleton the concrete cases share.

    Layout and navigation live here — the directory row over the
    filtered listing, the name and type rows, descending, ascending,
    jumping the ancestor chain — while what the affirm button *means*
    is each subclass's :meth:`_commit`. Directories list first with a
    trailing ``/``; files follow, filtered by the chosen type;
    selecting a file fills the name entry and Return in it commits;
    double-click descends into a directory row (a raw bind, the
    window-plumbing exemption: the public event vocabulary carries no
    click count) or hands a file row to
    :meth:`_take_double_clicked_file`.
    """

    __slots__ = (
        "_ancestors",
        "_directory",
        "_entries",
        "_filters",
        "_name",
        "_types",
    )

    def __init__(
        self,
        parent: Window,
        /,
        *,
        title: str,
        affirm: str,
        initial_directory: Path | None,
        initial_name: str,
        filters: Sequence[FileFilter] | None,
        name_caption: str = "File name:",
    ) -> None:
        """Build the skeleton; ``filters=None`` is the directory mode.

        In directory mode the listing shows directories alone and the
        type row is absent — Tk's ``chooseDir`` shape; otherwise the
        given filters are offered with the all-files entry last.
        """
        super().__init__(parent, title=title, width=440, height=380)
        self._directory = (
            initial_directory if initial_directory is not None else Path.cwd()
        ).resolve()
        self._filters: tuple[FileFilter, ...] | None = (
            None if filters is None else (*filters, _ALL_FILES)
        )
        window = self._window
        window.grid_columnconfigure(1, weight=1)
        window.grid_rowconfigure(1, weight=1)

        TextLabel(window, text="Directory:").grid(row=0, column=0, sticky="w", padx=(10, 4), pady=8)
        self._ancestors = ChoiceBox(window, self._ancestor_options(), chosen=str(self._directory))
        self._ancestors.grid(row=0, column=1, sticky="ew", pady=8)
        Button(window, "Up", command=self._ascend).grid(row=0, column=2, padx=(4, 10), pady=8)

        self._entries = Listbox(window, height=12)
        self._entries.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=10)

        TextLabel(window, text=name_caption).grid(row=2, column=0, sticky="w", padx=(10, 4), pady=6)
        self._name = Entry(window, initial_name)
        self._name.grid(row=2, column=1, sticky="ew", pady=6)
        Button(window, affirm, command=self._commit).grid(row=2, column=2, padx=(4, 10), pady=6)

        self._types: ChoiceBox | None = None
        if self._filters is not None:
            TextLabel(window, text="Files of type:").grid(
                row=3, column=0, sticky="w", padx=(10, 4), pady=(0, 10)
            )
            self._types = ChoiceBox(
                window,
                tuple(one.caption for one in self._filters),
                chosen=self._filters[0].caption,
            )
            self._types.grid(row=3, column=1, sticky="ew", pady=(0, 10))
        Button(window, "Cancel", command=self.cancel).grid(
            row=3, column=2, padx=(4, 10), pady=(0, 10)
        )

        if self._types is not None:
            self._types.chosen_observable.watch(lambda _value: self._refresh())
        else:
            self._refresh()
        self._ancestors.chosen_observable.watch(self._jump)
        self._entries.bind(Virtual(VirtualEvent.TREEVIEW_SELECT), self._take_selection)
        self._name.bind(Press(Key.ENTER), lambda event: self._commit())
        self._entries._treeview.bind("<Double-Button-1>", self._open_selection, add="+")

    # ----------------
    # The moving parts
    # ----------------

    def _ancestor_options(self) -> tuple[str, ...]:
        """The current directory and its chain up to the root, downward first."""
        return tuple(str(step) for step in (self._directory, *self._directory.parents))

    def _active_patterns(self) -> tuple[str, ...]:
        """The chosen filter's patterns; the catch-all if nothing matches."""
        if self._types is None or self._filters is None:
            return _ALL_FILES.patterns
        chosen = self._types.chosen
        for one in self._filters:
            if one.caption == chosen:
                return one.patterns
        return _ALL_FILES.patterns

    def _refresh(self) -> None:
        """Rebuild the listing: directories first, files by the filter.

        Directory mode lists directories alone.
        """
        try:
            children = sorted(self._directory.iterdir(), key=lambda child: child.name.lower())
        except OSError:
            children = []
        rows = [f"{child.name}/" for child in children if child.is_dir()]
        if self._filters is not None:
            patterns = self._active_patterns()
            rows.extend(
                child.name
                for child in children
                if not child.is_dir()
                and any(fnmatch.fnmatch(child.name, pattern) for pattern in patterns)
            )
        self._entries[:] = rows

    def _visit(self, target: Path) -> None:
        """Move the dialog to ``target`` and redraw everything above it."""
        self._directory = target
        self._ancestors.options = self._ancestor_options()
        self._ancestors.chosen = str(target)
        self._refresh()

    def _ascend(self) -> None:
        """The up button: one step toward the root, which is its own parent."""
        if self._directory.parent != self._directory:
            self._visit(self._directory.parent)

    def _jump(self, value: str) -> None:
        """The directory row's choice: jump anywhere on the ancestor chain.

        Also hears the echoes of the dialog's own moves — the equal
        guard is what keeps a programmatic visit from recursing.
        """
        if value and Path(value) != self._directory:
            self._visit(Path(value))

    def _take_selection(self, _event: Event) -> None:
        """A selected file fills the name entry; a directory does not."""
        chosen = self._entries.selected_items
        if chosen and not chosen[0].endswith("/"):
            self._name.text = chosen[0]

    def _open_selection(self, _event: object) -> None:
        """Double-click: descend into a directory, or hand a file onward."""
        chosen = self._entries.selected_items
        if not chosen:
            return
        if chosen[0].endswith("/"):
            self._visit(self._directory / chosen[0].rstrip("/"))
        else:
            self._take_double_clicked_file(chosen[0])

    def _take_double_clicked_file(self, name: str, /) -> None:
        """A double-clicked file row; nothing, unless a subclass says so."""

    def _commit(self) -> None:
        """What the affirm button means; each concrete case says.

        Raises:
            NotImplementedError: Always, on the skeleton itself.
        """
        raise NotImplementedError


class _FileSaveDialog(_FileDialog):
    """The save case: a name to write to, gated when it already exists.

    Internal — :func:`file_save` and :func:`async_file_save` are the
    public surface.
    """

    __slots__ = ("_confirm_overwrite", "_default_extension")

    def __init__(
        self,
        parent: Window,
        /,
        *,
        title: str | None,
        initial_directory: Path | None,
        initial_name: str,
        filters: Sequence[FileFilter],
        default_extension: str | None,
        confirm_overwrite: bool,
    ) -> None:
        super().__init__(
            parent,
            title=title if title is not None else "Save As",
            affirm="Save",
            initial_directory=initial_directory,
            initial_name=initial_name,
            filters=filters,
        )
        self._default_extension = default_extension
        self._confirm_overwrite = confirm_overwrite

    def _commit(self) -> None:
        """Resolve the typed name against the current directory and complete.

        An empty name does nothing. A name with no suffix takes the
        default extension when one was given. An existing target is
        gated by the nested confirm when overwrite confirmation is
        on — the outer dialog retakes its grab after the nested one
        releases it, since a grab dies with its window.
        """
        name = self._name.text.strip()
        if not name:
            return
        target = self._directory / name
        if not target.suffix and self._default_extension is not None:
            extension = self._default_extension
            if not extension.startswith("."):
                extension = f".{extension}"
            target = target.with_suffix(extension)
        if self._confirm_overwrite and target.exists():
            sure = _MessageDialog(
                self._window,
                f"{target.name} already exists.\nReplace it?",
                title="Confirm",
                affirm="Replace",
                decline="Cancel",
            ).result()
            self.show()
            if not sure:
                return
        self.complete(target)


class _FileOpenDialog(_FileDialog):
    """The open case: an existing file, picked or typed, nothing else.

    Internal — :func:`file_open` and :func:`async_file_open` are the
    public surface. Tk's own refusal, minus the bell: a name that
    resolves to nothing, or to a directory, holds the dialog open.
    """

    __slots__ = ()

    def __init__(
        self,
        parent: Window,
        /,
        *,
        title: str | None,
        initial_directory: Path | None,
        initial_name: str,
        filters: Sequence[FileFilter],
    ) -> None:
        super().__init__(
            parent,
            title=title if title is not None else "Open",
            affirm="Open",
            initial_directory=initial_directory,
            initial_name=initial_name,
            filters=filters,
        )

    def _commit(self) -> None:
        """Complete with the resolved name — an existing file only."""
        name = self._name.text.strip()
        if not name:
            return
        target = self._directory / name
        if target.is_file():
            self.complete(target)

    def _take_double_clicked_file(self, name: str, /) -> None:
        """Double-clicking a file chooses it, Tk's own open gesture."""
        self._name.text = name
        self._commit()


class _DirectorySaveDialog(_FileDialog):
    """The directory save case: where a directory should be, existing or not.

    Internal — :func:`directory_save` and :func:`async_directory_save`
    are the public surface. Tk's ``chooseDir`` shape with
    ``-mustexist`` off: the answer may name a directory that does not
    exist yet, and nothing is created — the answer is where the
    caller should act. An empty name answers the current directory
    itself; a name held by an existing *file* refuses.
    """

    __slots__ = ()

    def __init__(
        self,
        parent: Window,
        /,
        *,
        title: str | None,
        initial_directory: Path | None,
        initial_name: str,
    ) -> None:
        super().__init__(
            parent,
            title=title if title is not None else "Choose Directory",
            affirm="Choose",
            initial_directory=initial_directory,
            initial_name=initial_name,
            filters=None,
            name_caption="Directory name:",
        )

    def _commit(self) -> None:
        """Complete with the resolved name, existing or not — never a file's."""
        name = self._name.text.strip()
        target = self._directory / name if name else self._directory
        if target.exists() and not target.is_dir():
            return
        self.complete(target)


class _DirectoryOpenDialog(_FileDialog):
    """The directory open case: an existing directory, nothing else.

    Internal — :func:`directory_open` and :func:`async_directory_open`
    are the public surface. Tk's ``chooseDir`` shape with
    ``-mustexist`` on: only a directory that already exists completes
    the dialog. An empty name answers the directory being looked at,
    which by construction exists.
    """

    __slots__ = ()

    def __init__(
        self,
        parent: Window,
        /,
        *,
        title: str | None,
        initial_directory: Path | None,
        initial_name: str,
    ) -> None:
        super().__init__(
            parent,
            title=title if title is not None else "Choose Directory",
            affirm="Choose",
            initial_directory=initial_directory,
            initial_name=initial_name,
            filters=None,
            name_caption="Directory name:",
        )

    def _commit(self) -> None:
        """Complete with the resolved name — an existing directory only."""
        name = self._name.text.strip()
        target = self._directory / name if name else self._directory
        if target.is_dir():
            self.complete(target)


# --------------------
# The calling surface
# --------------------


def file_save(
    parent: Window,
    /,
    *,
    title: str | None = None,
    initial_directory: Path | None = None,
    initial_name: str = "",
    filters: Sequence[FileFilter] = (),
    default_extension: str | None = None,
    confirm_overwrite: bool = True,
) -> Path | None:
    """Ask where to save a file; block until answered, pumping throughout.

    The save dialog: pick or type a name under a chosen directory.
    Nothing is written to disk — the answer is where the caller
    should write.

    Args:
        parent (Window): The window the dialog prompts for.
        title (str | None): The dialog's title. Defaults to None,
            meaning "Save As".
        initial_directory (Path | None): Where the dialog opens.
            Defaults to None, meaning the working directory.
        initial_name (str): The name the entry starts with. Defaults
            to empty.
        filters (Sequence[FileFilter]): The choosable file types; an
            all-files filter is always offered last. Defaults to
            none, leaving only all-files.
        default_extension (str | None): Appended to a typed name with
            no suffix, with or without its leading dot. Defaults to
            None, appending nothing.
        confirm_overwrite (bool): Whether choosing an existing file
            asks before answering. Defaults to True.

    Returns:
        The chosen path, or None for a dismissal.
    """
    box = _FileSaveDialog(
        parent,
        title=title,
        initial_directory=initial_directory,
        initial_name=initial_name,
        filters=filters,
        default_extension=default_extension,
        confirm_overwrite=confirm_overwrite,
    )
    return box.result()


async def async_file_save(
    parent: Window,
    /,
    *,
    title: str | None = None,
    initial_directory: Path | None = None,
    initial_name: str = "",
    filters: Sequence[FileFilter] = (),
    default_extension: str | None = None,
    confirm_overwrite: bool = True,
) -> Path | None:
    """The awaitable :func:`file_save`: same dialog, no parked frame.

    Await it from a coroutine on the root's core; the options and the
    answer are :func:`file_save`'s exactly. The dialog is built and
    shown on the interpreter's thread — the crossing needs the
    mainloop live, like every off-thread door in the library.
    """
    box = await _posted(
        parent,
        lambda: _FileSaveDialog(
            parent,
            title=title,
            initial_directory=initial_directory,
            initial_name=initial_name,
            filters=filters,
            default_extension=default_extension,
            confirm_overwrite=confirm_overwrite,
        ),
    )
    return await box.wait()


def file_open(
    parent: Window,
    /,
    *,
    title: str | None = None,
    initial_directory: Path | None = None,
    initial_name: str = "",
    filters: Sequence[FileFilter] = (),
) -> Path | None:
    """Ask which existing file to open; block until answered, pumping throughout.

    The open dialog: pick a file from the listing — double-clicking
    one chooses it — or type its name. Only an existing file
    completes the dialog; one file at a time.

    Args:
        parent (Window): The window the dialog prompts for.
        title (str | None): The dialog's title. Defaults to None,
            meaning "Open".
        initial_directory (Path | None): Where the dialog opens.
            Defaults to None, meaning the working directory.
        initial_name (str): The name the entry starts with. Defaults
            to empty.
        filters (Sequence[FileFilter]): The choosable file types; an
            all-files filter is always offered last. Defaults to
            none, leaving only all-files.

    Returns:
        The chosen path, or None for a dismissal.
    """
    box = _FileOpenDialog(
        parent,
        title=title,
        initial_directory=initial_directory,
        initial_name=initial_name,
        filters=filters,
    )
    return box.result()


async def async_file_open(
    parent: Window,
    /,
    *,
    title: str | None = None,
    initial_directory: Path | None = None,
    initial_name: str = "",
    filters: Sequence[FileFilter] = (),
) -> Path | None:
    """The awaitable :func:`file_open`: same dialog, no parked frame.

    Await it from a coroutine on the root's core; the options and the
    answer are :func:`file_open`'s exactly. The dialog is built and
    shown on the interpreter's thread — the crossing needs the
    mainloop live, like every off-thread door in the library.
    """
    box = await _posted(
        parent,
        lambda: _FileOpenDialog(
            parent,
            title=title,
            initial_directory=initial_directory,
            initial_name=initial_name,
            filters=filters,
        ),
    )
    return await box.wait()


def directory_save(
    parent: Window,
    /,
    *,
    title: str | None = None,
    initial_directory: Path | None = None,
    initial_name: str = "",
) -> Path | None:
    """Ask where a directory should be; block until answered, pumping throughout.

    The directory dialog with creation allowed: navigate to a
    directory, or type a name for one that does not exist yet — the
    answer may be novel, and nothing is created; the answer is where
    the caller should act. An empty name answers the directory being
    looked at.

    Args:
        parent (Window): The window the dialog prompts for.
        title (str | None): The dialog's title. Defaults to None,
            meaning "Choose Directory".
        initial_directory (Path | None): Where the dialog opens.
            Defaults to None, meaning the working directory.
        initial_name (str): The name the entry starts with. Defaults
            to empty.

    Returns:
        The chosen path, or None for a dismissal.
    """
    box = _DirectorySaveDialog(
        parent,
        title=title,
        initial_directory=initial_directory,
        initial_name=initial_name,
    )
    return box.result()


async def async_directory_save(
    parent: Window,
    /,
    *,
    title: str | None = None,
    initial_directory: Path | None = None,
    initial_name: str = "",
) -> Path | None:
    """The awaitable :func:`directory_save`: same dialog, no parked frame.

    Await it from a coroutine on the root's core; the options and the
    answer are :func:`directory_save`'s exactly. The dialog is built
    and shown on the interpreter's thread — the crossing needs the
    mainloop live, like every off-thread door in the library.
    """
    box = await _posted(
        parent,
        lambda: _DirectorySaveDialog(
            parent,
            title=title,
            initial_directory=initial_directory,
            initial_name=initial_name,
        ),
    )
    return await box.wait()


def directory_open(
    parent: Window,
    /,
    *,
    title: str | None = None,
    initial_directory: Path | None = None,
    initial_name: str = "",
) -> Path | None:
    """Ask which existing directory to use; block until answered, pumping throughout.

    The directory dialog with existence required: navigate to a
    directory, or type the name of one that exists. An empty name
    answers the directory being looked at.

    Args:
        parent (Window): The window the dialog prompts for.
        title (str | None): The dialog's title. Defaults to None,
            meaning "Choose Directory".
        initial_directory (Path | None): Where the dialog opens.
            Defaults to None, meaning the working directory.
        initial_name (str): The name the entry starts with. Defaults
            to empty.

    Returns:
        The chosen path, or None for a dismissal.
    """
    box = _DirectoryOpenDialog(
        parent,
        title=title,
        initial_directory=initial_directory,
        initial_name=initial_name,
    )
    return box.result()


async def async_directory_open(
    parent: Window,
    /,
    *,
    title: str | None = None,
    initial_directory: Path | None = None,
    initial_name: str = "",
) -> Path | None:
    """The awaitable :func:`directory_open`: same dialog, no parked frame.

    Await it from a coroutine on the root's core; the options and the
    answer are :func:`directory_open`'s exactly. The dialog is built
    and shown on the interpreter's thread — the crossing needs the
    mainloop live, like every off-thread door in the library.
    """
    box = await _posted(
        parent,
        lambda: _DirectoryOpenDialog(
            parent,
            title=title,
            initial_directory=initial_directory,
            initial_name=initial_name,
        ),
    )
    return await box.wait()
