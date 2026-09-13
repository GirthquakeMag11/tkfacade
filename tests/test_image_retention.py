"""Images set through the wrappers survive garbage collection.

Tk stores only an image's *name*; the Python object owns the image
itself and deletes it from the interpreter when collected, so a widget
holding a name whose object has gone silently blanks. Every wrapper
that accepts an image therefore keeps a strong reference — for the tree
that is the :class:`~tkfacade.media.ImageWrapper` it built, which holds the
``PhotoImage`` it handed Tk — and these tests set one from a temporary
that nothing else holds, then collect and ask the interpreter whether
the image is still there.

Names are read off Tk rather than through the wrapper's own accessor
throughout, which is what keeps the measurement honest: the accessors
now answer with the wrapper itself, so binding one to a local would
anchor the very object the collect is supposed to threaten.

Everything here needs a live Tk interpreter and carries the ``gui``
marker.
"""

import gc
import io
import tkinter as tk

import pytest
from PIL import Image

import tkfacade
from tkfacade.tree import TreeColumnSpec
from tkfacade.window import Root

pytestmark = pytest.mark.gui


def _png() -> bytes:
    """An 8x8 solid red PNG, as encoded bytes."""
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (255, 0, 0)).save(buffer, format="PNG")
    return buffer.getvalue()


def _live_images(root: Root) -> set[str]:
    """The names of every image the interpreter currently holds."""
    return {str(name) for name in root.tk.call("image", "names")}


def _name(answer: object) -> str:
    """The Tk image name in an ``item``/``heading`` answer, holding nothing.

    Args:
        answer (object): What Tk gave back for an ``image`` option — a
            one-element tuple while an image is set, a bare ``""``
            once it is cleared, so an empty tuple never arrives.

    Returns:
        The image's name, or ``""`` when none is set.
    """
    return str(answer[0]) if isinstance(answer, tuple) else str(answer)


def test_a_row_image_survives_collection(root: Root, window: tkfacade.Window) -> None:
    """A row image set from a temporary is still a live Tk image after a collect.

    The path that already retained, kept as the reference the other two are measured against — if Tk's weak-image behaviour ever changed, all three tests would go green together and this one says so first. The source is bare bytes assigned straight into the property, so the only thing holding the wrapper the setter builds — and through it the PhotoImage — is the tree's own store, which is the claim.
    """
    tree = tkfacade.Tree(window, columns=(TreeColumnSpec(name="a"),))
    row = tree.insert(a="1")

    row.image = _png()
    name = _name(tree._treeview.item(row.iid, "image"))
    gc.collect()

    assert name != ""
    assert name in _live_images(root)


def test_a_heading_image_survives_collection(root: Root, window: tkfacade.Window) -> None:
    """A column heading's image set from a temporary survives a collect.

    Reading the heading back is not enough on its own: Tk answers with the stored *name* whether or not an image still answers to it, so a blanked heading and a live one are indistinguishable from the wrapper's own accessor. Asking the interpreter for its image names is what separates them, and is why this test reaches past the wrapper.
    """
    tree = tkfacade.Tree(window, columns=(TreeColumnSpec(name="a"),))
    column = tree.column("a")
    assert column is not None

    column.heading.image = _png()
    name = _name(tree._treeview.heading("a", "image"))
    gc.collect()

    assert name != ""
    assert name in _live_images(root)


def test_a_tag_image_survives_collection(root: Root, window: tkfacade.Window) -> None:
    """A tag image set from a temporary survives a collect.

    The third entry point, and the one with no natural release: a row image goes when its row does and a heading image when its column is dropped, but Tk offers no way to retire a tag, so the reference is held for the tree's life. That asymmetry is deliberate and documented on ``configure_tag``; what this pins is only that the image is there at all.
    """
    tree = tkfacade.Tree(window, columns=(TreeColumnSpec(name="a"),))
    tree.configure_tag("warn", image=_png())

    name = str(tree._treeview.tag_configure("warn", "image"))
    gc.collect()

    assert name != ""
    assert name in _live_images(root)


def test_dropping_a_column_releases_its_heading_image(root: Root, window: tkfacade.Window) -> None:
    """A dropped column stops holding its heading image alive.

    The other half of retention, and the half that makes it a cache rather than a leak: holding forever would be as wrong as not holding at all, just harder to notice. Dropping the column is the documented release point, and a second column exists so the drop is a real reconfigure rather than emptying the tree.
    """
    tree = tkfacade.Tree(window, columns=(TreeColumnSpec(name="a"), TreeColumnSpec(name="b")))
    column = tree.column("a")
    assert column is not None
    column.heading.image = _png()
    name = _name(tree._treeview.heading("a", "image"))

    tree.drop_column("a")
    gc.collect()

    assert name not in _live_images(root)


def test_a_refused_delete_evicts_nothing(root: Root, window: tkfacade.Window) -> None:
    """``delete(ROOT)`` raises and leaves images and detach records standing.

    delete used to evict the whole doomed set's bookkeeping before Tk passed judgement, and the walk tolerates ROOT where Tk refuses it — so a caller who tried delete(ROOT), caught the documented error, and carried on found row images silently blanking at the next collection and hidden rows unrestorable. The image half is asserted through the interpreter after a collect because that is when the dropped strong reference actually bites; the name is taken before the refused delete for the same reason the other tests take it off Tk — a live wrapper in a local would survive the collect on its own. The detach half goes through show_row restoring the hidden row to its recorded position.
    """
    tree = tkfacade.Tree(window, columns=(TreeColumnSpec(name="a"),))
    row = tree.insert(a="1")
    row.image = _png()
    name = _name(tree._treeview.item(row.iid, "image"))
    hidden = tree.insert(a="2")
    tree.hide_row(hidden.iid)

    with pytest.raises(tk.TclError):
        tree.delete(tkfacade.ROOT)
    gc.collect()

    assert name in _live_images(root)
    tree.show_row(hidden.iid)
    assert hidden.index == 1
