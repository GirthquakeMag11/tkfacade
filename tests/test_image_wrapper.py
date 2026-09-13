"""The pure-PIL image transformations, and the wrapper they answer with.

Everything here except the ``iter_frames`` tests runs without a Tk
interpreter — construction, cropping, flipping, rotation, and scaling
are PIL-only by the module's own contract. The doctests on each
function pin its headline size arithmetic; these tests cover ownership,
content, and the boundaries the doctests leave open.

``iter_frames`` builds Tk images, so its tests take the ``root``
fixture and carry the ``gui`` marker.
"""

import io
from typing import cast

import pytest
from PIL import Image, ImageTk

from tkfacade.media import (
    MIN_FRAME_DELAY,
    ImageWrapper,
    crop_absolute,
    crop_side,
    flip_horizontal,
    rotate,
    scale,
    thumbnail,
)
from tkfacade.window import Root

RED = (255, 0, 0)
BLUE = (0, 0, 255)


def _two_tone() -> Image.Image:
    """A 2x1 image, red on the left and blue on the right."""
    image = Image.new("RGB", (2, 1), RED)
    image.putpixel((1, 0), BLUE)
    return image


def _gif_bytes(*durations: int) -> bytes:
    """Encode one solid-color 2x1 GIF frame per entry of ``durations``.

    Each frame gets a distinct color — identical frames would be
    merged by GIF optimization, collapsing the frame count and
    summing the durations.

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


def _two_tone_gif_bytes() -> bytes:
    """Encode a 2x1 two-frame GIF: red|blue held 100ms, then blue|red held 200ms."""
    first = _two_tone()
    second = Image.new("RGB", (2, 1), BLUE)
    second.putpixel((1, 0), RED)
    buffer = io.BytesIO()
    first.save(buffer, format="GIF", save_all=True, append_images=[second], duration=[100, 200])
    return buffer.getvalue()


def _oriented_apng_bytes() -> bytes:
    """Encode a 4x2 two-frame PNG carrying EXIF orientation 6 (90° clockwise)."""
    first = Image.new("RGBA", (4, 2), (255, 0, 0, 255))
    second = Image.new("RGBA", (4, 2), (0, 255, 0, 255))
    exif = Image.Exif()
    exif[0x0112] = 6
    buffer = io.BytesIO()
    first.save(
        buffer, format="PNG", save_all=True, append_images=[second], duration=[100, 200], exif=exif
    )
    return buffer.getvalue()


def test_construction_copies_the_source_image() -> None:
    """Mutating the source image after wrapping never reaches the wrapper.

    "Construction takes ownership of its pixels" is the class's opening claim, and it is what lets callers keep transforming a source image without corrupting wrappers built from it earlier. putpixel on the source is the direct probe: shared pixel data would show blue.
    """
    source = _two_tone()
    wrapper = ImageWrapper(source)

    source.putpixel((0, 0), BLUE)

    assert wrapper.image.getpixel((0, 0)) == RED


def test_transforms_leave_the_source_wrapper_unchanged() -> None:
    """A transform returns a new wrapper and leaves its source's pixels alone.

    The other half of the ownership contract: every transformation "returns a fresh wrapper ... the original is never mutated". flip_horizontal stands in for the whole family because all transforms share the same construct-a-new-wrapper shape; the asymmetric two-tone image is what makes both the purity and the mirroring observable in single pixels.
    """
    original = ImageWrapper(_two_tone())

    mirrored = flip_horizontal(original)

    assert mirrored is not original
    assert original.image.getpixel((0, 0)) == RED
    assert mirrored.image.getpixel((0, 0)) == BLUE


def test_a_wrapper_is_itself_a_source() -> None:
    """A wrapper feeds straight back in, so transformations compose.

    ``ImageWrapper`` is an arm of ``ImageInput`` precisely so a caller never has to unwrap one to keep going, and nothing else pins that: without it the functions would still work one at a time and only composition would break. The nested call is the real probe — it feeds a wrapper in without ever binding it to a name, which is how chained code reads — and the second assertion covers a wrapper held in hand, the other way it arrives.
    """
    twice = scale(rotate(_two_tone(), 90), 50)

    assert twice.image.size == (1, 1)
    assert flip_horizontal(ImageWrapper(_two_tone())).image.getpixel((0, 0)) == BLUE


def test_crop_absolute_rejects_bad_ranges() -> None:
    """A backwards or out-of-bounds crop range raises ``ValueError``.

    The validation is the undoctested part of crop_absolute (the happy path has a doctest). Without it PIL would accept both boxes and answer a 0-wide or zero-padded image, deferring the failure to whatever displays the result. The match strings pin that each axis reports under its own name.
    """
    wrapper = ImageWrapper(Image.new("RGB", (40, 20)))

    with pytest.raises(ValueError, match="horizontal"):
        crop_absolute(wrapper, horizontal=(10, 5))
    with pytest.raises(ValueError, match="vertical"):
        crop_absolute(wrapper, vertical=(0, 21))


def test_crop_side_keeps_the_named_edge() -> None:
    """``crop_side`` keeps pixels nearest the anchor edge, not opposite it.

    The doctest pins the crop's *size*; this pins its *side*. "The anchor names the edge that is kept" is exactly the convention a reader can hold backwards, and a wrong-side implementation returns the right dimensions with the wrong pixels — invisible to any size assertion.
    """
    wrapper = ImageWrapper(_two_tone())

    assert crop_side(wrapper, "right", 1).image.getpixel((0, 0)) == BLUE
    assert crop_side(wrapper, "left", 1).image.getpixel((0, 0)) == RED


def test_crop_side_oversized_breadth_keeps_everything() -> None:
    """A breadth at or beyond the dimension returns the whole image.

    The documented saturation edge: the min/max clamps inside crop_side are what keep an oversized breadth from becoming a negative crop bound that crop_absolute would then reject. Both the exact dimension and a gross excess are checked because the boundary case (==) and the clamp case (>) take different values through ``min``.
    """
    wrapper = ImageWrapper(Image.new("RGB", (40, 20)))

    assert crop_side(wrapper, "top", 20).image.size == (40, 20)
    assert crop_side(wrapper, "top", 999).image.size == (40, 20)


def test_crop_side_rejects_bad_arguments() -> None:
    """A negative breadth or unknown anchor raises ``ValueError``.

    The two documented Raises clauses. "center" needs the arg-type ignore precisely because the Side literal already excludes it statically — the test exists for the caller who arrives with an unchecked string at runtime, which the type system cannot rule out.
    """
    wrapper = ImageWrapper(Image.new("RGB", (40, 20)))

    with pytest.raises(ValueError, match="breadth"):
        crop_side(wrapper, "top", -1)
    with pytest.raises(ValueError, match="anchor"):
        crop_side(wrapper, "center", 5)  # type: ignore[arg-type]


def test_rotate_quarter_turn_is_clockwise() -> None:
    """``rotate(90)`` turns clockwise: the left pixel lands at the top.

    PIL's own rotate is counter-clockwise and the wrapper documents clockwise, so the direction is a deliberate inversion sitting one sign error from wrong. The doctest already pins the size swap; only a pixel-level check can tell clockwise from counter-clockwise.
    """
    rotated = rotate(_two_tone(), 90)

    assert rotated.image.size == (1, 2)
    assert rotated.image.getpixel((0, 0)) == RED
    assert rotated.image.getpixel((0, 1)) == BLUE


def test_rotate_normalizes_negative_angles() -> None:
    """``rotate(-90)`` equals ``rotate(270)``, pixel for pixel.

    "Angles are normalized, so negative values ... are accepted" — and a negative quarter turn must take the exact-transposition path, not the resampling fallback (which would blur and expand). Comparing full pixel data against the canonical spelling pins both at once.
    """
    source = ImageWrapper(_two_tone())

    assert rotate(source, -90).image.tobytes() == rotate(source, 270).image.tobytes()


def test_rotate_off_axis_expands_the_canvas() -> None:
    """A non-quarter rotation grows the canvas so no corner is clipped.

    The resampling branch's one documented geometric promise (``expand=True``). Without it PIL keeps the original canvas and silently clips all four corners. Inequalities rather than exact values because the expanded size is PIL's rounding to own, not this wrapper's contract.
    """
    rotated = rotate(Image.new("RGB", (40, 20)), 45)

    assert rotated.image.size[0] > 40
    assert rotated.image.size[1] > 20


def test_scale_clamps_to_one_pixel() -> None:
    """Scaling far below one pixel still yields a 1x1 image.

    The documented floor ("Both axes round to at least one pixel"): 4 * 1% rounds to 0, and without the max() clamp PIL raises on a zero-dimension resize — from inside the library, far from the percentage that caused it.
    """
    assert scale(Image.new("RGB", (4, 4)), 1).image.size == (1, 1)


def test_scale_rejects_non_positive_percent() -> None:
    """A zero or negative percentage raises ``ValueError``.

    Zero is the boundary value (the check is <=, not <) and a negative percentage is the nonsense input; both belong to the same guard, so they share a test. Without the guard, zero would fall into the downscale branch and die inside PIL instead.
    """
    wrapper = ImageWrapper(Image.new("RGB", (4, 4)))

    with pytest.raises(ValueError, match="percent"):
        scale(wrapper, 0)
    with pytest.raises(ValueError, match="percent"):
        scale(wrapper, -50)


def test_thumbnail_never_upscales() -> None:
    """An image already inside the bounding box comes back unchanged.

    The doctest pins the shrink; this pins the refusal to grow, which is thumbnail's defining difference from scale. An implementation built on resize instead of PIL's thumbnail would inflate the image to the box and pass every shrinking test.
    """
    assert thumbnail(Image.new("RGB", (8, 4)), 100, 100).image.size == (8, 4)


def test_thumbnail_defaults_leave_an_axis_unbounded() -> None:
    """An omitted bound defaults to the current size on that axis.

    One bound given positionally, the other defaulted: the None-means- current-dimension defaults are what let callers constrain a single axis. Aspect preservation then forces the unconstrained axis to 5, so the assertion covers both the default and the ratio in one size.
    """
    assert thumbnail(Image.new("RGB", (40, 20)), 10).image.size == (10, 5)


@pytest.mark.gui
def test_frames_clamps_delays_to_the_floor(root: Root) -> None:
    """Frame delays below ``MIN_FRAME_DELAY`` are raised to it; others kept.

    The clamp exists because Tk cannot service sub-20ms timers, and GIFs claiming 10ms frames are common; without the floor an animation would spin the event loop. A two-frame GIF with one delay on each side of the floor pins clamped and passed-through in a single iteration. The wrapper is built from bytes because only an encoded source keeps its frames, and the test needs the root fixture since every frame becomes a Tk image.
    """
    wrapper = ImageWrapper(_gif_bytes(10, 500))

    delays = [frame.delay for frame in wrapper.iter_frames()]

    assert delays == [MIN_FRAME_DELAY, 500]


@pytest.mark.gui
def test_frames_rewinds_and_stills_yield_once(root: Root) -> None:
    """Iteration yields one frame per source frame, then rewinds to frame 0.

    Three contracts that share one setup: the count proves the iterator walks every encoded frame, ``tell() == 0`` proves the documented rewind (iteration seeks the wrapped image, and a wrapper left mid-seek would corrupt a later ``photo`` or second iteration), and the still image pins the exactly-one-frame degenerate case.
    """
    animated = ImageWrapper(_gif_bytes(100, 100, 100))
    still = ImageWrapper(Image.new("RGB", (2, 1)))

    assert len(list(animated.iter_frames())) == 3
    assert animated.image.tell() == 0
    assert len(list(still.iter_frames())) == 1


@pytest.mark.gui
def test_a_transformed_animation_keeps_every_frame(root: Root) -> None:
    """A transformed animation keeps every playback frame, transformed, delays intact.

    The ledger's model defect: every transformation answered a multi-frame source with a one-frame wrapper. Delays and pixels are asserted together because each catches what the other cannot — right delays over duplicated frame-0 pixels would mean the reel was rebuilt from one frame, and right pixels under collapsed delays would mean timing was lost in the mapping. The crop keeps the one column on which the two frames differ, so each frame's identity is readable from a single pixel, and the trailing flip pins that a wrapper already holding decoded frames feeds a second transformation without losing them.
    """
    cropped = crop_absolute(ImageWrapper(_two_tone_gif_bytes()), horizontal=(1, 2))

    frames = list(cropped.iter_frames())

    assert [frame.delay for frame in frames] == [100, 200]
    # getpixel's static type spans every mode; on an RGBA frame it is a tuple
    pixels = [
        cast("tuple[int, ...]", ImageTk.getimage(frame.frame).getpixel((0, 0)))[:3]
        for frame in frames
    ]
    assert pixels == [BLUE, RED]
    assert len(list(flip_horizontal(cropped).iter_frames())) == 2


@pytest.mark.gui
def test_copy_and_unscaled_scale_keep_the_animation(root: Root) -> None:
    """``copy`` and ``scale(100)`` keep an animation's frames, and ``copy`` its format.

    The two copy-shaped paths that flattened alongside the transformations proper. copy is the one path that decodes an encoded source's reel eagerly while still claiming the source's format for itself, so both halves of its contract are asserted; scale(100) shares the test because it documents itself as an unscaled copy and returns through copy — it was the entry's sharpest symptom, a "resize" that destroyed the animation without resizing anything.
    """
    wrapper = ImageWrapper(_gif_bytes(100, 100, 100))

    copied = wrapper.copy()

    assert len(list(copied.iter_frames())) == 3
    assert copied.format == "GIF"
    assert len(list(scale(wrapper, 100).iter_frames())) == 3


@pytest.mark.gui
def test_photo_is_frame_zero_even_mid_iteration(root: Root) -> None:
    """``photo`` answers frame 0 while an ``iter_frames`` iterator is mid-flight.

    photo used to build from whatever frame a live iterator had seeked the shared image to, and the one-shot cache kept that mid-animation frame for the wrapper's lifetime. Frame 0 is asserted by pixel because the defect produced a valid handle with wrong contents — no size or identity check can see it. Draining the iterator afterwards pins that the corrective rewind does not derail an in-flight iteration, and the identity read pins that the cache still holds.
    """
    wrapper = ImageWrapper(_gif_bytes(100, 100, 100))
    frames = wrapper.iter_frames()
    next(frames)
    next(frames)

    photo = wrapper.photo

    pixel = cast("tuple[int, ...]", ImageTk.getimage(photo).getpixel((0, 0)))
    assert pixel[:3] == (0, 0, 0)
    assert len(list(frames)) == 1
    assert wrapper.photo is photo


@pytest.mark.gui
def test_an_oriented_animation_keeps_its_frames_reoriented(root: Root) -> None:
    """An EXIF orientation on an animated source rotates every frame, dropping none.

    _open transposed any oriented encoded source whole, which copies one frame — so an animated PNG or WebP carrying a camera orientation tag silently lost its animation at load, a case no GIF-based test could produce because GIF has no EXIF at all. Size, delays, and per-frame pixels are asserted together: the swap to 2x4 proves the orientation was applied, the count and delays prove the reel survived the reorientation, and the distinct colors prove frame identity rather than frame 0 twice.
    """
    wrapper = ImageWrapper(_oriented_apng_bytes())

    frames = list(wrapper.iter_frames())

    assert (wrapper.width, wrapper.height) == (2, 4)
    assert [frame.delay for frame in frames] == [100, 200]
    pixels = [
        cast("tuple[int, ...]", ImageTk.getimage(frame.frame).getpixel((0, 0)))[:3]
        for frame in frames
    ]
    assert pixels == [(255, 0, 0), (0, 255, 0)]


def test_an_oriented_pil_image_arrives_upright() -> None:
    """The same tagged photograph is upright from a path and from an opened image alike.

    _open's Image.Image branch returned its copy untransposed while the method claims "honoring EXIF orientation", and the constructor's reorientation applies only to animations — so the same photograph arrived upright from a path or bytes and sideways from an opened PIL image, the sideways form propagating through copy() and every transformation with its tag intact. The two sources are asserted side by side because the defect is the asymmetry itself, on a 2x1 canvas whose swap to 1x2 is the transpose. The final read pins that the tag is consumed by the transpose, not carried on the upright pixels — the intact tag is what let the sideways form propagate.
    """
    base = Image.new("RGB", (2, 1), RED)
    exif = Image.Exif()
    exif[0x0112] = 6
    buffer = io.BytesIO()
    base.save(buffer, format="JPEG", exif=exif.tobytes())
    data = buffer.getvalue()

    from_bytes = ImageWrapper(data)
    from_image = ImageWrapper(Image.open(io.BytesIO(data)))

    assert (from_bytes.width, from_bytes.height) == (1, 2)
    assert (from_image.width, from_image.height) == (1, 2)
    assert from_image.image.getexif().get(0x0112) is None


@pytest.mark.gui
def test_wrapper_images_bind_to_the_interpreter_they_are_used_on(root: Root) -> None:
    """A window icon and a menu image land on a second interpreter without error.

    ImageWrapper.photo built its PhotoImage masterless, registering on the first interpreter the process created — so Window(icon=..., root=custom) raised TclError ('can't use "pyimage1" as iconphoto') out of a valid call, after the toplevel was built, and menu rows with images on a second root died the same way. The first window exists purely to make the shared root the default one before the custom root appears — the single-root situation every other test lives in, and exactly the masking condition. The image_names reads pin the mechanism, not just the absence of a raise: the handle is registered on the interpreter that uses it and on no other. The name comes from photo_for on the custom root rather than from str() on what Window holds: the window keeps the ImageWrapper now, and a wrapper stringifies to its repr, so the old spelling would compare a repr against Tk's names and fail whatever the binding did.
    """
    import tkfacade

    first = tkfacade.Window(title="first", root=root)
    assert first.title == "first"  # the shared root is already the default one
    data = _gif_bytes(100)
    custom = Root()
    try:
        window = tkfacade.Window(title="second", icon=data, root=custom)
        tkfacade.Menubutton(window, "File").insert_command("Open", image=data)

        assert window.icon is not None
        name = str(window.icon.photo_for(custom._tk))
        assert name in custom._tk.image_names()
        assert name not in root._tk.image_names()
    finally:
        if not custom.destroyed:
            custom.destroy()


@pytest.mark.gui
def test_a_wide_mode_still_shows_the_same_through_both_doors(root: Root) -> None:
    """``photo`` rescales a 16-bit still exactly as ``iter_frames`` does.

    photo built its PhotoImage straight from the wrapped image, and ImageTk's fallback for modes outside {1, L, RGB, RGBA} converts by saturation — every 16-bit sample above 255 clipped to white, so the full-scale gradient read (255, 255, 255) at its midpoint through photo while iter_frames, which routes through _to_rgba's rescale, answered (127, 127, 127): the same image differed by door, and only Label took the correct one. The midpoint pixel is the whole claim — saturation and rescale agree at both ends of the ramp, and disagree maximally in the middle. Both doors are read through ImageTk's own getimage so the assertion sees what Tk would draw.
    """
    gradient = Image.new("I;16", (256, 1))
    gradient.putdata([x * 257 for x in range(256)])
    wrapper = ImageWrapper(gradient)

    via_photo = cast("tuple[int, ...]", ImageTk.getimage(wrapper.photo).getpixel((127, 0)))
    frame = next(iter(wrapper.iter_frames())).frame
    via_frames = cast("tuple[int, ...]", ImageTk.getimage(frame).getpixel((127, 0)))

    assert via_photo[:3] == (127, 127, 127)
    assert via_frames[:3] == (127, 127, 127)


def test_a_16_bit_still_survives_a_deep_thumbnail() -> None:
    """A 4x shrink of an ``I;16`` image fits the box instead of raising.

    Image.thumbnail's default reducing_gap pre-shrink calls Pillow's C reduce, which has no I;16 kernel — so any shrink factor reaching ~2 raised "image has wrong mode" out of thumbnail and every icon helper riding it, window_icon behind tkfacade.Window(icon=...) included, on a 16-bit PNG/TIFF the wrapper accepts and Label displays. The shrink now skips the pre-shrink (resize handles every mode); the 4x factor is what used to engage the broken path, the size pins that the box fit still happened, and the mode read pins that the fix converts nothing behind the caller's back.
    """
    scan = Image.new("I;16", (256, 64))
    scan.putdata([(x * 257) % 65536 for x in range(256 * 64)])

    shrunk = thumbnail(scan, 64, 64)

    assert shrunk.image.size == (64, 16)
    assert shrunk.image.mode == "I;16"


def test_a_16_bit_still_survives_a_deep_scale() -> None:
    """A 25% ``scale`` of an ``I;16`` image shrinks instead of raising.

    The reducing_gap fix landed in thumbnail() and its regression test pinned only that door — scale's shrink branch calls Image.thumbnail too, with Pillow's default pre-shrink, so a linear factor of 4 or more (percent 25 and below) still died in the kernel-less C reduce: scale(scan, 25) raised where scale(scan, 26) worked. 25% is exactly the first failing percent, and the mode read pins that the fix converts nothing behind the caller's back.
    """
    scan = Image.new("I;16", (256, 64))
    scan.putdata([(x * 257) % 65536 for x in range(256 * 64)])

    shrunk = scale(scan, 25)

    assert shrunk.image.size == (64, 16)
    assert shrunk.image.mode == "I;16"


@pytest.mark.gui
def test_a_wrapper_does_not_pin_the_roots_it_outlives(root: Root) -> None:
    """Cycling roots through one wrapper leaves no growing pile of interpreters.

    The cache is keyed by the interpreter itself and nothing evicted, so a wrapper reused across roots — the app-icon shape, one wrapper and a new Root per window generation — held every dead root's whole TkappType and the Tk state behind it for the wrapper's life, defeating the root retirement machinery outright (three roots cycled left three fully live interpreters after a drained flush). photo_for now drops entries whose interpreter no longer answers a Tk command, so the pile cannot grow: the bound is the live root's own entry plus at most one not yet swept, which is what the length asserts — an unfixed cache reaches four here. The final build pins that pruning never costs a live interpreter its handle.
    """
    wrapper = ImageWrapper(_gif_bytes(100))
    wrapper.photo_for(root._tk)
    cycled = []
    for _ in range(3):
        extra = Root()
        wrapper.photo_for(extra._tk)
        cycled.append(extra)
        extra.destroy()

    live = wrapper.photo_for(root._tk)

    assert len(wrapper._photos) <= 2
    assert live.width() == 2
