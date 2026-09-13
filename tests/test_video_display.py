""":class:`~tkfacade.VideoDisplay`'s pause policy, driven against a real idle mpv.

No media file is needed: mpv's ``pause`` property reads and writes on
an idle core, which is exactly the state these contracts live in. The
obstruction dance needs real mapping, so everything runs on the
``window`` fixture under the ``gui`` marker.
"""

import sys
import time
import wave
from collections.abc import Callable
from pathlib import Path

import pytest

import tkfacade
from conftest import Pump
from tkfacade.media import VideoDisplay
from tkfacade.widget import Surface

pytestmark = [
    pytest.mark.gui,
    pytest.mark.skipif(
        sys.platform == "win32",
        reason=(
            "mpv.terminate() crashes the interpreter on Windows "
            "(access violation in MPVEventHandlerThread during "
            "fixture teardown — see the media teardown notes)"
        ),
    ),
]


def _silence_wav(directory: Path) -> str:
    """Write one second of silent mono audio and return its path.

    Audio-only on purpose: mpv loads it with ``ao=null`` and no video
    output at all, which is what keeps a real load viable under a
    headless test display.
    """
    path = directory / "silence.wav"
    with wave.open(str(path), "wb") as sink:
        sink.setnchannels(1)
        sink.setsampwidth(2)
        sink.setframerate(8000)
        sink.writeframes(b"\x00\x00" * 8000)
    return str(path)


def _eventually(window: tkfacade.Window, pump: Pump, condition: Callable[[], bool]) -> bool:
    """Pump the loop until ``condition`` holds or three seconds pass."""
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if condition():
            return True
        pump(window)
        time.sleep(0.05)
    return condition()


def test_obstructed_pause_survives_a_resume_while_hidden(
    window: tkfacade.Window, pump: Pump
) -> None:
    """``resume()`` on a hidden display records the intent but mpv stays paused.

    The policy pause flag survived a deliberate unpause while its pause did not: resume() pushed pause=False to mpv and the re-assertion no-opped because the flag said a policy pause was already in force — so mpv played sound and decoded video for as long as the widget stayed hidden, precisely what the option exists to stop. The review_all calls stand in for the event-driven reviews a real obstruction fires, since a pumped test loop delivers no genuine visibility events on an unmapped frame; mpv's own pause property is the ground truth asserted, because the wrapper-side ``paused`` variable was already right while the backend was wrong.
    """
    display = VideoDisplay(window, obstructed_pause=True, width=320, height=200)
    display.grid(row=0, column=0)
    pump(window)
    Surface.review_all()
    pump(window)
    visible_state = display.obstructed
    assert display.ready and not visible_state
    backend = display._mpv
    assert backend is not None

    display._tk.grid_remove()
    pump(window)
    Surface.review_all()
    pump(window)
    hidden_state = display.obstructed
    assert hidden_state
    assert backend.pause is True

    display.resume()
    pump(window)

    assert backend.pause is True


def test_stop_then_play_restarts_the_file(
    window: tkfacade.Window, pump: Pump, tmp_path: Path
) -> None:
    """After ``stop``, the display reads paused and ``play()`` reloads the file.

    stop clears mpv's playlist while source keeps naming the file, and play() used to push pause flags at an idle core and nothing more — the shipped bar's stop button was unrecoverable through the bar, and programmatic play() contradicted its own "resume the current file". paused-after-stop is asserted because mpv reports no pause change on stop: the honest True is stated by the wrapper, and it is what makes a transport button offer play over the unloaded file. Every backend read is polled through _eventually because loadfile and stop are asynchronous on mpv's side.
    """
    display = VideoDisplay(window, width=320, height=200)
    display.grid(row=0, column=0)
    pump(window)
    Surface.review_all()
    pump(window)
    backend = display._mpv
    assert backend is not None
    backend["ao"] = "null"
    source = _silence_wav(tmp_path)

    display.play(source)
    assert _eventually(window, pump, lambda: backend.path is not None)

    display.stop()
    assert _eventually(window, pump, lambda: backend.path is None)
    assert _eventually(window, pump, lambda: display.paused is True)
    assert display.source == source

    display.play()
    assert _eventually(window, pump, lambda: backend.path is not None)
    assert _eventually(window, pump, lambda: display.paused is False)


def test_stop_and_a_new_load_reset_the_telemetry(
    window: tkfacade.Window, pump: Pump, tmp_path: Path
) -> None:
    """``stop`` zeroes the readout, and a new load never shows the old timeline.

    Every _observe_* handler dropped mpv's None reports, and stop reset nothing itself, so position, duration, and the media sizes kept the unloaded file's last values forever — plausible numbers for a file that no longer existed, with seeks clamped against the dead duration in the window after a switch. The stop half waits on the observers' None-as-reset path; the reload half asserts duration is 0.0 *synchronously* after play, because mpv's own None arrives a pump late and the stale window between load and first report is exactly where the old timeline used to linger. The readouts are compared against a small bound rather than exact zero to keep ruff's float rule; a stale value here would read near the full second, not near nothing.
    """
    display = VideoDisplay(window, width=320, height=200)
    display.grid(row=0, column=0)
    pump(window)
    Surface.review_all()
    pump(window)
    backend = display._mpv
    assert backend is not None
    backend["ao"] = "null"
    source = _silence_wav(tmp_path)

    display.play(source)
    assert _eventually(window, pump, lambda: display.duration > 0.9)

    display.stop()

    assert _eventually(window, pump, lambda: display.duration < 0.1)
    assert display.position < 0.1

    display.play(source)
    assert _eventually(window, pump, lambda: display.duration > 0.9)
    display.play(source)

    assert display.duration < 0.1
    assert _eventually(window, pump, lambda: display.duration > 0.9)


def test_a_seek_right_after_play_lands_once_the_timeline_arrives(
    window: tkfacade.Window, pump: Pump, tmp_path: Path
) -> None:
    """A seek issued in a live backend's load window is held and replayed, not dropped.

    The hold used to be armed only while mpv did not exist, so the resume-at-position idiom — play(path) then seek(saved) — worked for the first file ever loaded and silently started at zero on every later one: the seek raced the async loadfile, mpv refused it, and the refusal was suppressed with nothing held to replay. The display is paused before the seek because a one-second file plays to 0.6 on its own in under a second — only a landed seek can move a paused position, which is what the final pair of assertions pins. The held-not-issued readout check rides the documented "the readout does not move in the meantime".
    """
    display = VideoDisplay(window, width=320, height=200)
    display.grid(row=0, column=0)
    pump(window)
    Surface.review_all()
    pump(window)
    backend = display._mpv
    assert backend is not None
    backend["ao"] = "null"
    source = _silence_wav(tmp_path)

    display.play(source)
    assert _eventually(window, pump, lambda: display.duration > 0.9)

    display.play(source)
    display.pause()
    display.seek(0.6)
    assert display.position < 0.1

    assert _eventually(window, pump, lambda: display.position > 0.5)
    assert display.paused is True


def test_play_after_a_natural_end_starts_the_file_over(
    window: tkfacade.Window, pump: Pump, tmp_path: Path
) -> None:
    """A play-shaped call on a file that finished on its own restarts it.

    keep_open holds a finished file loaded and paused on its last frame, and _ensure_loaded's path-only test saw a loaded file and no-opped — so play(), resume(), and the shipped bar's play button were all dead after a natural end, frozen until a seek or a stop. The fix rewinds instead, and the assertion watches eof-reached itself flip False through an mpv property observer because the direct read races: a silent test file replays to its end faster than a poll can catch it under ao=null, so only the transition — reported on change, however brief — can witness the restart. The observer is registered only after EOF is already held, so the False in the log can come from nothing but the rewind; path stays set because this is a restart, not a stop-and-reload.
    """
    display = VideoDisplay(window, width=320, height=200)
    display.grid(row=0, column=0)
    pump(window)
    Surface.review_all()
    pump(window)
    backend = display._mpv
    assert backend is not None
    backend["ao"] = "null"

    display.play(_silence_wav(tmp_path))
    assert _eventually(window, pump, lambda: bool(backend.eof_reached))

    transitions: list[object] = []
    backend.observe_property("eof-reached", lambda _name, value: transitions.append(value))
    display.play()

    assert _eventually(window, pump, lambda: False in transitions)
    assert backend.path is not None


def test_stop_then_play_in_one_tick_reloads(
    window: tkfacade.Window, pump: Pump, tmp_path: Path
) -> None:
    """``stop().play()`` with no tick between always comes back playing the file.

    mpv's stop returns before the unload completes, so _ensure_loaded, consulted by the same-tick play(), read the still-set path, concluded a file was loaded, and skipped the reload — the stop then completed into an idle core with nothing queued and the paused mirror pushed False: a transport bar reading "playing" over a black display. The race lives on mpv's core thread, so the round is driven ten times — unfixed, roughly one round in fifteen dies — while the _unloading reads pin the mechanism deterministically: armed by a stop over a loaded file, consumed by the play-shaped call that must reload because of it. loop-file keeps the file from reaching EOF mid-round, which would put _ensure_loaded on its rewind branch instead.
    """
    display = VideoDisplay(window, width=320, height=200)
    display.grid(row=0, column=0)
    pump(window)
    Surface.review_all()
    pump(window)
    backend = display._mpv
    assert backend is not None
    backend["ao"] = "null"
    backend["loop-file"] = "inf"
    source = _silence_wav(tmp_path)

    for _ in range(10):
        display.play(source)
        assert _eventually(window, pump, lambda: backend.path is not None)

        display.stop()
        armed = display._unloading
        display.play()
        consumed = display._unloading
        assert (armed, consumed) == (True, False)

        assert _eventually(window, pump, lambda: backend.path is not None)
        assert _eventually(window, pump, lambda: display.paused is False)


def test_a_seek_in_the_same_tick_as_stop_is_held_for_the_next_load(
    window: tkfacade.Window, pump: Pump, tmp_path: Path
) -> None:
    """``stop(); seek(x)`` holds the cue, and the next load lands paused on it.

    stop cleared the pending-seek slots but left the dead file's duration standing in the mirror until mpv's None report arrived a pump later — so a same-tick seek saw a timeline, bypassed the no-timeline hold, issued a real seek at a stopping core, and the suppressed refusal left nothing held and nothing to replay: the cue-then-resume idiom started at zero. The held/mirror pair is the mechanism, read synchronously before any pump: the mirror must be zero the instant stop returns, and the cue must be sitting in the hold because of it; the position readout showing the cue pins that the reload consumed it through _begin_seek. The backend leg is loose on purpose — the cue rides the reload as mpv's start option, so time_pos can only ever be at or past 0.6 (EOF included), while ao=null plays too fast for any exact position to be assertable — but it can never sit below the cue, which is where a file started from zero pauses out.
    """
    display = VideoDisplay(window, width=320, height=200)
    display.grid(row=0, column=0)
    pump(window)
    Surface.review_all()
    pump(window)
    backend = display._mpv
    assert backend is not None
    backend["ao"] = "null"

    display.play(_silence_wav(tmp_path))
    assert _eventually(window, pump, lambda: display.duration > 0.9)

    display.stop()
    display.seek(0.6)
    held = display._pending_seek
    mirror = display.duration
    display.play()

    assert (held, mirror) == (0.6, 0.0)
    assert display.position > 0.5
    assert _eventually(window, pump, lambda: (backend.time_pos or 0.0) > 0.55)


def test_skips_accumulate_across_the_seek_hold(
    window: tkfacade.Window, pump: Pump, tmp_path: Path
) -> None:
    """Repeated ``skip`` calls add up while a seek is held for a timeline.

    skip promises repeats accumulate "because each records its target as the position the next reads", but that recording lived only on the live branch — the hold branch stores the target and deliberately leaves the readout still, so the second skip re-read the same stale position and overwrote the hold: N clicks of a player's step buttons during a load window moved one step. skip now measures from the held target when one is waiting. The synchronous pending read is the mechanism (0.6, not 0.3); the landing leg reruns the existing resume-at-position shape through skips, pinning that the accumulated hold replays like a plain held seek — paused, so the file cannot outrun the assertion under ao=null.
    """
    display = VideoDisplay(window, width=320, height=200)
    display.grid(row=0, column=0)
    pump(window)
    Surface.review_all()
    pump(window)
    backend = display._mpv
    assert backend is not None
    backend["ao"] = "null"
    source = _silence_wav(tmp_path)

    display.play(source)
    assert _eventually(window, pump, lambda: display.duration > 0.9)

    display.play(source)
    display.pause()
    display.skip(0.3)
    display.skip(0.3)

    assert display._pending_seek is not None
    assert abs(display._pending_seek - 0.6) < 0.001
    assert _eventually(window, pump, lambda: display.position > 0.5)
    assert display.paused is True


def test_uncovering_an_ended_display_keeps_the_pause_truthful(
    window: tkfacade.Window, pump: Pump, tmp_path: Path
) -> None:
    """A cover/uncover cycle after a natural EOF leaves ``paused`` agreeing with mpv.

    Every deliberate unpause routes through _ensure_loaded's EOF rewind, but the policy release pushed pause=False raw at a core keep_open holds at EOF: mpv refuses the unpause (nothing can advance there) and, its value never changing, reports nothing to correct the False the push wrote into the mirror — display.paused lied against backend.pause indefinitely, a bar claiming playing over the frozen last frame. The release now leaves keep_open's own pause standing: the file was finished before the cover, so uncovering restores that state. Both sides of the formerly-split truth are asserted; the grid_remove/grid dance with review_all is the same stand-in for real obstruction events the sibling policy test uses.
    """
    display = VideoDisplay(window, obstructed_pause=True, width=320, height=200)
    display.grid(row=0, column=0)
    pump(window)
    Surface.review_all()
    pump(window)
    backend = display._mpv
    assert backend is not None
    backend["ao"] = "null"

    display.play(_silence_wav(tmp_path))
    assert _eventually(window, pump, lambda: bool(backend.eof_reached))
    assert _eventually(window, pump, lambda: display.paused)

    display._tk.grid_remove()
    pump(window)
    Surface.review_all()
    pump(window)
    display.grid(row=0, column=0)
    pump(window)
    Surface.review_all()
    pump(window)

    assert display.obstructed is False
    assert display.paused is True
    assert backend.pause is True
