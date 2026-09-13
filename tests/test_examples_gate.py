"""The examples gate: example applications import tkfacade, never tkinter.

The demonstration requirement is that a nontrivial application
imports ``tkfacade`` and nothing else of the toolkit; ``examples/`` is
where such applications live, and this gate holds every file there to
the tkinter half of that claim — the facade is not supplanting tkinter
while its own demonstrations still reach past it. The showcase is also
built against a live window here, so "the example app runs" stays a
suite fact rather than a manual one.
"""

import ast
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

import tkfacade
from conftest import Pump
from tkfacade.window import Root

EXAMPLES = Path(__file__).parent.parent / "examples"


def _example_files() -> list[Path]:
    """Return every example module, sorted for stable parametrization."""
    return sorted(EXAMPLES.glob("*.py"))


def _imported_roots(source: Path) -> set[str]:
    """Return the root package of every import statement in one file."""
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            roots.add(node.module.partition(".")[0])
    return roots


def test_there_are_examples_to_gate() -> None:
    """The examples directory holds at least one module.

    The guard against the gate below silently covering nothing: the directory held only a README for a stretch of the project's life, and a rename or a stray deletion would return it to that state with the parametrized test green over an empty list.
    """
    assert _example_files(), f"no example modules under {EXAMPLES}"


@pytest.mark.parametrize("example", _example_files(), ids=lambda path: path.stem)
def test_an_example_never_imports_tkinter(example: Path) -> None:
    """No example module imports tkinter, _tkinter, or any submodule of either.

    The gate reads the AST rather than importing the module because the claim is about the source a reader sees -- an import inside a function or an `if` arm is still a reach past the facade -- and ast.walk visits those where a runtime check would miss any path not taken. Roots are compared exactly: tkfacade's own name contains no "tkinter", and a hypothetical third-party name merely containing the string should not fail the gate.
    """
    offending = {root for root in _imported_roots(example) if root in {"tkinter", "_tkinter"}}
    assert not offending, f"{example.name} imports {sorted(offending)}"


def _load_showcase() -> ModuleType:
    """Import ``examples/showcase.py`` by path, uncached."""
    spec = importlib.util.spec_from_file_location("showcase", EXAMPLES / "showcase.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["showcase"] = module
    try:
        spec.loader.exec_module(module)
    finally:
        del sys.modules["showcase"]
    return module


@pytest.mark.gui
def test_the_showcase_builds_on_a_live_window(root: Root, pump: Pump) -> None:
    """``showcase.build`` populates a window: bar filled, tabs live.

    What the demonstration requirement is worth day to day: the showcase is the one consumer written purely against the facade, so a public-surface regression that every focused test steps around tends to break it first. Built on the suite's window fixture rather than via main() so no mainloop runs; the assertions then check the build through public surface alone -- nametowrapper over the window's children and the mapping face of the TabFrame -- because reaching into the module's internals would exempt exactly the layer this test exists to exercise. Every direct child of the window resolving through nametowrapper is itself half the point: the window's registered children are exactly the tab container the showcase built, and a KeyError here would mean it grew a child no wrapper owns.
    """
    window = tkfacade.Window(title="showcase", menubar=True, root=root)
    _load_showcase().build(window)
    pump(window)

    assert window.menubar is not None
    assert [type(part).__name__ for part in window.menubar._parts] == ["Submenu"]
    wrappers = [window.nametowrapper(name) for name in window.children]
    assert sorted(type(w).__name__ for w in wrappers) == ["Menubar", "TabFrame"]
    tabs = next(w for w in wrappers if isinstance(w, tkfacade.TabFrame))
    assert set(tabs.keys()) == {
        "choices",
        "form",
        "labels",
        "list",
        "media",
        "split",
        "stack",
        "table",
        "text",
        "values",
    }
    assert tabs.showing is tabs["form"]
