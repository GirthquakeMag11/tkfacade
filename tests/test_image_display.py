""":class:`~tkfacade.ImageDisplay` on the timed-media contract's terms.

The timeline is what these cover: a reel of frames laid end to end, and
the transport methods reading and moving through it. Animations are
encoded in memory, each frame a distinct colour so GIF optimization
cannot merge two and collapse the reel this asserts on.

Everything needs a real Tk interpreter — frames are Tk images and the
tick is an ``after`` job — so the suite runs on the ``window`` fixture
under the ``gui`` marker. libmpv is not needed by the class, only by the
package import that reaches it.
"""

import gc
import io
import time
from collections.abc import Callable

import pytest
from PIL import Image

import tkfacade
from conftest import Pump
from tkfacade.media import ImageDisplay
from tkfacade.widget import Surface
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
    """An 8x4 solid red PNG: one frame, and so no timeline at all."""
    buffer = io.BytesIO()
    Image.new("RGB", (8, 4), (255, 0, 0)).save(buffer, format="PNG")
    return buffer.getvalue()


def _drawn(window: tkfacade.Window, pump: Pump) -> ImageDisplay:
    """An empty display, laid out and reviewed until its surface is drawing."""
    display = ImageDisplay(window, width=64, height=32)
    display.grid(row=0, column=0)
    pump(window)
    Surface.review_all()
    pump(window)
    return display


def _eventually(window: tkfacade.Window, pump: Pump, condition: Callable[[], bool]) -> bool:
    """Pump the loop until ``condition`` holds or three seconds pass."""
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if condition():
            return True
        pump(window)
        time.sleep(0.01)
    return condition()


def test_an_animations_duration_is_its_frame_delays_added_up(
    window: tkfacade.Window, pump: Pump
) -> None:
    """``duration`` is the sum of the reel's delays, and the image's size is reported.

    The timeline is the whole of what ImageDisplay adds over Label, which has no concept of one, and the delays are the only thing it can be built from. Asserted through the public duration rather than the delay list because the sum is the contract and the list is not: a reel stored in seconds, or one that forgot the last frame, would both keep a plausible-looking list. The size assertion rides along to pin that media_width/media_height report the image and not the widget, which is 64x32 here precisely so the two cannot be confused.
    """
    display = _drawn(window, pump)

    display.play(_gif_bytes(100, 200, 300))

    assert abs(display.duration - 0.6) < 0.001
    assert (display.media_width, display.media_height) == (2, 1)


def test_a_seek_reports_the_asked_position_and_shows_the_frame_it_lands_in(
    window: tkfacade.Window, pump: Pump
) -> None:
    """A seek keeps the exact position asked for while the frame quantizes to the reel.

    The two halves of the seek contract, which pull in opposite directions: the contract promises the position lands exactly, while a reel can only show whole frames. 0.25 is chosen to fall inside the middle frame without touching either boundary -- the frames start at 0, 0.1 and 0.3 -- so an off-by-one in the frame search shows up as index 0 or 2, and a position quantized to the frame's start shows up as 0.1.
    """
    display = _drawn(window, pump)
    display.play(_gif_bytes(100, 200, 300))

    display.seek(0.25)

    assert abs(display.position - 0.25) < 0.001
    assert display.index == 1


def test_skips_accumulate_inside_a_single_frame(window: tkfacade.Window, pump: Pump) -> None:
    """Repeated skips too small to leave a frame still add up.

    The contract says repeated skips accumulate exactly and never collapse to the last delta, and a frame reel is where that is easiest to get wrong: were the position quantized to the frame it lands in, each skip would re-read 0.0 as its base and the three would collapse to one, with nothing else looking any different. Three skips inside the first frame is the smallest shape that distinguishes 0.06 from 0.02, and the index assertion is what says they never left the frame -- so the accumulation cannot be coming from the frame boundary instead.
    """
    display = _drawn(window, pump)
    display.play(_gif_bytes(100, 200, 300))
    display.pause()

    display.skip(0.02)
    display.skip(0.02)
    display.skip(0.02)

    assert abs(display.position - 0.06) < 0.001
    assert display.index == 0


def test_a_still_image_answers_the_transport_methods_as_no_ops(
    window: tkfacade.Window, pump: Pump
) -> None:
    """A one-frame image has no timeline, so nothing the transport does moves it.

    The entry this class closes asks for exactly this: the transport methods answering as no-ops on a still image, as Label already does. Every one of them is called in a chain -- which also pins that each returns self, the contract's other promise -- and the assertions are that nothing moved. duration is 0.0 rather than the frame's own delay because a one-frame reel has nowhere to be, and it is that 0.0 the no-op runs through: every transport method reads it as "no timeline". The size still reports, since a still is displayed like any other image.
    """
    display = _drawn(window, pump)
    display.play(_png_bytes())

    display.play().resume().toggle_pause().seek(1.0).skip(1.0)

    assert display.duration < 0.001
    assert display.position < 0.001
    assert display.paused is True
    assert display.index == 0
    assert (display.media_width, display.media_height) == (8, 4)


def test_a_display_with_no_image_is_safe_to_drive(window: tkfacade.Window, pump: Pump) -> None:
    """A display never given an image answers empty and survives the whole transport.

    The empty display is the state a caller reaches by constructing one and laying it out before deciding what to show, so every method has to tolerate it; an IndexError off an empty frame list is what this would catch. Distinct from the still-image case above because the two fail differently -- a still has a reel to index into and this has none -- and the chain runs stop() as well, which the still-image test deliberately leaves out so its assertions can still see a loaded image.
    """
    display = _drawn(window, pump)

    display.play().pause().resume().toggle_pause().stop().seek(1.0).skip(1.0)

    assert display.wrapper is None
    assert display.source is None
    assert display.duration < 0.001
    assert display.paused is True
    assert (display.media_width, display.media_height) == (0, 0)


def test_stop_unloads_the_reel_and_a_later_play_decodes_it_again(
    window: tkfacade.Window, pump: Pump
) -> None:
    """``stop`` clears the frames while ``source`` keeps naming them for ``play``.

    stop's contract is that the readout zeroes at once and a play-shaped call brings the same media back from the start, which is what makes a transport bar's stop button recoverable through its own play button. The stopped wrapper and readout are captured before the reload rather than asserted after it, because the reload is what would hide a stop that zeroed nothing; the readout is the larger of duration and position so that one assertion covers both and neither can pass by staying behind the other. `is source` rather than `==`: what matters is that the original object was kept to decode again, and comparing GIF bytes by value would pass even if the display had re-encoded them.
    """
    display = _drawn(window, pump)
    source = _gif_bytes(100, 200, 300)
    display.play(source)

    display.stop()
    stopped_wrapper = display.wrapper
    stopped_readout = max(display.duration, display.position)
    display.play()

    assert stopped_wrapper is None
    assert stopped_readout < 0.001
    assert display.source is source
    assert abs(display.duration - 0.6) < 0.001
    assert display.position < 0.001


def test_an_animation_with_loop_off_stops_on_its_last_frame(
    window: tkfacade.Window, pump: Pump
) -> None:
    """Playback with ``loop`` off runs out on the last frame and reads paused.

    The end of a reel that does not loop is the image display's version of mpv's keep_open pause: it holds the last frame rather than blanking, and a play-shaped call is the door back out, rewinding rather than doing nothing -- the same shape VideoDisplay answers at EOF, and the one a caller writing over both relies on. The delays are the shortest the decoder will keep (MIN_FRAME_DELAY is 20ms), so the reel runs out inside a pumped loop; _eventually is what waits for the after jobs, since the ticks are real timers and no synchronous call advances them.
    """
    display = _drawn(window, pump)
    display.play(_gif_bytes(20, 20, 20))
    display.loop = False

    assert _eventually(window, pump, lambda: display.paused)
    assert display.index == 2

    display.play()

    assert display.paused is False
    assert display.index == 0


def test_volume_and_muted_are_kept_and_clamped_but_inert(
    window: tkfacade.Window, pump: Pump
) -> None:
    """The audio members hold what they are given without touching playback.

    An image has no audio, and the decision recorded for this class is that volume and muted are answered inertly rather than refused, so that controls written against AbstractMediaDisplay bind here as they do to a video. Inert has to be pinned from both sides: the values are kept and clamped like a video's -- 250 is out of range on purpose -- and nothing else about the display moves, which is what the position and paused assertions after the writes are for. A volume setter that reached into playback would leave those two intact only by accident. The explicit pause is what makes the pair deterministic: read off a running display they would depend on no timer having fired between the writes.
    """
    display = _drawn(window, pump)
    display.play(_gif_bytes(100, 200, 300))
    display.seek(0.25)
    display.pause()

    display.volume = 250.0
    display.muted = True

    assert abs(display.volume - 100.0) < 0.001
    assert display.muted is True
    assert abs(display.position - 0.25) < 0.001
    assert display.paused is True


def test_a_seek_after_a_stop_is_held_for_the_reload(window: tkfacade.Window, pump: Pump) -> None:
    """``stop(); seek(x)`` holds the cue, and the reload ``play()`` performs lands on it.

    The contract promises seek holds a request while there is no timeline and applies it once one arrives, and stop is the state that produces one here: the frames are gone, so duration reads 0 and there is nowhere to move until play() decodes the image again. That makes stop-then-cue-then-resume work on an image exactly as it does on a video, which is the point of the two answering one contract. play(new) is not the shape tested, because the contract has it discard a held request rather than apply it -- a position measured against an image that is being replaced means nothing. The held read is taken before the reload, since the documented promise is that the readout does not move in the meantime.
    """
    display = _drawn(window, pump)
    display.play(_gif_bytes(100, 200, 300))

    display.stop()
    display.seek(0.25)
    held = display.position
    display.play()

    assert held < 0.001
    assert abs(display.position - 0.25) < 0.001
    assert display.index == 1


def test_a_display_holds_its_frames_after_the_source_is_dropped(
    window: tkfacade.Window, pump: Pump, root: Root
) -> None:
    """The decoded frames stay live Tk images after the source bytes are dropped.

    media/_image.py records that Tk keeps only a weak reference to an image, so a widget displaying one has to hold it: were the frames built and not stored, every one would be collected and the display would silently blank. Nothing in the class's own source would look different, and no other test here would fail -- position, duration and index all keep working over frames Tk no longer has. The source is held in a local and dropped before the collect, so refcounting cannot rescue the frames through the bytes; the name is read off the view widget and checked against the interpreter's own image list rather than through the display's accessors, which would anchor the very objects the collect is meant to threaten.
    """
    source = _gif_bytes(100, 200, 300)
    display = _drawn(window, pump)
    display.play(source)
    shown = str(display._view.cget("image"))

    del source
    gc.collect()

    assert shown != ""
    assert shown in {str(name) for name in root.tk.call("image", "names")}


class _LockedDisplay(ImageDisplay):
    """An image display that withholds its position, as a scrub bar mid-drag would."""

    @property
    def position_locked(self) -> bool:
        return True


def test_position_locked_withholds_the_reported_position_but_not_the_frame(
    window: tkfacade.Window, pump: Pump
) -> None:
    """A seek still lands on its frame while the published position stays put.

    position_locked is the one member the base supplies concretely, and every position write the image display publishes runs through _publish_position, which consults it. The subclass stands in for the only caller the hook exists for — a holder of the position, like a scrub bar mid-drag — and the two assertions pull the frame and the published position apart: the seek moved the frame to index 1 while the reported position never left 0.0, which is exactly the division the lock exists to draw.
    """
    display = _LockedDisplay(window, width=64, height=32)
    display.grid(row=0, column=0)
    pump(window)
    Surface.review_all()
    pump(window)
    display.play(_gif_bytes(100, 200, 300))

    display.seek(0.25)

    assert display.index == 1
    assert display.position < 0.001


def test_auto_size_fits_the_display_to_the_image(window: tkfacade.Window, pump: Pump) -> None:
    """With ``auto_size`` on, playing an image sizes the display to it.

    _resize_to_media reads the media's own reported size and writes it back as the display's size request, and _load calls it whenever auto_size is on — so a caller can turn the option on before deciding what to show, in either order, and the display follows the image. The 8x4 size is the image's own, deliberately not the 64x32 the display was built with, so the assertion cannot pass by the display simply keeping its constructed size.
    """
    display = _drawn(window, pump)
    display.auto_size = True

    display.play(_png_bytes())

    assert (display.width, display.height) == (8, 4)


def test_auto_size_limit_scales_the_fit_down_and_never_up(
    window: tkfacade.Window, pump: Pump
) -> None:
    """The fit honours the limit in both directions.

    The same factor is applied to both axes — 8x4 under a 4x4 limit halves to 4x2, keeping the image's shape — and the factor is never above 1, so a limit larger than the image leaves the image at its own size rather than upscaling. Both directions matter: a caller setting a limit expects the fit to respect it, and one clearing it expects the image not to balloon.
    """
    display = _drawn(window, pump)
    display.auto_size = True

    display.auto_size_limit = (4, 4)
    display.play(_png_bytes())
    capped = (display.width, display.height)

    display.auto_size_limit = (1000, 1000)
    display.play(_png_bytes())
    uncapped = (display.width, display.height)

    assert capped == (4, 2)
    assert uncapped == (8, 4)


def test_obstructed_pause_stops_and_restores_a_hidden_animation(
    window: tkfacade.Window, pump: Pump
) -> None:
    """With the option on, a suppressed surface stops the timer and showing it resumes.

    The obstruction machinery is Surface's; this pins the image display's half of it — that obstructed_pause translates a hidden surface into a stopped timer. grid_remove plus the review stand in for a real cover, the same substitution test_video_display.py makes, since a pumped test loop delivers no genuine visibility events. The hidden read is taken after the blank, and the restored read after the surface is gridded back, so both directions of the policy are exercised; the mapped check beside it says the blank really happened rather than the flag flipping on its own.
    """
    display = ImageDisplay(window, obstructed_pause=True, width=64, height=32)
    display.grid(row=0, column=0)
    pump(window)
    Surface.review_all()
    pump(window)
    display.play(_gif_bytes(50, 50, 50))
    running: bool = display.paused
    assert not running

    display._tk.grid_remove()
    pump(window)
    Surface.review_all()
    pump(window)
    hidden: bool = display.paused
    hidden_mapped: bool = bool(display._surface.winfo_ismapped())

    display._tk.grid()
    pump(window)
    Surface.review_all()
    pump(window)
    restored: bool = display.paused

    assert (hidden, hidden_mapped) == (True, False)
    assert restored is False


def test_a_still_swapped_into_a_running_animation_reports_paused(
    window: tkfacade.Window, pump: Pump
) -> None:
    """``play`` of a still over a running animation stops the reel honestly.

    The one state a play-shaped call used to leave dishonest: _start_playback returned on a reel of fewer than two frames before cancelling the old reel's pending tick or writing the pause mirror, so replacing a running animation with a still left paused reading False for good, a control bound to it showing the pause glyph over a motionless image, and toggle_pause one-way. The sleep outlasts the swapped-out reel's 50ms frame so a stray tick still armed against the new reel would fire inside the test and flip the mirror; the toggle assertion pins that a still never animates however often it is poked.
    """
    display = _drawn(window, pump)
    display.play(_gif_bytes(50, 50, 50))
    running: bool = display.paused
    assert not running

    display.play(_png_bytes())

    stopped: bool = display.paused
    assert stopped
    toggled: bool = display.toggle_pause().paused
    assert toggled
    time.sleep(0.08)
    pump(window)
    settled: bool = display.paused
    assert settled
