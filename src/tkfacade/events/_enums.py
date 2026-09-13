"""Enumerations of the strings and bits that make up Tk event patterns."""

from enum import IntEnum, IntFlag, StrEnum


class EventType(StrEnum):
    """Physical event type names accepted as the type field of a binding.

    ``KEY`` is an alias spelling of ``KEY_PRESS`` and ``BUTTON`` of
    ``BUTTON_PRESS``; both bind identically. ``CIRCULATE`` is not
    bindable in Tk 8.6.15.
    """

    # --- Keyboard
    KEY = "Key"
    KEY_PRESS = "KeyPress"
    KEY_RELEASE = "KeyRelease"

    # --- Mouse
    BUTTON = "Button"
    BUTTON_PRESS = "ButtonPress"
    BUTTON_RELEASE = "ButtonRelease"
    MOTION = "Motion"
    MOUSE_WHEEL = "MouseWheel"
    ENTER = "Enter"
    LEAVE = "Leave"

    # --- Focus
    FOCUS_IN = "FocusIn"
    FOCUS_OUT = "FocusOut"

    # --- Lifecycle and geometry
    CONFIGURE = "Configure"
    MAP = "Map"
    UNMAP = "Unmap"
    EXPOSE = "Expose"
    VISIBILITY = "Visibility"
    DESTROY = "Destroy"
    CREATE = "Create"

    # --- Toplevel activation (Windows / macOS)
    ACTIVATE = "Activate"
    DEACTIVATE = "Deactivate"

    # --- X11 / window-manager plumbing, rarely delivered
    CIRCULATE = "Circulate"
    COLORMAP = "Colormap"
    GRAVITY = "Gravity"
    PROPERTY = "Property"
    REPARENT = "Reparent"
    CONFIGURE_REQUEST = "ConfigureRequest"
    MAP_REQUEST = "MapRequest"
    RESIZE_REQUEST = "ResizeRequest"


class EventModifier(StrEnum):
    """Pattern prefixes that are neither click counts nor state bits.

    Modifiers, not event types: each stands before the type field of a
    pattern — ``<B1-Motion>`` is motion with button 1 held,
    ``<Any-KeyPress>`` a key press whatever else is held — and Tk
    rejects every one of them in the type position itself. Tk also
    accepts the long spellings ``Button1``..``Button5`` for held
    buttons; only the short forms are enumerated, one name per idea.
    """

    BUTTON1 = "B1"
    BUTTON2 = "B2"
    BUTTON3 = "B3"
    BUTTON4 = "B4"
    BUTTON5 = "B5"

    # --- Match regardless of other modifiers
    ANY = "Any"


class ModifierState(IntFlag):
    """Bit values of ``%s`` / ``event.state``. Every value measured on Windows.

    ``MOD1`` is Command and ``MOD2`` is Option on macOS — identical bits,
    so they are not repeated. Test a held button with
    ``state & ModifierState.BUTTON1``.
    """

    SHIFT = 1
    LOCK = 2
    CONTROL = 4
    MOD1 = 8
    MOD2 = 16
    MOD3 = 32
    MOD4 = 64
    MOD5 = 128
    BUTTON1 = 256
    BUTTON2 = 512
    BUTTON3 = 1024
    BUTTON4 = 2048
    BUTTON5 = 4096
    META = 65536
    ALT = 131072
    EXTENDED = 262144


class MouseButton(IntEnum):
    """Button numbers valid as the detail of a Button/ButtonRelease pattern.

    ``4`` and ``5`` carry the wheel on X11 only; Windows and macOS use
    ``MouseWheel`` instead. Buttons 6 and 7 are rejected by Tk 8.6.15 —
    they arrive in Tk 8.7.
    """

    LEFT = 1
    MIDDLE = 2
    RIGHT = 3
    WHEEL_UP_X11 = 4
    WHEEL_DOWN_X11 = 5


class CrossingDetail(StrEnum):
    """Values of ``%d`` / ``event.detail`` on Enter and Leave.

    ``INFERIOR`` fires Leave when the pointer moves onto a child — filter
    it out or hover highlighting will flicker.
    """

    ANCESTOR = "NotifyAncestor"
    VIRTUAL = "NotifyVirtual"
    INFERIOR = "NotifyInferior"
    NONLINEAR = "NotifyNonlinear"
    NONLINEAR_VIRTUAL = "NotifyNonlinearVirtual"
    POINTER = "NotifyPointer"
    POINTER_ROOT = "NotifyPointerRoot"
    NONE = "NotifyDetailNone"


class CrossingMode(StrEnum):
    """Values of ``%m`` on Enter and Leave: why the crossing happened.

    ``GRAB`` and ``UNGRAB`` fire when a menu or modal takes the pointer,
    with no real move.
    """

    NORMAL = "NotifyNormal"
    GRAB = "NotifyGrab"
    UNGRAB = "NotifyUngrab"
    WHILE_GRABBED = "NotifyWhileGrabbed"


class VisibilityState(StrEnum):
    """Values of ``%s`` on a Visibility event. Round-tripped through Tk."""

    UNOBSCURED = "VisibilityUnobscured"
    PARTIALLY_OBSCURED = "VisibilityPartiallyObscured"
    FULLY_OBSCURED = "VisibilityFullyObscured"


class Substitution(StrEnum):
    """Percent codes Tk replaces in a Tcl-level binding script.

    ``%r`` is not a substitution — Tk passes it through as a literal
    ``"r"``. Codes not applicable to the current event type substitute
    as ``"??"``.
    """

    SERIAL = "%#"
    ABOVE = "%a"
    BUTTON = "%b"
    COUNT = "%c"
    DETAIL = "%d"
    FOCUS = "%f"
    HEIGHT = "%h"
    WINDOW_ID = "%i"
    KEYCODE = "%k"
    MODE = "%m"
    OVERRIDE_REDIRECT = "%o"
    PLACE = "%p"
    STATE = "%s"
    TIME = "%t"
    WIDTH = "%w"
    X = "%x"
    Y = "%y"
    CHAR = "%A"
    BORDER_WIDTH = "%B"
    DELTA = "%D"
    SENT_EVENT = "%E"
    KEYSYM = "%K"
    MATCHES = "%M"
    KEYSYM_NUM = "%N"
    PROPERTY = "%P"
    ROOT_WINDOW = "%R"
    SUBWINDOW = "%S"
    TYPE = "%T"
    WIDGET = "%W"
    X_ROOT = "%X"
    Y_ROOT = "%Y"
    PERCENT = "%%"


class VirtualEvent(StrEnum):
    """The virtual events shipped with Tk, by bare name.

    Any name is a bindable virtual event; these are the ones Tk itself
    fires, so they are the ones the library can account for out of the
    box. Values carry no ``<<>>`` brackets — the ``Virtual``
    specification spells the pattern.
    """

    # --- Clipboard
    COPY = "Copy"
    CUT = "Cut"
    PASTE = "Paste"
    PASTE_SELECTION = "PasteSelection"
    CLEAR = "Clear"

    # --- Undo
    UNDO = "Undo"
    REDO = "Redo"

    # --- Caret movement
    PREV_CHAR = "PrevChar"
    NEXT_CHAR = "NextChar"
    PREV_LINE = "PrevLine"
    NEXT_LINE = "NextLine"
    PREV_WORD = "PrevWord"
    NEXT_WORD = "NextWord"
    PREV_PARA = "PrevPara"
    NEXT_PARA = "NextPara"
    LINE_START = "LineStart"
    LINE_END = "LineEnd"

    # --- Selection
    SELECT_PREV_CHAR = "SelectPrevChar"
    SELECT_NEXT_CHAR = "SelectNextChar"
    SELECT_PREV_LINE = "SelectPrevLine"
    SELECT_NEXT_LINE = "SelectNextLine"
    SELECT_PREV_WORD = "SelectPrevWord"
    SELECT_NEXT_WORD = "SelectNextWord"
    SELECT_PREV_PARA = "SelectPrevPara"
    SELECT_NEXT_PARA = "SelectNextPara"
    SELECT_LINE_START = "SelectLineStart"
    SELECT_LINE_END = "SelectLineEnd"
    SELECT_ALL = "SelectAll"
    SELECT_NONE = "SelectNone"
    TOGGLE_SELECTION = "ToggleSelection"

    # --- Focus traversal and menus
    NEXT_WINDOW = "NextWindow"
    PREV_WINDOW = "PrevWindow"
    CONTEXT_MENU = "ContextMenu"

    # --- Text widget notifications
    MODIFIED = "Modified"
    SELECTION = "Selection"
    UNDO_STACK = "UndoStack"
    WIDGET_VIEW_SYNC = "WidgetViewSync"

    # --- Other widget notifications
    LISTBOX_SELECT = "ListboxSelect"
    MENU_SELECT = "MenuSelect"
    TREEVIEW_SELECT = "TreeviewSelect"
    TREEVIEW_OPEN = "TreeviewOpen"
    TREEVIEW_CLOSE = "TreeviewClose"
    NOTEBOOK_TAB_CHANGED = "NotebookTabChanged"
    COMBOBOX_SELECTED = "ComboboxSelected"
    INCREMENT = "Increment"
    DECREMENT = "Decrement"
    INVOKE = "Invoke"

    # --- Application and system
    THEME_CHANGED = "ThemeChanged"
    TRAVERSE_IN = "TraverseIn"
    TRAVERSE_OUT = "TraverseOut"
    ALT_UNDERLINED = "AltUnderlined"
    FONTCHOOSER_VISIBILITY = "TkFontchooserVisibility"
    FONTCHOOSER_FONT_CHANGED = "TkFontchooserFontChanged"

    # --- macOS input-method editor
    IME_START_MARKED_TEXT = "TkStartIMEMarkedText"
    IME_END_MARKED_TEXT = "TkEndIMEMarkedText"
    IME_CLEAR_MARKED_TEXT = "TkClearIMEMarkedText"
    IME_ACCENT_BACKSPACE = "TkAccentBackspace"


class ConsoleVirtualEvent(StrEnum):
    """Events of the wish built-in console, by bare name.

    NOT reachable from tkinter; values carry no ``<<>>`` brackets.
    """

    EVAL = "Console_Eval"
    CLEAR = "Console_Clear"
    CLEAR_LINE = "Console_ClearLine"
    KILL_LINE = "Console_KillLine"
    TAB = "Console_Tab"
    TRANSPOSE = "Console_Transpose"
    SAVE_COMMAND = "Console_SaveCommand"
    PREV_IMMEDIATE = "Console_PrevImmediate"
    NEXT_IMMEDIATE = "Console_NextImmediate"
    PREV_SEARCH = "Console_PrevSearch"
    NEXT_SEARCH = "Console_NextSearch"
    EXPAND = "Console_Expand"
    EXPAND_FILE = "Console_ExpandFile"
    EXPAND_PROC = "Console_ExpandProc"
    EXPAND_VAR = "Console_ExpandVar"
    FIT_SCREEN_WIDTH = "Console_FitScreenWidth"
    FONT_SIZE_INCR = "Console_FontSizeIncr"
    FONT_SIZE_DECR = "Console_FontSizeDecr"


class Key(StrEnum):
    """Keysym names valid as the detail of a KeyPress or KeyRelease pattern.

    Values are the canonical spellings Tk reports in ``event.keysym``,
    so members also compare correctly against live events. Verified on
    Tcl/Tk 8.6.15.

    Three members exist only in Tk's Windows keysym table and X11
    rejects them at bind time (``bad event type or keysym``):
    :attr:`LEFT_WINDOWS`, :attr:`RIGHT_WINDOWS`, and
    :attr:`CONTEXT_MENU`. Their X11 counterparts are
    :attr:`LEFT_SUPER`, :attr:`RIGHT_SUPER`, and :attr:`MENU`, so
    portable code binds per platform.
    """

    # --- Whitespace and editing ----------------------------------------------
    SPACE = "space"
    BACKSPACE = "BackSpace"
    TAB = "Tab"
    X11_SHIFT_TAB = "ISO_Left_Tab"
    LINEFEED = "Linefeed"
    CLEAR = "Clear"
    ENTER = "Return"
    ESCAPE = "Escape"
    DELETE = "Delete"
    INSERT = "Insert"

    # --- Navigation ----------------------------------------------------------
    LEFT_ARROW = "Left"
    RIGHT_ARROW = "Right"
    UP_ARROW = "Up"
    DOWN_ARROW = "Down"
    HOME = "Home"
    END = "End"
    PAGE_UP = "Prior"
    PAGE_DOWN = "Next"
    BEGIN = "Begin"

    # --- Letters (case selects the keysym; uppercase implies Shift) ----------
    A_LOWER = "a"
    B_LOWER = "b"
    C_LOWER = "c"
    D_LOWER = "d"
    E_LOWER = "e"
    F_LOWER = "f"
    G_LOWER = "g"
    H_LOWER = "h"
    I_LOWER = "i"
    J_LOWER = "j"
    K_LOWER = "k"
    L_LOWER = "l"
    M_LOWER = "m"
    N_LOWER = "n"
    O_LOWER = "o"
    P_LOWER = "p"
    Q_LOWER = "q"
    R_LOWER = "r"
    S_LOWER = "s"
    T_LOWER = "t"
    U_LOWER = "u"
    V_LOWER = "v"
    W_LOWER = "w"
    X_LOWER = "x"
    Y_LOWER = "y"
    Z_LOWER = "z"

    A_UPPER = "A"
    B_UPPER = "B"
    C_UPPER = "C"
    D_UPPER = "D"
    E_UPPER = "E"
    F_UPPER = "F"
    G_UPPER = "G"
    H_UPPER = "H"
    I_UPPER = "I"
    J_UPPER = "J"
    K_UPPER = "K"
    L_UPPER = "L"
    M_UPPER = "M"
    N_UPPER = "N"
    O_UPPER = "O"
    P_UPPER = "P"
    Q_UPPER = "Q"
    R_UPPER = "R"
    S_UPPER = "S"
    T_UPPER = "T"
    U_UPPER = "U"
    V_UPPER = "V"
    W_UPPER = "W"
    X_UPPER = "X"
    Y_UPPER = "Y"
    Z_UPPER = "Z"

    # --- Digits (unshifted number row) ---------------------------------------
    DIGIT_0 = "0"
    DIGIT_1 = "1"
    DIGIT_2 = "2"
    DIGIT_3 = "3"
    DIGIT_4 = "4"
    DIGIT_5 = "5"
    DIGIT_6 = "6"
    DIGIT_7 = "7"
    DIGIT_8 = "8"
    DIGIT_9 = "9"

    # --- ASCII punctuation ---------------------------------------------------
    EXCLAMATION_MARK = "exclam"
    QUOTATION_MARK = "quotedbl"
    NUMBER_SIGN = "numbersign"
    DOLLAR_SIGN = "dollar"
    PERCENT_SIGN = "percent"
    AMPERSAND = "ampersand"
    APOSTROPHE = "apostrophe"
    LEFT_PAREN = "parenleft"
    RIGHT_PAREN = "parenright"
    ASTERISK = "asterisk"
    PLUS_SIGN = "plus"
    COMMA = "comma"
    MINUS_SIGN = "minus"
    PERIOD = "period"
    FORWARD_SLASH = "slash"
    COLON = "colon"
    SEMICOLON = "semicolon"
    LESS_THAN = "less"
    EQUALS = "equal"
    GREATER_THAN = "greater"
    QUESTION_MARK = "question"
    AT_SIGN = "at"
    LEFT_BRACKET = "bracketleft"
    BACK_SLASH = "backslash"
    RIGHT_BRACKET = "bracketright"
    CARET = "asciicircum"
    UNDERSCORE = "underscore"
    BACK_TICK = "grave"
    LEFT_BRACE = "braceleft"
    BAR = "bar"
    RIGHT_BRACE = "braceright"
    TILDE = "asciitilde"

    # --- Function keys -------------------------------------------------------
    F1 = "F1"
    F2 = "F2"
    F3 = "F3"
    F4 = "F4"
    F5 = "F5"
    F6 = "F6"
    F7 = "F7"
    F8 = "F8"
    F9 = "F9"
    F10 = "F10"
    F11 = "F11"
    F12 = "F12"
    F13 = "F13"
    F14 = "F14"
    F15 = "F15"
    F16 = "F16"
    F17 = "F17"
    F18 = "F18"
    F19 = "F19"
    F20 = "F20"
    F21 = "F21"
    F22 = "F22"
    F23 = "F23"
    F24 = "F24"
    F25 = "F25"
    F26 = "F26"
    F27 = "F27"
    F28 = "F28"
    F29 = "F29"
    F30 = "F30"
    F31 = "F31"
    F32 = "F32"
    F33 = "F33"
    F34 = "F34"
    F35 = "F35"

    # --- Keypad (NumLock off yields the named variant, on yields the digit) --
    KEYPAD_0 = "KP_0"
    KEYPAD_1 = "KP_1"
    KEYPAD_2 = "KP_2"
    KEYPAD_3 = "KP_3"
    KEYPAD_4 = "KP_4"
    KEYPAD_5 = "KP_5"
    KEYPAD_6 = "KP_6"
    KEYPAD_7 = "KP_7"
    KEYPAD_8 = "KP_8"
    KEYPAD_9 = "KP_9"
    KEYPAD_PLUS_SIGN = "KP_Add"
    KEYPAD_MINUS_SIGN = "KP_Subtract"
    KEYPAD_ASTERISK = "KP_Multiply"
    KEYPAD_FORWARD_SLASH = "KP_Divide"
    KEYPAD_PERIOD = "KP_Decimal"
    KEYPAD_SEPARATOR = "KP_Separator"
    KEYPAD_EQUALS = "KP_Equal"
    KEYPAD_ENTER = "KP_Enter"
    KEYPAD_SPACE = "KP_Space"
    KEYPAD_TAB = "KP_Tab"
    KEYPAD_DELETE = "KP_Delete"
    KEYPAD_INSERT = "KP_Insert"
    KEYPAD_BEGIN = "KP_Begin"
    KEYPAD_HOME = "KP_Home"
    KEYPAD_END = "KP_End"
    KEYPAD_UP_ARROW = "KP_Up"
    KEYPAD_DOWN_ARROW = "KP_Down"
    KEYPAD_LEFT_ARROW = "KP_Left"
    KEYPAD_RIGHT_ARROW = "KP_Right"
    KEYPAD_PAGE_UP = "KP_Prior"
    KEYPAD_PAGE_DOWN = "KP_Next"
    KEYPAD_F1 = "KP_F1"
    KEYPAD_F2 = "KP_F2"
    KEYPAD_F3 = "KP_F3"
    KEYPAD_F4 = "KP_F4"

    # --- Modifier keys pressed on their own ----------------------------------
    LEFT_SHIFT = "Shift_L"
    RIGHT_SHIFT = "Shift_R"
    LEFT_CONTROL = "Control_L"
    RIGHT_CONTROL = "Control_R"
    LEFT_ALT = "Alt_L"
    RIGHT_ALT = "Alt_R"
    LEFT_META = "Meta_L"
    RIGHT_META = "Meta_R"
    LEFT_SUPER = "Super_L"
    RIGHT_SUPER = "Super_R"
    LEFT_HYPER = "Hyper_L"
    RIGHT_HYPER = "Hyper_R"

    # --- Lock keys -----------------------------------------------------------
    CAPS_LOCK = "Caps_Lock"
    SHIFT_LOCK = "Shift_Lock"
    NUM_LOCK = "Num_Lock"
    SCROLL_LOCK = "Scroll_Lock"

    # --- OS and menu keys ----------------------------------------------------
    LEFT_WINDOWS = "Win_L"
    RIGHT_WINDOWS = "Win_R"
    CONTEXT_MENU = "App"
    MENU = "Menu"

    # --- System and legacy terminal keys -------------------------------------
    PRINT_SCREEN = "Print"
    SYS_REQ = "Sys_Req"
    PAUSE = "Pause"
    BREAK = "Break"
    CANCEL = "Cancel"
    HELP = "Help"
    SELECT = "Select"
    EXECUTE = "Execute"
    UNDO = "Undo"
    REDO = "Redo"
    FIND = "Find"

    # --- Compose and input-method --------------------------------------------
    COMPOSE = "Multi_key"
    MODE_SWITCH = "Mode_switch"
