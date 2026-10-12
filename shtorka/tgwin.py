"""Win32 helpers: find the Telegram window, track focus, paste into it."""
import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")
gdi32 = ctypes.WinDLL("gdi32")

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x80
GW_OWNER = 4
DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14
MONITOR_DEFAULTTONEAREST = 2
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
KEYEVENTF_KEYUP = 0x0002
WM_NCLBUTTONDOWN = 0x00A1
WM_SYSCOMMAND = 0x0112
HTCAPTION = 2
SC_MAXIMIZE = 0xF030
SC_RESTORE = 0xF120
SRCCOPY = 0x00CC0020
VK_LBUTTON = 0x01
VK_CONTROL = 0x11
VK_V = 0x56

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HANDLE
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HANDLE]
gdi32.CreateCompatibleDC.argtypes = [wintypes.HANDLE]
gdi32.CreateCompatibleDC.restype = wintypes.HANDLE
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wintypes.HANDLE
gdi32.SelectObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
gdi32.SelectObject.restype = wintypes.HANDLE
gdi32.BitBlt.argtypes = [
    wintypes.HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HANDLE, ctypes.c_int, ctypes.c_int, wintypes.DWORD,
]
gdi32.GetDIBits.argtypes = [
    wintypes.HANDLE, wintypes.HANDLE, wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT,
]
gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
gdi32.DeleteDC.argtypes = [wintypes.HANDLE]
user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindow.restype = wintypes.HWND
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsZoomed.argtypes = [wintypes.HWND]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.GetDpiForWindow.argtypes = [wintypes.HWND]
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.MonitorFromWindow.restype = wintypes.HANDLE
user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT,
]
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD),
]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]


@dataclass
class Window:
    hwnd: int
    left: int
    top: int
    right: int
    bottom: int


_names: dict[int, str] = {}


def _pid(hwnd) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _process_name(pid: int) -> str:
    if pid in _names:
        return _names[pid]
    name = ""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if handle:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            name = os.path.basename(buf.value).lower()
        kernel32.CloseHandle(handle)
    if len(_names) > 512:
        _names.clear()
    _names[pid] = name
    return name


def _frame_rect(hwnd) -> wintypes.RECT:
    rect = wintypes.RECT()
    dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect))
    return rect


def _is_cloaked(hwnd) -> bool:
    cloaked = wintypes.DWORD()
    dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
    return bool(cloaked.value)


def find_main_window(names) -> Window | None:
    """Largest visible top-level window that belongs to one of the given processes."""
    best: list[Window] = []

    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        if user32.GetWindow(hwnd, GW_OWNER) or user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            return True
        if not user32.GetWindowTextLengthW(hwnd) or _is_cloaked(hwnd):
            return True
        if _process_name(_pid(hwnd)) not in names:
            return True
        r = _frame_rect(hwnd)
        win = Window(hwnd, r.left, r.top, r.right, r.bottom)
        area = (r.right - r.left) * (r.bottom - r.top)
        if not best or area > (best[0].right - best[0].left) * (best[0].bottom - best[0].top):
            best[:] = [win]
        return True

    user32.EnumWindows(EnumWindowsProc(visit), 0)
    return best[0] if best else None


def foreground_is(names) -> bool:
    """True when the focused window belongs to one of the given processes."""
    hwnd = user32.GetForegroundWindow()
    return bool(hwnd) and _process_name(_pid(hwnd)) in names


def scale(hwnd) -> float:
    return (user32.GetDpiForWindow(hwnd) or 96) / 96


def work_area(hwnd) -> wintypes.RECT:
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(info)
    user32.GetMonitorInfoW(user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST), ctypes.byref(info))
    return info.rcWork


def move(hwnd, x: int, y: int, w: int, h: int) -> None:
    user32.SetWindowPos(hwnd, None, x, y, w, h, SWP_NOZORDER | SWP_NOACTIVATE)


def screen_row(x: int, y: int, width: int) -> bytes:
    """One row of screen pixels, four bytes (B, G, R, unused) per pixel."""
    screen = user32.GetDC(None)
    memory = gdi32.CreateCompatibleDC(screen)
    bitmap = gdi32.CreateCompatibleBitmap(screen, width, 1)
    previous = gdi32.SelectObject(memory, bitmap)
    gdi32.BitBlt(memory, 0, 0, width, 1, screen, x, y, SRCCOPY)
    gdi32.SelectObject(memory, previous)
    header = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), width, -1, 1, 32)
    pixels = ctypes.create_string_buffer(width * 4)
    gdi32.GetDIBits(memory, bitmap, 0, 1, pixels, ctypes.byref(header), 0)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(memory)
    user32.ReleaseDC(None, screen)
    return pixels.raw


def find_divider(row: bytes, start: int, end: int) -> int | None:
    """Leftmost thin vertical line in the row: 1-2 pixels that differ from a flat background."""

    def pixel(i):
        return row[i * 4 : i * 4 + 3]

    def differ(a, b):
        return sum(abs(p - q) for p, q in zip(a, b))

    count = len(row) // 4
    for x in range(max(start, 2), end):
        for thickness in (1, 2):
            if x + thickness + 1 >= count:
                return None
            before, after = pixel(x - 1), pixel(x + thickness)
            flat = (
                differ(before, after) <= 6
                and differ(pixel(x - 2), before) <= 6
                and differ(pixel(x + thickness + 1), after) <= 6
            )
            if flat and all(differ(pixel(x + i), before) >= 12 for i in range(thickness)):
                return x
    return None


def is_maximized(hwnd) -> bool:
    return bool(user32.IsZoomed(hwnd))


def mouse_down() -> bool:
    return bool(user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)


def drag(hwnd) -> None:
    """Start moving the window as if its own title bar had been grabbed."""
    user32.ReleaseCapture()
    user32.SetForegroundWindow(hwnd)
    user32.PostMessageW(hwnd, WM_NCLBUTTONDOWN, HTCAPTION, 0)


def toggle_maximize(hwnd) -> None:
    user32.PostMessageW(hwnd, WM_SYSCOMMAND, SC_RESTORE if user32.IsZoomed(hwnd) else SC_MAXIMIZE, 0)


def activate(hwnd) -> None:
    user32.SetForegroundWindow(hwnd)


def send_ctrl_v() -> None:
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_V, 0, 0, 0)
    user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
