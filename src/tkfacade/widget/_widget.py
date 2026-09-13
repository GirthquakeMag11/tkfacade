"""Compose the geometry-manager facets into the widget wrapper bases."""

import tkinter as tk
from collections.abc import Sequence

from ..look import Look
from ..look._look import STYLE_OPTION_NAMES
from ._base import BaseWidget
from ._grid import GridContainerWidget, GridWidget
from ._pack import PackContainerWidget, PackWidget
from ._place import PlaceContainerWidget, PlaceWidget


class ContainerWidget(GridContainerWidget, PackContainerWidget, PlaceContainerWidget):
    """Wrapper exposing only the container half of each geometry manager.

    The base for wrappers around widgets that master others but are
    never slaves themselves — toplevels, which the window manager owns.
    A :class:`Widget` is a ``ContainerWidget`` plus the slave role.
    """

    __slots__ = ()


class Widget(GridWidget, PackWidget, PlaceWidget, ContainerWidget):
    """Wrapper exposing every Tk geometry manager on one object.

    Each base — ``GridWidget``, ``PackWidget``, ``PlaceWidget`` — is
    a facet over the same wrapped widget in ``_tk``; composing them
    here keeps each geometry manager's API in its own module while
    concrete wrappers inherit all three at once. ``ContainerWidget``
    in the bases makes the is-a relationship nominal, so code needing
    only a container accepts a full widget too.

    Every widget carries the :attr:`look` door to the styling facade.
    A wrapper whose principal widget is themed wears the look's minted
    style; one hosting a classic widget holds the look without acting
    on it — an option that cannot apply simply does not, per the
    styling rulings — and states that exception in its own class body.
    """

    __slots__ = ("_look",)

    def _look_targets(self) -> tuple[tk.Misc, ...]:
        """The widgets this wrapper's look considers dressing.

        The default answers ``_tk``; a composite whose principals sit
        inside a frame overrides this to name them — several where a
        bank of parts shares the look. Targets that are not themed
        widgets the measurements cover are skipped at wearing time, so
        an override lists its principals without filtering.
        """
        return (self._tk,)

    @property
    def look(self) -> Look | None:
        """The look this widget wears, or None for the library's base style.

        Assigning dresses the widget's themed principals with the
        look's compatible subset and keeps following the look as it is
        edited; None returns them to the base style. On a wrapper with
        no themed principal the look is held without acting — nothing
        in it can apply — which the wrapper's own class body documents.
        """
        try:
            return self._look
        except AttributeError:
            return None

    @look.setter
    def look(self, value: Look | None) -> None:
        for target in self._look_targets():
            if not isinstance(target, tk.Widget) or target.winfo_class() not in STYLE_OPTION_NAMES:
                continue
            worn = "" if value is None else value._wear(target) or ""
            # item assignment rather than configure(style=...): typeshed types the keyword per concrete class, not here
            target["style"] = worn
        self._look = value


def wrappers_among(widgets: Sequence[tk.Misc], /) -> tuple[Widget, ...]:
    """The wrappers among ``widgets``, in the same order.

    A walk answers the wrappers the facade built and does not name what
    it did not build. A raw tkinter widget a caller made and a
    composite's own internals are absent from the answer rather than
    answered raw — asking a composite what it masters is not a door
    through its boundary. Windows are never geometry slaves, so what a
    walk answers is always a full :class:`Widget`.

    Args:
        widgets (Sequence[tk.Misc]): The Tk widgets a geometry manager
            reported.

    Returns:
        The registered wrappers among them, order kept.
    """
    found: list[Widget] = []
    for widget in widgets:
        wrapper = BaseWidget._wrappers.get((widget.tk, str(widget)))
        if isinstance(wrapper, Widget):
            found.append(wrapper)
    return tuple(found)
