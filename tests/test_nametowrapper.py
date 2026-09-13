""":meth:`~tkfacade.widget.BaseWidget.nametowrapper`: resolving a Tk path to its wrapper.

Every wrapper enters a class-level registry as it is built and leaves
it when Tk destroys the widget underneath, so the contracts here are
about liveness as much as lookup: what a path answers with, what a
destroyed widget answers with, what a second interpreter answers with
for the identical path, and how long the entry keeps a wrapper the
caller has let go. Everything needs real
widgets on a real interpreter, so the suite rides the ``window``
fixture under the ``gui`` marker.
"""

import gc
import weakref

import pytest

import tkfacade
from tkfacade.widget import BaseWidget, Surface
from tkfacade.window._root import Root

pytestmark = pytest.mark.gui


def test_a_wrapper_answers_to_everything_that_names_its_path(window: tkfacade.Window) -> None:
    """A path string, a Tk widget and a wrapper all resolve to the same wrapper.

    The three spellings are one contract: nametowidget takes str(name) of whatever it is handed, and the wrapper-side counterpart has to accept the same three things or callers converting an event's widget field would have to spell the conversion themselves. The wrapper case matters most -- BaseWidget.__str__ is the widget path, so a wrapper is already a legal Tcl argument everywhere else.
    """
    label = tkfacade.TextLabel(window, text="hi")

    assert window.nametowrapper(str(label)) is label
    assert window.nametowrapper(label._tk) is label
    assert window.nametowrapper(label) is label


def test_the_root_is_registered_under_its_own_path(window: tkfacade.Window, root: Root) -> None:
    """The root wrapper answers to ``"."``, the path Tk gives every interpreter.

    Root is a BaseWidget like any other and registers on the same terms, which is what lets the eviction handler recognise the root by path and release the whole interpreter. Asserted separately because "." is the one path the library never generates itself.
    """
    assert window.nametowrapper(".") is root


def test_each_interpreter_answers_with_its_own_wrapper(window: tkfacade.Window) -> None:
    """Two roots hand out the same window path, and each resolves to its own.

    The whole reason the registry key carries the interpreter. Every root names its first toplevel .!basewindow, so a registry keyed on the path alone would have the second root's window overwrite the first's and hand the wrong wrapper to both. The paths are asserted equal first, so a future Tk that numbered them apart would fail here rather than let the real claim pass vacuously.
    """
    other = Root()
    held = tkfacade.Window(title="other", root=other)
    try:
        assert str(held) == str(window)
        assert window.nametowrapper(str(window)) is window
        assert held.nametowrapper(str(held)) is held
    finally:
        held.destroy()


def test_a_destroyed_widget_leaves_the_registry(window: tkfacade.Window) -> None:
    """A widget's destruction takes its wrapper's entry with it.

    Tk delivers <Destroy> synchronously from inside destroy(), so the entry is gone by the time destroy() returns and no pump is needed. Registered before the destroy so the eviction half cannot pass vacuously against a wrapper that never enrolled. This is what keeps "live instances" true: without it the registry would hand back wrappers over freed Tk windows.
    """
    label = tkfacade.TextLabel(window, text="hi")
    path = str(label)
    assert window.nametowrapper(path) is label

    label._tk.destroy()

    with pytest.raises(KeyError):
        window.nametowrapper(path)


def test_a_widget_no_wrapper_was_built_for_is_not_found(window: tkfacade.Window) -> None:
    """A widget the library made for its own use has no entry to answer with.

    A TextBox wraps its outer frame; the tk.Text inside it and the scrollbars beside it are the library's own plumbing and no wrapper was ever built for them. The lookup says so by raising, exactly as nametowidget raises for a name it cannot resolve, rather than walking up to the nearest wrapped ancestor -- a caller wanting the owning wrapper is asking a different question than this one.
    """
    box = tkfacade.TextBox(window, text="hi")

    assert window.nametowrapper(box) is box
    with pytest.raises(KeyError):
        window.nametowrapper(box._text)


def test_a_dead_interpreter_leaves_the_registry(window: tkfacade.Window) -> None:
    """Destroying a root drops every entry still keyed to its interpreter.

    The registry key holds the interpreter object itself, so an entry outliving its widget would pin a dead TkappType and the Tcl state behind it for the life of the process -- one per root an application cycles through, invisible in any single-root run and masked in this suite by conftest clearing the registry by hand. Membership is asserted before the destroy so a registry that never enrolled the interpreter could not pass the eviction half vacuously, and the window is destroyed rather than the root so the release is driven through the same last-window cascade a real application takes.
    """
    other = Root()
    held = tkfacade.Window(title="other", root=other)
    try:
        tkfacade.TextLabel(held, text="hi")
        interpreter = held._tk.tk
        assert any(key[0] is interpreter for key in BaseWidget._wrappers)
    finally:
        held.destroy()

    assert not any(key[0] is interpreter for key in BaseWidget._wrappers)


def test_every_wrapper_class_registers_itself(window: tkfacade.Window, root: Root) -> None:
    """One of each concrete wrapper is reachable by its own path.

    Registration hangs off each concrete __init__ calling super() last, which is a line a wrapper added later can simply be missing -- and nothing else would notice, since every other contract that class has still holds. Sweeping the whole hierarchy here is what turns that omission into a failure. VideoDisplay is absent on purpose: it registers through Surface's __init__, which is covered, and constructing it needs libmpv.
    """
    built: list[BaseWidget] = [
        root,
        window,
        tkfacade.Entry(window),
        tkfacade.TitleEntry(window),
        tkfacade.TextBox(window),
        tkfacade.Frame(window),
        tkfacade.TabFrame(window),
        tkfacade.StackFrame(window),
        tkfacade.Tree(window),
        tkfacade.Table(window),
        tkfacade.TextLabel(window, text="hi"),
        tkfacade.ImageLabel(window),
        tkfacade.PercentageBasedProgressBar(window, orient="horizontal", length=100),
        tkfacade.ItemBasedProgressBar(window, orient="horizontal", length=100, maximum=10),
        tkfacade.Menubutton(window, "File"),
        tkfacade.MediaPlayer(window, width=64, height=32),
        Surface(window),
    ]

    assert [window.nametowrapper(str(wrapper)) for wrapper in built] == built


def test_a_widget_is_looked_up_on_the_interpreter_it_belongs_to(window: tkfacade.Window) -> None:
    """A wrapper from another root resolves to itself, not to this root's namesake.

    A path string cannot say which interpreter it came from, so one is chosen for it; a widget can say, and now does. Taking only str() of a widget threw that away and re-attached this wrapper's interpreter, so asking one root about another root's window answered with the namesake at the same path -- a wrong wrapper returned in silence, worse than the miss a caller could have handled. The paths are asserted equal first so the claim cannot pass on two roots that happened to differ.
    """
    other = Root()
    held = tkfacade.Window(title="other", root=other)
    try:
        assert str(held) == str(window)
        assert window.nametowrapper(held) is held
        assert window.nametowrapper(held._tk) is held
    finally:
        held.destroy()


def test_a_relative_name_resolves_against_the_widget_asked(
    window: tkfacade.Window, root: Root
) -> None:
    """A name not starting with a dot is taken as relative, as nametowidget takes it.

    BaseWidget.children hands back exactly these relative keys, so an absolute-only lookup left two members of one class unable to compose, and the refusal read as "no wrapper there" rather than "wrong spelling". The root case is the one the code needs care for: its path is already "." and naive joining would ask for "..!basewindow".
    """
    label = tkfacade.TextLabel(window, text="hi")
    name = str(label).rsplit(".", 1)[1]

    assert window.nametowrapper(name) is label
    assert root.nametowrapper(f"{window._tk.winfo_name()}.{name}") is label


def test_a_miss_names_the_path_it_could_not_resolve(window: tkfacade.Window) -> None:
    """The KeyError carries the resolved path, as nametowidget carries the name.

    A bare registry lookup raised with the internal key -- a two-tuple holding an interpreter repr -- which is not what the docstring promises and tells a caller nothing they can read. The args are asserted rather than the message so this stays about the payload.
    """
    with pytest.raises(KeyError) as caught:
        window.nametowrapper(".!basewindow.!nope")

    assert caught.value.args == (".!basewindow.!nope",)


def test_the_registry_is_the_only_thing_holding_a_wrapper(window: tkfacade.Window) -> None:
    """A wrapper dropped by its caller lives exactly as long as its registry entry.

    The eviction watch used to close over the wrapper, and tkinter parks a binding's callable in the widget's Tcl command table, so every wrapper was anchored there for its widget's whole life whatever the registry did -- invisible, and enough to make test_text's dropped-wrapper test pass with the fix it guards deleted. The watch closes over the Tk widget instead. The subject must be a wrapper that binds nothing of its own -- a converted value-bearing wrapper anchors itself through its Destroyed release binding, legitimately, so the progress bar stopped qualifying at its conversion -- and Frame qualifies for as long as it stays bind-free. The one-slot subclass exists because every wrapper class is slotted without __weakref__: it lets the test probe the wrapper itself instead of a held member standing in.
    """

    class Probed(tkfacade.Frame):
        __slots__ = ("__weakref__",)

    frame = Probed(window)
    key = (frame._tk.tk, str(frame))
    doomed = weakref.ref(frame)

    del frame
    gc.collect()
    assert doomed() is not None

    BaseWidget._wrappers.pop(key, None)
    gc.collect()
    assert doomed() is None
