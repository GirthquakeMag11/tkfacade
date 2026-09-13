"""The place facet: typed delegation to Tk's place geometry manager."""

import tkinter as tk
from types import EllipsisType
from typing import TYPE_CHECKING, Any, Self, cast

from .._params import PlaceSetOptions
from .._types import Anchor, BorderMode, PadValue, PlaceInfo, Rel
from ._base import BaseWidget

if TYPE_CHECKING:
    from ._widget import Widget

_PLACE_DEFAULTS: dict[str, Any] = {
    "anchor": "nw",
    "bordermode": "inside",
    "x": 0,
    "y": 0,
    "relx": 0.0,
    "rely": 0.0,
    "width": "",
    "height": "",
    "relwidth": "",
    "relheight": "",
}
"""Options a first :meth:`PlaceWidget.place` placement fills in when unnamed."""


class PlaceContainerWidget(BaseWidget):
    """Container half of the place facet: managing the widgets this one places.

    Delegates the one ``place_*`` method every Tk widget carries, the
    slave query. The other role, being placed within a master, is
    :class:`PlaceWidget`; toplevel wrappers stop here, since a toplevel
    is managed by the window manager and can never be a place slave.
    """

    __slots__ = ()

    def place_slaves(self) -> tuple[Widget, ...]:
        """Return the wrappers of the widgets managed by this placer.

        Reads :meth:`tkinter.Misc.place_slaves` and answers the
        wrappers among the slaves, per the traversal rule
        (:func:`~tkfacade.widget._widget.wrappers_among`): what the
        facade did not build is not named.

        Returns:
            The managed wrappers, in no guaranteed order.
        """
        from ._widget import wrappers_among

        return wrappers_among(self._tk.place_slaves())


class PlaceWidget(PlaceContainerWidget):
    """Place facet of a wrapper: the container half plus being a slave.

    Adds the slave role — placing this widget within its master — which
    only exists on real ``tk.Widget`` subclasses; hence the narrowed
    ``_tk``.
    """

    if TYPE_CHECKING:
        _tk: tk.Widget

    __slots__ = ()

    def place(
        self,
        cnf: PlaceSetOptions | None = None,
        *,
        anchor: Anchor | EllipsisType = ...,
        bordermode: BorderMode | EllipsisType = ...,
        x: PadValue | EllipsisType = ...,
        y: PadValue | EllipsisType = ...,
        relx: Rel | EllipsisType = ...,
        rely: Rel | EllipsisType = ...,
        width: PadValue | EllipsisType = ...,
        height: PadValue | EllipsisType = ...,
        relwidth: Rel | EllipsisType = ...,
        relheight: Rel | EllipsisType = ...,
        in_: tk.Misc | BaseWidget | EllipsisType = ...,
        **kw: Any,
    ) -> Self:
        """Place or reconfigure the widget at fixed or relative coordinates.

        Delegates to :meth:`tkinter.Place.place`, and is incremental
        the way Tk itself is: on a widget this placer already manages,
        only the options named are changed. The defaults below apply
        when the call first places an unmanaged widget. Also available
        as ``place_configure``, an alias for this method.

        Absolute and relative options combine additively: the final
        horizontal offset is ``relx * master_width + x``, and
        likewise for the vertical axis and the width/height pairs.

        Args:
            cnf (PlaceSetOptions | None): Place options, merged with
                keyword options. Defaults to None.
            anchor (Anchor): Point of the widget positioned at the
                computed coordinate. Defaults to ``"nw"``.
            bordermode (BorderMode): Whether coordinates and relative
                sizes measure inside or outside the master's border,
                or ignore it entirely. Defaults to ``"inside"``.
            x (PadValue): Horizontal offset, in screen units. Defaults
                to 0.
            y (PadValue): Vertical offset, in screen units. Defaults
                to 0.
            relx (Rel): Horizontal offset as a fraction of the
                master's width, usually 0.0 to 1.0. Defaults to 0.0.
            rely (Rel): Vertical offset as a fraction of the master's
                height, usually 0.0 to 1.0. Defaults to 0.0.
            width (PadValue): Absolute width, in screen units.
                Defaults to ``""``, meaning the widget's natural
                (requested) width.
            height (PadValue): Absolute height, in screen units.
                Defaults to ``""``, meaning the widget's natural
                (requested) height.
            relwidth (Rel): Width as a fraction of the master's width.
                Defaults to ``""``, meaning no relative width.
            relheight (Rel): Height as a fraction of the master's
                height. Defaults to ``""``, meaning no relative
                height.
            in_ (tk.Misc | BaseWidget): Master to place into, if other
                than the existing master; a wrapper is unwrapped. Must
                be the widget's parent or a descendant of it.
            **kw (Any): Additional place options forwarded to Tcl, for
                options :class:`PlaceSetOptions` doesn't cover (e.g.
                future Tk versions).

        Returns:
            This wrapper, for call chaining.

        Raises:
            TclError: If Tcl rejects an option or value.
        """
        opts: dict[str, Any] = {}
        if in_ is not ...:
            opts["in_"] = self._as_master(in_)
        named = {
            "anchor": anchor,
            "bordermode": bordermode,
            "x": x,
            "y": y,
            "relx": relx,
            "rely": rely,
            "width": width,
            "height": height,
            "relwidth": relwidth,
            "relheight": relheight,
        }
        opts |= {name: value for name, value in named.items() if value is not ...}
        opts |= kw
        if self._tk.winfo_manager() != "place":
            for name, default in _PLACE_DEFAULTS.items():
                opts.setdefault(name, default)
        if cnf:
            opts.update(cnf)
        if "in_" in opts:
            opts["in_"] = self._as_master(opts["in_"])
        self._tk.place(**opts)
        return self

    place_configure = place

    def place_info(self) -> PlaceInfo:
        """Return the widget's current place options.

        Delegates to :meth:`tkinter.Place.place_info`.

        Returns:
            The place options in effect (e.g. ``x``, ``rely``,
            ``anchor``), or an empty dict if the widget is not
            place-managed.
        """
        return cast(PlaceInfo, self._tk.place_info())
