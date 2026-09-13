"""The Menubutton wrapper: a button that reveals a set of actions."""

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from .._types import ImageSpec, MenuDirection
from ..events import Destroyed, Event
from ..look import Look
from ..media import ImageInput, ImageWrapper, PhotoImage
from ..widget import BaseWidget, Widget
from ._menu import RuledMenu
from ._rows import MenuPart


class Menubutton(Widget, RuledMenu):
    """A themed button that opens a menu instead of running one command.

    Where a :class:`~tkfacade.Button` is one command, this is many,
    revealed rather than performed — so it takes no command of its own:
    Tk gives the widget none, and posts the menu from its own class
    bindings.

    The menu is the menubutton's, and the ``insert_*`` calls are on the
    menubutton itself, so nothing has to be named to fill it::

        picker = Menubutton(parent, "File")
        picker.insert_command("New", command=new_file)
        picker.insert_separator()
        theme = picker.insert_submenu("Theme")

    Rows come back as handles rather than being addressed by their text
    afterwards, so two rows may carry the same words and a handle held
    across other rows' deletion still names its own.

    The menubutton builds its own menu and never adopts one. Tk accepts
    a menu that is not the button's child and accepts one menu named by
    two buttons, and both leave a menu outliving or dying against the
    thing that shows it.

    Events bound here are the button's, not the menu's, and that is
    Tk's own division rather than a gap: an ordinary descendant carries
    its toplevel in its bindtags, while a popped menu does not, being a
    surface posted under a grab. What a user does in the menu arrives
    as the row's command or through its observable, which says which
    row was chosen — something a raw click could not.

    Appearance comes from the ``TMenubutton`` style rather than from
    per-widget options: no color, font, or relief rides this
    constructor.
    """

    if TYPE_CHECKING:
        _tk: ttk.Menubutton

    __slots__ = ("_parts", "_photo", "_tk_menu")

    def __init__(
        self,
        parent: tk.Misc | BaseWidget,
        /,
        text: str = "",
        *,
        direction: MenuDirection = "below",
        image: ImageInput | None = None,
        width: int | None = None,
        enabled: bool = True,
        look: Look | None = None,
    ) -> None:
        """Create the menubutton and the empty menu it opens.

        Args:
            parent (tk.Misc | BaseWidget): The widget or wrapper the
                menubutton is created inside.
            text (str): The text on the button. Defaults to ``""``.
            direction (MenuDirection): Where the menu appears relative
                to the button. Defaults to ``"below"``.
            image (ImageInput | None): Picture drawn on the button;
                anything :class:`~tkfacade.ImageWrapper` accepts.
                Defaults to None.
            width (int | None): Width in characters. Defaults to None,
                leaving Tk to size to the content.
            enabled (bool): Whether the menubutton starts activatable.
                Defaults to True.
            look (Look | None): The look to wear from the start; see
                :attr:`~tkfacade.widget.Widget.look`. Defaults to None,
                the library's base style.
        """
        master = self._as_master(parent)
        self._photo: PhotoImage | None = (
            ImageWrapper(image).photo_for(master) if image is not None else None
        )
        self._tk = ttk.Menubutton(
            master,
            text=text,
            direction=direction,
            image="" if self._photo is None else self._photo,
            state="normal" if enabled else "disabled",
        )
        if width is not None:
            self._tk.configure(width=width)
        self._tk_menu = tk.Menu(self._tk, tearoff=False)
        self._parts: list[MenuPart] = []
        self._tk.configure(menu=self._tk_menu)
        super().__init__()
        self.bind(Destroyed(), self._give_back_transports)
        if look is not None:
            self.look = look

    def _give_back_transports(self, event: Event) -> None:
        """Release every parked observable's ride when the button dies.

        Only the event resolving to this wrapper counts: the binding
        hears its menu's Destroy too (`hazards/tkinter.md`, *Bindings*), and
        releasing on that would steal rides from observables still
        serving live widgets elsewhere.
        """
        if event.widget is not self:
            return
        self._release_deeply()

    @property
    def text(self) -> str:
        """The text on the button."""
        return str(self._tk.cget("text"))

    @text.setter
    def text(self, value: str) -> None:
        self._tk.configure(text=value)

    @property
    def direction(self) -> MenuDirection:
        """Where the menu appears relative to the button; read live from Tk.

        Read through ``str`` rather than passed through: Tk answers an
        enumerated option with an index object that prints as the word
        but compares unequal to it (`hazards/tkinter.md`, *Query answers*).
        """
        return str(self._tk.cget("direction"))  # type: ignore[return-value]

    @direction.setter
    def direction(self, value: MenuDirection) -> None:
        self._tk.configure(direction=value)

    @property
    def image(self) -> ImageSpec | None:
        """The picture on the button, or None where there is none.

        Answers Tk's own handle for the image, the stratum this relays
        verbatim; assign any :data:`~tkfacade.ImageInput` to replace it,
        or None to take it away.
        """
        held = str(self._tk.cget("image"))
        return held or None

    @image.setter
    def image(self, value: ImageInput | None) -> None:
        photo = ImageWrapper(value).photo_for(self._tk) if value is not None else None
        self._tk.configure(image="" if photo is None else photo)
        self._photo = photo

    @property
    def enabled(self) -> bool:
        """Whether the menubutton can be activated; read live from Tk."""
        return not self._tk.instate(["disabled"])

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._tk.state(["!disabled" if value else "disabled"])
