""":class:`~tkfacade.MediaPlayer`: kind resolution, switching, and the mirrors.

The player's own claims — a source resolving to the right display, the
video half built lazily, the held settings and watches surviving a
switch, the bridge gating under a drag, and teardown returning what
construction took. The displays' own playback contracts are covered by
their suites; everything here drives them only as far as the player's
seams require. Runs on the ``window`` fixture under the ``gui`` marker;
the switching tests construct a real mpv, as the video suite does.
"""

import io
import wave
from pathlib import Path

import pytest
from PIL import Image

import tkfacade
from conftest import Pump
from tkfacade.media._player import _GLYPH_PLAY, _resolve_kind
from tkfacade.widget import Surface

pytestmark = pytest.mark.gui


def _gif_bytes(*durations: int) -> bytes:
    """Encode one solid-colour 2x1 GIF frame per entry of ``durations``."""
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


def _silence_wav(directory: Path) -> str:
    """Write one second of silent mono audio and return its path.

    The video-kind fixture: PIL cannot identify a wav, so it resolves
    to mpv's display, and mpv loads it without a video output — viable
    under a headless test display, as the video suite records.
    """
    path = directory / "silence.wav"
    with wave.open(str(path), "wb") as sink:
        sink.setnchannels(1)
        sink.setsampwidth(2)
        sink.setframerate(8000)
        sink.writeframes(b"\x00\x00" * 8000)
    return str(path)


def _drawn(window: tkfacade.Window, pump: Pump) -> tkfacade.MediaPlayer:
    """An empty player, laid out and reviewed until its displays can draw."""
    player = tkfacade.MediaPlayer(window, width=64, height=32)
    player.grid(row=0, column=0)
    pump(window)
    Surface.review_all()
    pump(window)
    return player


def test_sources_resolve_to_the_display_their_kind_belongs_to(tmp_path: Path) -> None:
    """Image sources of every spelling go to the image display, the rest to mpv.

    The whole routing decision in one place, one assertion per spelling: a non-path source is an image by construction (mpv takes only paths and URLs), an existing file is whatever PIL says it is, and a string naming no file is a URL and mpv's to refuse. The wav is the suite's standing video stand-in — a real media file PIL cannot identify — so the same fixture that drives the switching tests is the one proven to resolve.
    """
    png = tmp_path / "still.png"
    png.write_bytes(_png_bytes())
    gif = tmp_path / "anim.gif"
    gif.write_bytes(_gif_bytes(50, 50))
    wav = Path(_silence_wav(tmp_path))

    assert _resolve_kind(_png_bytes()) == "image"
    assert _resolve_kind(Image.new("RGB", (2, 2))) == "image"
    assert _resolve_kind(png) == "image"
    assert _resolve_kind(str(gif)) == "image"
    assert _resolve_kind(wav) == "video"
    assert _resolve_kind("https://example.invalid/clip.mkv") == "video"


def test_an_empty_player_answers_its_constructed_state(window: tkfacade.Window, pump: Pump) -> None:
    """Before any source: paused over nothing, no kind, the bar at rest.

    The mirrors answer the player's own constructed state while no display is seated — the honest answers a caller gets between construction and the first play, and what masks the bare video display's wrong startup paused from every player user. The glyph read pins that the bar renders off those mirrors' immediate first calls.
    """
    player = _drawn(window, pump)

    idle: bool = player.paused
    assert idle
    assert player.kind is None
    assert not player.duration > 0.0  # 0.0 exactly: the constructed mirror, no arithmetic
    assert player.source is None
    assert player._play["text"] == _GLYPH_PLAY


def test_an_image_source_seats_the_image_display(window: tkfacade.Window, pump: Pump) -> None:
    """``play`` of an animation resolves to the image display and plays it.

    The image path end to end: resolution seats the display, the display's own decode lands synchronously, and the bridge's immediate first calls put the reel's duration and running state on the player's mirrors. The final assertion is the lazy half of ruling 3: an image-only player never builds the video display, so it never asks for libmpv.
    """
    player = _drawn(window, pump)

    player.play(_gif_bytes(100, 200, 300))

    assert player.kind == "image"
    assert abs(player.duration - 0.6) < 0.001
    playing: bool = player.paused
    assert not playing
    assert player._video_display is None


def test_a_video_source_builds_the_video_display_on_first_use(
    window: tkfacade.Window, pump: Pump, tmp_path: Path
) -> None:
    """The first video source constructs the video display; a switch seats it.

    Lazy construction observed from both sides: absent after an image played, present exactly when a video source arrives. The outgoing display is stopped on the way out — a hidden reel must not keep ticking behind the video — which the image display's paused pins.
    """
    player = _drawn(window, pump)
    player.play(_gif_bytes(50, 50))
    before = player._video_display
    assert before is None

    player.play(_silence_wav(tmp_path))

    assert player.kind == "video"
    assert player._video_display is not None
    image_stopped: bool = player._image_display.paused
    assert image_stopped


def test_held_settings_ride_every_switch(
    window: tkfacade.Window, pump: Pump, tmp_path: Path
) -> None:
    """The settable four are the player's own and reach each seated display.

    Ruling 2's persistence half: volume and loop live in the player and are pushed into whichever display activates, so a level set over an image holds across the video and the image after that. Asserted on the displays' own bundles — the push must actually arrive, not merely be remembered — and back on the player, whose mirror must not have been dragged by any display's own default.
    """
    player = _drawn(window, pump)
    player.play(_gif_bytes(50, 50))
    player.volume = 37.0
    player.loop = True

    player.play(_silence_wav(tmp_path))
    video = player._video_display
    assert video is not None
    assert abs(video.variables.volume.value - 37.0) < 0.001
    assert video.loop

    player.play(_gif_bytes(50, 50))
    assert abs(player._image_display.variables.volume.value - 37.0) < 0.001
    assert player._image_display.loop
    assert abs(player.volume - 37.0) < 0.001


def test_a_watch_on_the_player_survives_a_switch(
    window: tkfacade.Window, pump: Pump, tmp_path: Path
) -> None:
    """One watch on the player's bundle sees both displays' reports.

    The point of the player owning its bundle: the caller binds once and never re-binds. The gif's decode puts 0.6 through the watch; seating the video display puts its current 0.0 through the same watch via the bridge's immediate first call. Were the bundle the active display's, the first switch would orphan the subscription silently.
    """
    player = _drawn(window, pump)
    seen: list[float] = []
    subscription = player.variables.duration.watch(seen.append)

    player.play(_gif_bytes(100, 200, 300))
    assert any(abs(value - 0.6) < 0.001 for value in seen)

    player.play(_silence_wav(tmp_path))
    assert not seen[-1] > 0.0  # 0.0 exactly: the video display's unloaded mirror

    subscription.cancel()


def test_the_position_bridge_holds_under_a_drag(window: tkfacade.Window, pump: Pump) -> None:
    """Display position reports do not move the mirror while scrubbing.

    Ruling 5: scrubbing rides the bridge, not position_locked. The flag is driven directly rather than through synthesized button events because the claim is the bridge's, not Tk's: with the gate up, a report that reaches the display's own variable stays off the player's mirror, and dropping the gate lets the next report through. The displays' hook and its known bypass are deliberately not involved.
    """
    player = _drawn(window, pump)
    player.play(_gif_bytes(100, 200, 300))
    player.pause()
    player.seek(0.3)
    assert abs(player.position - 0.3) < 0.001

    player._scrubbing = True
    assert player._active is not None
    player._active.seek(0.1)
    held: float = player.position
    assert abs(held - 0.3) < 0.001

    player._scrubbing = False
    player._active.seek(0.2)
    assert abs(player.position - 0.2) < 0.001


def test_a_still_swapped_in_through_the_player_reads_paused(
    window: tkfacade.Window, pump: Pump
) -> None:
    """The player's image-to-image path lands on the repaired still-swap.

    The composition's own regression for the still-swap fix: same-kind sources never switch displays, so this is the exact path the Known Issues entry warned a control bar about — and the bar here is bound to the very mirror asserted on.
    """
    player = _drawn(window, pump)
    player.play(_gif_bytes(50, 50, 50))
    running: bool = player.paused
    assert not running

    player.play(_png_bytes())

    stopped: bool = player.paused
    assert stopped
    assert player.kind == "image"


def test_teardown_returns_the_bars_transport_rides(window: tkfacade.Window, pump: Pump) -> None:
    """Destroying the player drops all five transports it acquired.

    The five rides are the three toggles' and the two scales'; a transport left standing pins the interpreter (`hazards/tkinter.md`, *Variables*), which is what the Destroyed-bound give-back exists to prevent. Read off the observables' own transport slot because the count is the claim — the wrapper-side wreckage after destroy offers nothing else to assert on.
    """
    player = _drawn(window, pump)
    ridden = (
        player._variables.loop,
        player._variables.auto_size,
        player._variables.muted,
        player._variables.position,
        player._variables.volume,
    )
    assert all(observable._var is not None for observable in ridden)

    player._tk.destroy()
    pump(window)

    assert all(observable._var is None for observable in ridden)
