"""Dialogs: modal prompts over owned, encapsulated windows.

:class:`Dialog` is the foundation every dialog builds on — see its
docstring for the whole contract. The roster's dialog functions land
here as their queue items are worked, each in a synchronous and an
``async_``-named awaitable spelling::

    from tkfacade import dialog

    where = dialog.file_save(window, default_extension="txt")
    where = await dialog.async_file_save(window)
"""

from ._dialog import Dialog as Dialog
from ._fields import DataField as DataField
from ._fields import async_data_fields as async_data_fields
from ._fields import data_fields as data_fields
from ._file import FileFilter as FileFilter
from ._file import async_directory_open as async_directory_open
from ._file import async_directory_save as async_directory_save
from ._file import async_file_open as async_file_open
from ._file import async_file_save as async_file_save
from ._file import directory_open as directory_open
from ._file import directory_save as directory_save
from ._file import file_open as file_open
from ._file import file_save as file_save
from ._message import async_confirm as async_confirm
from ._message import async_message as async_message
from ._message import confirm as confirm
from ._message import message as message
from ._textbox import async_textbox as async_textbox
from ._textbox import textbox as textbox
