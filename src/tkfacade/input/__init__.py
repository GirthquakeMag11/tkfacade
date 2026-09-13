"""Input state: the root-held record of what is pressed, and chords over it.

:class:`InputObserver` is reached as :attr:`~tkfacade.window.Root.inputs`;
:class:`Chord` is what its :meth:`~InputObserver.chord` answers. See
:class:`InputObserver` for the whole story.
"""

from ._observer import Chord as Chord
from ._observer import InputName as InputName
from ._observer import InputObserver as InputObserver
from ._observer import KeyGroup as KeyGroup
