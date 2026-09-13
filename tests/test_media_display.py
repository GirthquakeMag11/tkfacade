"""The timed-media contract's shape, and that every display answers it.

Class introspection only: no Tk interpreter and no window handle, so
this runs without a display and carries no ``gui`` marker.
"""

import pytest

from tkfacade.media import AbstractMediaDisplay, ImageDisplay, MediaPlayer, VideoDisplay

IMPLEMENTATIONS: tuple[type[AbstractMediaDisplay], ...] = (
    ImageDisplay,
    MediaPlayer,
    VideoDisplay,
)
"""Every concrete wearer of the contract in the library."""

CONTRACT: tuple[str, ...] = (
    "variables",
    "loop",
    "muted",
    "media_width",
    "media_height",
    "auto_size",
    "auto_size_limit",
    "obstructed_pause",
    "position",
    "duration",
    "paused",
    "volume",
    "position_locked",
    "play",
    "pause",
    "resume",
    "toggle_pause",
    "stop",
    "seek",
    "skip",
)
"""Every member :class:`~tkfacade.media.AbstractMediaDisplay` declares itself."""


def test_the_contract_names_every_member_of_a_timed_media_display() -> None:
    """The base declares exactly the members a display of timed media offers.

    The base exists so that a consumer -- a control bar, a caller holding "something that plays" -- can be written against it instead of against mpv, and its member list is the whole of what such a consumer may reach for. A member dropping off it during a later edit narrows that silently: VideoDisplay keeps working, every other test keeps passing, and only the next consumer finds out. Nothing else in the suite reads the base's shape, so this is the only place that would fail. vars(), not getattr(): Surface already supplies width, height and obstructed, so a getattr check would pass for names the base does not declare at all. The equality runs both ways so that a member added without the decision behind it fails just as loudly as one removed.
    """
    declared = {name for name in vars(AbstractMediaDisplay) if not name.startswith("_")}

    assert declared == set(CONTRACT)


@pytest.mark.parametrize("display", IMPLEMENTATIONS, ids=lambda cls: cls.__name__)
def test_a_display_answers_the_whole_contract(display: type[AbstractMediaDisplay]) -> None:
    """Each display declares the contract and leaves nothing of it abstract.

    "A contract is tested whole" reaches every implementation, not the first one written, and an empty __abstractmethods__ is what says the whole of it is answered -- a member left unimplemented lands there and makes the class uninstantiable, which the GUI suite would report as a constructor failure with nothing pointing at the contract. Read off the class rather than by building a display, because constructing one needs a real window handle (and, for the video, libmpv) while the claim needs neither; test_image_display.py and test_video_display.py cover the behaviour behind these members.
    """
    assert issubclass(display, AbstractMediaDisplay)

    assert display.__abstractmethods__ == frozenset()


def test_every_implementation_is_listed() -> None:
    """``IMPLEMENTATIONS`` names every concrete wearer in the library.

    Guard against the parametrized test above silently covering less than it claims: a wearer added later and not listed would leave the contract check green while nothing had ever run against the new class. Direct subclasses only, which is the line the contract is answered at: the two displays wear it over Surface, MediaPlayer over a composite of both, and each answers for itself.
    """
    assert set(IMPLEMENTATIONS) == set(AbstractMediaDisplay.__subclasses__())
