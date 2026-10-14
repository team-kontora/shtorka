"""A global hotkey such as Ctrl+Space, registered with Windows for one window."""
import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
# holding the keys down must not fire it over and over
MOD_NOREPEAT = 0x4000
HOTKEY_ID = 1
# a second id, so that checking a combination never disturbs the one in use
CHECK_ID = 2

MODIFIERS = {"ctrl": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT, "win": MOD_WIN}
NAMED_KEYS = {"space": 0x20, "`": 0xC0, "ё": 0xC0}
F_KEYS = {f"f{n}": 0x6F + n for n in range(1, 25)}
# how the settings spell what parse() reads
MODIFIER_NAMES = [("Ctrl", MOD_CONTROL), ("Alt", MOD_ALT), ("Shift", MOD_SHIFT), ("Win", MOD_WIN)]
KEY_NAMES = {0x20: "Space", 0xC0: "`"}


def parse(spec) -> tuple[int, int] | None:
    """'Ctrl+Space' as (modifiers, virtual key code), or None when it is not a usable hotkey.

    A key other than F1-F24 needs Ctrl, Alt or Win with it, so that the hotkey never takes over plain typing.
    """
    if not isinstance(spec, str):
        return None
    *mods, key = (part.strip().lower() for part in spec.split("+"))
    if len(set(mods)) != len(mods) or not all(m in MODIFIERS for m in mods):
        return None
    if key in F_KEYS:
        vk = F_KEYS[key]
    elif key in NAMED_KEYS:
        vk = NAMED_KEYS[key]
    elif len(key) == 1 and key.isascii() and key.isalnum():
        vk = ord(key.upper())
    else:
        return None
    modifiers = 0
    for m in mods:
        modifiers |= MODIFIERS[m]
    if key not in F_KEYS and not modifiers & (MOD_CONTROL | MOD_ALT | MOD_WIN):
        return None
    return modifiers, vk


def modifier_names(modifiers: int) -> list[str]:
    return [name for name, flag in MODIFIER_NAMES if modifiers & flag]


def spec(modifiers: int, vk: int) -> str:
    """The settings spelling of pressed keys, 'Ctrl+Shift+K', or "" for a key that cannot be a hotkey.

    It goes by the virtual key, not the typed character, so Ctrl+Q stays Ctrl+Q in any keyboard layout.
    """
    if 0x70 <= vk <= 0x87:
        key = f"F{vk - 0x6F}"
    elif vk in KEY_NAMES:
        key = KEY_NAMES[vk]
    elif 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        key = chr(vk)
    else:
        return ""
    return "+".join([*modifier_names(modifiers), key])


def available(keys: tuple[int, int]) -> bool:
    """False when another program holds the combination, so registering it would fail."""
    modifiers, vk = keys
    if not user32.RegisterHotKey(None, CHECK_ID, modifiers | MOD_NOREPEAT, vk):
        return False
    user32.UnregisterHotKey(None, CHECK_ID)
    return True


class Hotkey:
    """Holds the hotkey only while it is wanted, so that other programs keep the keys the rest of the time."""

    def __init__(self, spec):
        self.keys = parse(spec)
        self._hwnd: int | None = None

    def hold(self, hwnd: int, wanted: bool) -> None:
        if not self.keys:
            return
        if wanted and self._hwnd is None:
            modifiers, vk = self.keys
            # fails while another program holds the same keys; the next call tries again
            if user32.RegisterHotKey(hwnd, HOTKEY_ID, modifiers | MOD_NOREPEAT, vk):
                self._hwnd = hwnd
        elif not wanted and self._hwnd is not None:
            user32.UnregisterHotKey(self._hwnd, HOTKEY_ID)
            self._hwnd = None
