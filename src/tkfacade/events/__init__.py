"""Names, patterns, and field values for Tk event bindings.

:class:`EventType`, :class:`Key`, :class:`MouseButton`, and
:class:`EventModifier` spell the pieces of a binding pattern;
:class:`VirtualEvent` and :class:`ConsoleVirtualEvent`
name the ``<<Name>>`` events Tk ships. :class:`Substitution` lists the
percent codes Tk expands in binding scripts; :class:`CrossingDetail`,
:class:`CrossingMode`, :class:`VisibilityState`, and
:class:`ModifierState` — the ``%s`` / ``event.state`` modifier bits —
are the values those codes take; and :class:`RawEventDict` types the
raw field dict of a delivered event.
"""

from ._enums import ConsoleVirtualEvent as ConsoleVirtualEvent
from ._enums import CrossingDetail as CrossingDetail
from ._enums import CrossingMode as CrossingMode
from ._enums import EventModifier as EventModifier
from ._enums import EventType as EventType
from ._enums import Key as Key
from ._enums import ModifierState as ModifierState
from ._enums import MouseButton as MouseButton
from ._enums import Substitution as Substitution
from ._enums import VirtualEvent as VirtualEvent
from ._enums import VisibilityState as VisibilityState
from ._event import EMPTY_PAYLOAD as EMPTY_PAYLOAD
from ._event import Event as Event
from ._events import NA as NA
from ._events import RawEventDict as RawEventDict
from ._events import VisibilityStateName as VisibilityStateName
from ._spec import ACTIVATED as ACTIVATED
from ._spec import Destroyed as Destroyed
from ._spec import EventSpec as EventSpec
from ._spec import FocusGained as FocusGained
from ._spec import FocusLost as FocusLost
from ._spec import Motion as Motion
from ._spec import PointerEnter as PointerEnter
from ._spec import PointerLeave as PointerLeave
from ._spec import Press as Press
from ._spec import Release as Release
from ._spec import Virtual as Virtual
from ._spec import Wheel as Wheel
