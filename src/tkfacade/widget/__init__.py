"""The widget wrapper hierarchy and its geometry-manager facets.

:class:`BaseWidget` holds the wrapped Tk widget and the registry that
finds a wrapper again from its widget's path;
:class:`ContainerWidget` adds the container half of grid, pack and
place, and :class:`Widget` adds the slave half on top — so a window,
which masters others but is never mastered, is a container and a
concrete wrapper is a full widget. :class:`Surface` is the wrapper for
things drawn by something other than Tk.

The deferred master-side configs live in ``config`` and are re-exported
here, as are the geometry option dicts, which this package's own
signatures take.
"""

from .._params import GridSetOptions as GridSetOptions
from .._params import PackSetOptions as PackSetOptions
from .._params import PlaceSetOptions as PlaceSetOptions
from ._base import BaseWidget as BaseWidget
from ._surface import Surface as Surface
from ._widget import ContainerWidget as ContainerWidget
from ._widget import Widget as Widget
from .config import GridConfig as GridConfig
from .config import GridElementConfig as GridElementConfig
from .config import GridSetConfig as GridSetConfig
from .config import PackConfig as PackConfig
from .config import PackSetConfig as PackSetConfig
from .config import PlaceConfig as PlaceConfig
from .config import PlaceSetConfig as PlaceSetConfig
