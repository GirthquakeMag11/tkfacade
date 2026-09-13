"""Looks: shared appearance objects, worn by widgets through ``look``.

:class:`Look` holds any of the styling vocabulary and applies the
subset measured to act on each widget it dresses; :class:`LookPart`
and :class:`LookState` are the sections a look answers for parts and
situations. See :class:`Look` for the whole story.
"""

from ._look import Look as Look
from ._look import LookOptions as LookOptions
from ._look import LookPart as LookPart
from ._look import LookState as LookState
