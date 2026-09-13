""":class:`~tkfacade.ImageLabel`: the image-only half of the split Label.

The split moved the old ``Label.image`` view's whole surface — frame
cache, playback, transformations, retention — onto a widget of its own.
These pin that surface: playback as a no-op on a still and on an empty
label, ``set`` swapping a source, the ``<Destroy>`` binding cancelling a
pending tick, transformations replacing the wrapper, and the
image-retention claim `media/_image.py` makes for every displaying
widget. Animations are encoded in memory as distinct-colour GIF frames,
as in `test_image_display.py`, so GIF optimization cannot collapse the
reel. Everything needs a real Tk interpreter — frames are Tk images and
the tick is an ``after`` job — so the suite rides the ``window`` fixture
under the ``gui`` marker.
"""

import gc
import io

import pytest
from PIL import Image

import tkfacade
from conftest import Pump
from tkfacade.window import Root

pytestmark = pytest.mark.gui


def _gif_bytes(*durations: int) -> bytes:
    """Encode one solid-colour 2x1 GIF frame per entry of ``durations``.

    Each frame gets a distinct colour — identical frames would be merged
    by GIF optimization, collapsing the frame count and summing the
    durations.

    Args:
        *durations (int): Per-frame display times in milliseconds.

    Returns:
        The encoded GIF.
    """
    frames = [Image.new("RGB", (2, 1), (index * 40, 0, 0)) for index in range(len(durations))]
    buffer = io.BytesIO()
    frames[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=list(durations),
    )
    return buffer.getvalue()


def _png_bytes() -> bytes:
    """An 8x4 solid red PNG: one frame, and so no animation at all."""
    buffer = io.BytesIO()
    Image.new("RGB", (8, 4), (255, 0, 0)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_a_still_image_answers_playback_as_no_ops(window: tkfacade.Window, pump: Pump) -> None:
    """A one-frame image never plays, and the transport leaves it unchanged.

    The transport methods each guard on the frame count, so a still is safe to drive: play refuses a reel of fewer than two frames, pause cancels nothing, and stop rewinds to the frame already shown. The dimensions report the image's own size — 8x4, deliberately not the widget's — which pins that a still is displayed like any other image while the playback members stay put.
    """
    label = tkfacade.ImageLabel(window, image=_png_bytes())
    label.grid(row=0, column=0)
    pump(window)

    label.play().pause().stop()

    assert label.playing is False
    assert label.index == 0
    assert (label.width, label.height) == (8, 4)


def test_a_label_with_no_image_is_safe_to_drive(window: tkfacade.Window, pump: Pump) -> None:
    """An empty label answers the whole transport with no-ops and no frames.

    The empty label is the state a caller reaches by building one and laying it out before deciding what to show, so every method has to tolerate it; an IndexError off an empty frame list is what this would catch. Distinct from the still-image case above because the two fail differently — a still has a frame cache to index into and this has none.
    """
    label = tkfacade.ImageLabel(window)
    label.grid(row=0, column=0)
    pump(window)

    label.play().pause().stop()

    assert label.playing is False
    assert label.wrapper is None
    assert (label.width, label.height) == (0, 0)


def test_set_swaps_the_source_in_place(window: tkfacade.Window, pump: Pump) -> None:
    """``set`` replaces the image, decodes an animation whole, and None clears it.

    set is the swapping door: it re-decodes from the new source, rewinds to the transformed first frame rather than playing on, and None clears the image entirely. The three-frame count pins that an animation passes through whole, the playing and index assertions that a swap is not a play, and the cleared half that the transport still answers after the image is gone.
    """
    label = tkfacade.ImageLabel(window, image=_png_bytes())
    label.grid(row=0, column=0)
    pump(window)
    first = label.wrapper

    label.set(_gif_bytes(100, 200, 300))

    assert label.wrapper is not first
    assert (label.width, label.height) == (2, 1)
    assert len(list(label.iter_frames())) == 3
    assert label.playing is False
    assert label.index == 0

    label.set(None)

    assert label.wrapper is None
    assert (label.width, label.height) == (0, 0)


def test_destroying_the_label_cancels_a_pending_tick(window: tkfacade.Window, pump: Pump) -> None:
    """The label's own ``<Destroy>`` binding stops a running animation.

    A pending tick outlives the widget otherwise: it would fire on a destroyed label and, until it did, hold every decoded frame alive through its own closure. The <Destroy> binding is the only route that fires whatever way the widget dies, so the test destroys the wrapper itself and pins that the after job was cancelled rather than merely that no error surfaced — which a swallowed background exception would also leave green.
    """
    label = tkfacade.ImageLabel(window, image=_gif_bytes(50, 50, 50))
    label.grid(row=0, column=0)
    pump(window)
    label.play()
    assert label._job is not None

    label.destroy()
    pump(window)

    assert label._job is None


def test_a_transformation_replaces_the_wrapper_and_keeps_the_size(
    window: tkfacade.Window, pump: Pump
) -> None:
    """A transformation swaps the wrapper and decodes from its result.

    Each transformation is pure on the pipeline: the label's wrapper is
    replaced by the returned one, so the dimensions report the
    transformed image and the playback cache follows it.
    """
    label = tkfacade.ImageLabel(window, image=_png_bytes())
    label.grid(row=0, column=0)
    pump(window)
    before = label.wrapper

    label.rotate(180)

    assert label.wrapper is not before
    assert (label.width, label.height) == (8, 4)


def test_a_label_holds_its_frames_alive_against_collection(
    window: tkfacade.Window, pump: Pump, root: Root
) -> None:
    """The decoded frames stay live Tk images after the source is dropped.

    media/_image.py records that Tk keeps only a weak reference to an image, so a displaying widget has to hold its own: were the frames built and not stored, every one would be collected and the label would silently blank. The source is held in a local and dropped before the collect, so refcounting cannot rescue the frames through the bytes; the image name is read off the label widget and checked against the interpreter's own image list rather than through the label's accessors, which would anchor the very objects the collect is meant to threaten.
    """
    source = _gif_bytes(100, 200, 300)
    label = tkfacade.ImageLabel(window, image=source)
    label.grid(row=0, column=0)
    pump(window)
    shown = str(label._tk.cget("image")[0])

    del source
    gc.collect()

    assert shown != ""
    assert shown in {str(name) for name in root.tk.call("image", "names")}
