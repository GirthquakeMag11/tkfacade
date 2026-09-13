"""Deferred, mergeable geometry configuration for widgets.

A config accumulates the options a geometry manager takes on a
*master* — grid's column and row settings, anchor and propagation;
pack's propagation — without touching any widget. Configs combine via
``|`` / ``|=`` and the hard/soft update methods, then apply to a live
widget in one pass via ``visit()``, so a layout can be described and
composed before the widget it targets exists.

One config per manager: :class:`~tkfacade.widget.GridConfig`,
:class:`~tkfacade.widget.PackConfig`, and
:class:`~tkfacade.widget.PlaceConfig`, which is empty because Tk gives
place no master-side options at all.
:class:`~tkfacade.widget.GridElementConfig` is the live view over a grid
config's column or row entries that
:meth:`~tkfacade.widget.GridConfig.column` and
:meth:`~tkfacade.widget.GridConfig.row` return, exported for annotating
that return rather than to be built directly.

The options that position one widget inside its master —
``row``/``sticky``, ``side``/``fill``, ``relx``/``anchor`` — are the
slave half, and have their own composable twins:
:class:`~tkfacade.widget.GridSetConfig`,
:class:`~tkfacade.widget.PackSetConfig` and
:class:`~tkfacade.widget.PlaceSetConfig`, each mirroring its
``*SetOptions`` dict with the same merge surface the master configs
carry and a ``visit`` that replays through the widget's own placement
method.
"""

from ._grid import GridConfig as GridConfig
from ._grid import GridElementConfig as GridElementConfig
from ._grid import GridSetConfig as GridSetConfig
from ._pack import PackConfig as PackConfig
from ._pack import PackSetConfig as PackSetConfig
from ._place import PlaceConfig as PlaceConfig
from ._place import PlaceSetConfig as PlaceSetConfig
