"""The public-surface audit: tkinter types stay behind the facade.

The library's goal is an imperative interface usable
without naming a tkinter type, and this suite is the ratchet that
measures it: every annotation on the public surface is walked, every
tkinter type found is compared against the allowlist below, and the two
must match exactly. Work that seals part of the surface deletes its
entries; work that would leak a new tkinter type fails here before it
lands. The one structural allowance is the hospitality widening:
a *parameter* union offering a
:class:`~tkfacade.widget.BaseWidget` alternative alongside raw tkinter
acceptance — ``parent: tk.Misc | BaseWidget`` and its kin — forces
tkinter on no caller and is not a leak.

The surface walked: every public name exported by ``tkfacade`` and its
public subpackages, closed over the tkfacade classes those names reach —
base classes, and the component handles public members answer with
(the facade boundary) — then every public method,
property, module-level function, class-level field, and type alias of
the lot.
"""

import enum
import pkgutil
import types
from annotationlib import Format, ForwardRef, get_annotations
from collections.abc import Iterator
from functools import cache
from importlib import import_module
from typing import Any, TypeAliasType, get_args, get_origin

import tkfacade
from tkfacade.widget import BaseWidget

ALLOWLIST: frozenset[str] = frozenset(
    (
        # the tkinter-master protocol stratum, ruled 2026-08-27:
        # construction writes into the dict children answers,
        # Misc._root() walks master, and tkinter reads tk off every
        # master, so none can answer wrappers; parent and the
        # *_slaves methods are the facade's own words instead.
        "BaseWidget.children:return",
        "BaseWidget.master:return",
        "BaseWidget.tk:return",
        # widened parameters — hospitality: a raw master is accepted
        # everywhere a wrapper is, and a caller who never imports
        # tkinter never notices.
        "BaseWindow.__init__:master",
        "ImageWrapper.iter_frames:master",
        "ImageWrapper.photo_for:master",
        "Observable.transport_for:master",
        # wrapper plumbing: the transport is the variable wrappers
        # hand to Tk's -variable options, documented as something a
        # caller watching or driving the value never needs.
        "Observable.transport_for:return",
        # the documented raw stratum: the *Info dicts
        # relay a geometry manager's answers verbatim and the raw
        # event dict relays Tk's packet, each declaring Tk's own types
        # with the trap named.
        "GridInfo.in",
        "PackInfo.in",
        "PlaceInfo.in",
        "RawEventDict.type",
        "RawEventDict.widget",
    )
)
"""Every tkinter-typed public signature element the surface still carries.

Seeded with the honest baseline at instantiation
and only ever shrunk: the work that seals an element deletes its entry
in the same change, and the audit's exact-match assertion turns a stale
entry into a failure just like a fresh leak. Entries are
``Owner.member:slot`` — the slot a parameter name, ``return`` for a
return or property getter, ``value`` for a property setter — or
``Owner.field`` for a class-level field, or a bare alias name.

Terminal as of 2026-08-27: every entry is a ruled widening, the
protocol stratum, or the documented raw stratum, each
group carrying its ruling above. The list grows only by ruling — a
fresh leak is a defect, never a candidate entry.
"""


def _public_modules() -> Iterator[types.ModuleType]:
    """Yield ``tkfacade`` and every public submodule under it."""
    yield tkfacade
    for info in pkgutil.iter_modules(tkfacade.__path__):
        if not info.name.startswith("_"):
            yield import_module(f"tkfacade.{info.name}")


def _atoms(annotation: Any) -> Iterator[Any]:
    """Yield every atomic type an annotation is built from.

    Unwraps unions, generics, and callables recursively; what comes out
    is classes, special forms, and — for names resolvable only under
    ``TYPE_CHECKING`` — :class:`ForwardRef` proxies, which the caller
    matches by their text.
    """
    if annotation is None or annotation is Ellipsis:
        return
    origin = get_origin(annotation)
    if origin is None:
        yield annotation
        return
    yield origin
    for arg in get_args(annotation):
        if isinstance(arg, list):  # Callable[[X, Y], Z] parameter lists
            for inner in arg:
                yield from _atoms(inner)
        else:
            yield from _atoms(arg)


def _is_tkinter(atom: Any) -> bool:
    """Return whether one atom is a tkinter (or _tkinter) type."""
    if isinstance(atom, ForwardRef):
        return "tkinter" in atom.__forward_arg__
    module = getattr(atom, "__module__", "")
    return module == "tkinter" or module.startswith("tkinter.") or module == "_tkinter"


def _is_widening(annotation: Any) -> bool:
    """Return whether a parameter annotation is a hospitality widening.

    True when the union offers a wrapper alternative beside the raw
    tkinter acceptance, so a caller never needs the tkinter half.
    """
    return any(
        isinstance(atom, type) and issubclass(atom, BaseWidget) for atom in _atoms(annotation)
    )


def _is_tkfacade_class(atom: Any) -> bool:
    """Return whether one atom is a class tkfacade itself defines."""
    return isinstance(atom, type) and atom.__module__.startswith("tkfacade")


def _function_leaks(owner: str, name: str, func: Any) -> Iterator[str]:
    """Yield the allowlist entry for each tkinter-typed slot of one callable."""
    annotations = get_annotations(func, format=Format.FORWARDREF)
    for slot, annotation in annotations.items():
        if slot != "return" and _is_widening(annotation):
            continue
        if any(_is_tkinter(atom) for atom in _atoms(annotation)):
            yield f"{owner}.{name}:{slot}" if owner else f"{name}:{slot}"


@cache
def _audit() -> tuple[frozenset[str], frozenset[str]]:
    """Walk the public surface once; return (leak entries, classes walked)."""
    queue: list[type] = []
    functions: list[tuple[str, Any]] = []
    aliases: list[TypeAliasType] = []
    seen: set[int] = set()

    def enqueue(atom: Any) -> None:
        if _is_tkfacade_class(atom) and not atom.__name__.startswith("_") and id(atom) not in seen:
            seen.add(id(atom))
            queue.append(atom)

    for module in _public_modules():
        for name, member in vars(module).items():
            if name.startswith("_"):
                continue
            if isinstance(member, TypeAliasType):
                aliases.append(member)
            elif isinstance(member, types.FunctionType) and member.__module__.startswith(
                "tkfacade"
            ):
                functions.append((name, member))
            else:
                enqueue(member)

    leaks: set[str] = set()
    walked: set[str] = set()

    for name, func in functions:
        walked.add(name)
        leaks.update(_function_leaks("", name, func))

    for alias in aliases:
        walked.add(alias.__name__)
        if any(_is_tkinter(atom) for atom in _atoms(alias.__value__)):
            leaks.add(alias.__name__)

    while queue:
        cls = queue.pop()
        walked.add(cls.__name__)
        for base in cls.__mro__[1:]:
            enqueue(base)
        if issubclass(cls, enum.Enum):
            continue
        for field, annotation in get_annotations(cls, format=Format.FORWARDREF).items():
            if field.startswith("_"):
                continue
            if any(_is_tkinter(atom) for atom in _atoms(annotation)):
                leaks.add(f"{cls.__qualname__}.{field}")
            for atom in _atoms(annotation):
                enqueue(atom)
        for name, member in vars(cls).items():
            if name.startswith("_") and name != "__init__":
                continue
            if isinstance(member, classmethod | staticmethod):
                member = member.__func__
            if isinstance(member, types.FunctionType):
                leaks.update(_function_leaks(cls.__qualname__, name, member))
                for atom in _atoms(get_annotations(member, format=Format.FORWARDREF).get("return")):
                    enqueue(atom)
            elif isinstance(member, property):
                if member.fget is not None:
                    returned = get_annotations(member.fget, format=Format.FORWARDREF).get("return")
                    if any(_is_tkinter(atom) for atom in _atoms(returned)):
                        leaks.add(f"{cls.__qualname__}.{name}:return")
                    for atom in _atoms(returned):
                        enqueue(atom)
                if member.fset is not None:
                    values = get_annotations(member.fset, format=Format.FORWARDREF)
                    values.pop("return", None)
                    for annotation in values.values():
                        if not _is_widening(annotation) and any(
                            _is_tkinter(atom) for atom in _atoms(annotation)
                        ):
                            leaks.add(f"{cls.__qualname__}.{name}:value")

    return frozenset(leaks), frozenset(walked)


def test_every_tkinter_type_on_the_surface_is_allowlisted() -> None:
    """The surface's tkinter-typed elements and the allowlist match exactly.

    The exact-match assertion is what makes this a ratchet rather than a ceiling: a new tkinter type on the surface fails as a fresh leak, and a sealed element whose entry was not deleted fails as stale, so the allowlist can only ever track the true residue downward. The two halves are reported by name because the fix differs -- a fresh leak is sealed or taken to a ruling, a stale entry is simply deleted as the proof its work is done. Runtime introspection rather than an AST scan because the surface is defined by what a caller can actually reach -- re-exports, inheritance, and component handles included -- which only the object graph knows; FORWARDREF format keeps annotations resolvable when their names live under TYPE_CHECKING (BaseWidget.tk's _tkinter.TkappType is the standing case).
    """
    found, _ = _audit()
    report = ""
    if fresh := sorted(found - ALLOWLIST):
        report += "\nfresh leaks (seal them, or allowlist by ruling):\n  " + "\n  ".join(fresh)
    if stale := sorted(ALLOWLIST - found):
        report += "\nstale allowlist entries (sealed; delete them):\n  " + "\n  ".join(stale)
    assert found == ALLOWLIST, report


def test_the_audit_walked_the_surface_it_claims_to() -> None:
    """The walk reaches exported classes, inherited bases, and component handles.

    The guard against the main test silently covering nothing: an import rename, a change to how re-exports are declared, or a regression in the closure walk could empty the audit and turn its equality green with both sides vacant. Each sentinel pins one distinct route into the walk -- direct export, MRO ascent, annotation closure, module functions, aliases -- so the route that broke is named by the sentinel that goes missing.
    """
    _, walked = _audit()
    expected = {
        "Entry",  # exported directly from tkfacade
        "Frame",
        "Window",
        "Widget",  # reachable only through the MRO of exported classes
        "GridWidget",
        "TreeColumnHeading",  # reachable only through a property's return annotation
        "ImageLabel",
        "MediaVariables",
        "get_root",  # a module-level function
        "Anchor",  # a type alias
    }
    assert expected <= walked, f"missing from walk: {sorted(expected - walked)}"
