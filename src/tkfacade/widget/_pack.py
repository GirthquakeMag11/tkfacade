"""The pack facet: typed delegation to Tk's pack geometry manager."""

import tkinter as tk
from types import EllipsisType
from typing import TYPE_CHECKING, Any, Self, cast, overload

from .._params import PackSetOptions
from .._types import Anchor, Fill, PackInfo, Pad, PadValue, Side
from ._base import BaseWidget

if TYPE_CHECKING:
    from ._widget import Widget

_PACK_DEFAULTS: dict[str, Any] = {
    "anchor": "center",
    "expand": False,
    "fill": "none",
    "side": "top",
    "ipadx": 0,
    "ipady": 0,
    "padx": 0,
    "pady": 0,
}
"""Options a first :meth:`PackWidget.pack` placement fills in when unnamed."""


class PackContainerWidget(BaseWidget):
    """Container half of the pack facet: managing the widgets this one packs.

    Delegates the ``pack_*`` methods every Tk widget carries —
    propagation and slave queries. The other role, being packed into a
    master, is :class:`PackWidget`; toplevel wrappers stop here, since
    a toplevel is managed by the window manager and can never be a
    pack slave.
    """

    __slots__ = ()

    def pack_slaves(self) -> tuple[Widget, ...]:
        """Return the wrappers of the widgets managed by this packer.

        Reads :meth:`tkinter.Misc.pack_slaves` and answers the
        wrappers among the slaves, per the traversal rule
        (:func:`~tkfacade.widget._widget.wrappers_among`): what the
        facade did not build is not named.

        Returns:
            The managed wrappers, in packing order.
        """
        from ._widget import wrappers_among

        return wrappers_among(self._tk.pack_slaves())

    @overload
    def pack_propagate(self) -> bool: ...
    @overload
    def pack_propagate(self, flag: bool) -> None: ...
    def pack_propagate(self, flag: bool | None = None) -> bool | None:
        """Query or set whether the master resizes to fit its packed contents.

        Delegates to :meth:`tkinter.Misc.pack_propagate`.

        Args:
            flag (bool | None): Enable or disable propagation.
                Defaults to None, meaning query without changing.

        Returns:
            The current setting if ``flag`` is None; otherwise None.
        """
        if flag is None:
            return bool(self._tk.pack_propagate())
        self._tk.pack_propagate(flag)
        return None


class PackWidget(PackContainerWidget):
    """Pack facet of a wrapper: the container half plus being a slave.

    Adds the slave role — packing this widget into its master — which
    only exists on real ``tk.Widget`` subclasses; hence the narrowed
    ``_tk``.
    """

    if TYPE_CHECKING:
        _tk: tk.Widget

    __slots__ = ()

    def pack(
        self,
        cnf: PackSetOptions | None = None,
        *,
        after: tk.Misc | BaseWidget | EllipsisType = ...,
        anchor: Anchor | EllipsisType = ...,
        before: tk.Misc | BaseWidget | EllipsisType = ...,
        expand: bool | EllipsisType = ...,
        fill: Fill | EllipsisType = ...,
        side: Side | EllipsisType = ...,
        ipadx: PadValue | EllipsisType = ...,
        ipady: PadValue | EllipsisType = ...,
        padx: Pad | EllipsisType = ...,
        pady: Pad | EllipsisType = ...,
        in_: tk.Misc | BaseWidget | EllipsisType = ...,
        **kw: Any,
    ) -> Self:
        """Place or reconfigure the widget in its master's packing order.

        Delegates to :meth:`tkinter.Pack.pack`, and is incremental the
        way Tk itself is: on a widget this packer already manages, only
        the options named are changed. The defaults below apply when
        the call first places an unmanaged widget. Also available as
        ``pack_configure``, an alias for this method.

        Args:
            cnf (PackSetOptions | None): Pack options, merged with
                keyword options. Defaults to None.
            after (tk.Misc | BaseWidget): Sibling to pack immediately
                after in the packing order; a wrapper is unwrapped.
            anchor (Anchor): Position within the parcel when the
                parcel is larger than the widget. Defaults to
                ``"center"``.
            before (tk.Misc | BaseWidget): Sibling to pack immediately
                before in the packing order; a wrapper is unwrapped.
            expand (bool): Whether the parcel grows to consume extra
                space in the master. Defaults to False.
            fill (Fill): Axes along which the widget stretches to fill
                its parcel. Defaults to ``"none"``.
            side (Side): Side of the master the widget is packed
                against. Defaults to ``"top"``.
            ipadx (PadValue): Internal horizontal padding. Defaults
                to 0.
            ipady (PadValue): Internal vertical padding. Defaults to 0.
            padx (Pad): External horizontal padding. Defaults to 0.
            pady (Pad): External vertical padding. Defaults to 0.
            in_ (tk.Misc | BaseWidget): Master to pack into, if other
                than the existing master; a wrapper is unwrapped.
            **kw (Any): Additional pack options forwarded to Tcl, for
                options :class:`PackSetOptions` doesn't cover (e.g.
                future Tk versions).

        Returns:
            This wrapper, for call chaining.

        Raises:
            TclError: If Tcl rejects an option or value.
        """
        # in_ is inserted first: Tk reads options left to right, and -in after -after/-before means append
        opts: dict[str, Any] = {}
        if in_ is not ...:
            opts["in_"] = self._as_master(in_)
        if after is not ...:
            opts["after"] = self._as_master(after)
        if before is not ...:
            opts["before"] = self._as_master(before)
        named = {
            "anchor": anchor,
            "expand": expand,
            "fill": fill,
            "side": side,
            "ipadx": ipadx,
            "ipady": ipady,
            "padx": padx,
            "pady": pady,
        }
        opts |= {name: value for name, value in named.items() if value is not ...}
        opts |= kw
        if self._tk.winfo_manager() != "pack":
            for name, default in _PACK_DEFAULTS.items():
                opts.setdefault(name, default)
        if cnf:
            opts.update(cnf)
        for name in ("in_", "after", "before"):
            if name in opts:
                opts[name] = self._as_master(opts[name])
        if "in_" in opts:
            opts = {"in_": opts.pop("in_"), **opts}
        self._tk.pack(**opts)
        return self

    pack_configure = pack

    def pack_info(self) -> PackInfo:
        """Return the widget's current pack options.

        Delegates to :meth:`tkinter.Pack.pack_info`.

        Returns:
            The pack options in effect (e.g. ``side``, ``fill``,
            ``expand``).

        Raises:
            TclError: If the widget is not currently managed by pack.
        """
        return cast(PackInfo, self._tk.pack_info())
