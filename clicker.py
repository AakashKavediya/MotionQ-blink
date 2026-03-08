import ctypes
import ctypes.wintypes
import time


def move_and_click(x, y, double=False):
    """
    Move cursor to (x, y) and fire a real left click.
    Works in all Windows applications.
    """
    x = int(x)
    y = int(y)

    # Move cursor using SetCursorPos - most reliable method
    ctypes.windll.user32.SetCursorPos(x, y)
    time.sleep(0.05)

    # Bring window at this position to foreground
    hwnd = ctypes.windll.user32.WindowFromPoint(
        ctypes.wintypes.POINT(x, y)
    )
    if hwnd:
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        time.sleep(0.1)

    # Fire click using SendInput - most reliable click method on Windows
    INPUT_MOUSE = 0
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", ctypes.c_long),
            ("dy", ctypes.c_long),
            ("mouseData", ctypes.c_ulong),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUT(ctypes.Structure):
        _fields_ = [
            ("type", ctypes.c_ulong),
            ("mi", MOUSEINPUT),
        ]

    def send_mouse(flags):
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.mi.dx = 0
        inp.mi.dy = 0
        inp.mi.mouseData = 0
        inp.mi.dwFlags = flags
        inp.mi.time = 0
        inp.mi.dwExtraInfo = None
        ctypes.windll.user32.SendInput(
            1,
            ctypes.byref(inp),
            ctypes.sizeof(INPUT)
        )

    send_mouse(MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.05)
    send_mouse(MOUSEEVENTF_LEFTUP)

    if double:
        time.sleep(0.1)
        send_mouse(MOUSEEVENTF_LEFTDOWN)
        time.sleep(0.05)
        send_mouse(MOUSEEVENTF_LEFTUP)

    print(f"[CLICK] Fired at ({x}, {y})")


def send_key(vk_code):
    """
    Send a single key press using SendInput.
    Works in all Windows applications.
    vk_code is a Windows Virtual Key code integer.
    """
    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.c_ushort),
            ("wScan", ctypes.c_ushort),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUT(ctypes.Structure):
        _fields_ = [
            ("type", ctypes.c_ulong),
            ("ki", KEYBDINPUT),
        ]

    def send(flags):
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.ki.wVk = vk_code
        inp.ki.wScan = 0
        inp.ki.dwFlags = flags
        inp.ki.time = 0
        inp.ki.dwExtraInfo = None
        ctypes.windll.user32.SendInput(
            1,
            ctypes.byref(inp),
            ctypes.sizeof(INPUT)
        )

    send(0)
    time.sleep(0.05)
    send(KEYEVENTF_KEYUP)
    print(f"[KEY] Sent VK {vk_code}")


def send_key_combo(vk_codes):
    """
    Send a key combination e.g. Ctrl+Tab.
    vk_codes is a list of Virtual Key codes pressed in order.
    """
    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.c_ushort),
            ("wScan", ctypes.c_ushort),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUT(ctypes.Structure):
        _fields_ = [
            ("type", ctypes.c_ulong),
            ("ki", KEYBDINPUT),
        ]

    def send_vk(vk, flags):
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.ki.wVk = vk
        inp.ki.wScan = 0
        inp.ki.dwFlags = flags
        inp.ki.time = 0
        inp.ki.dwExtraInfo = None
        ctypes.windll.user32.SendInput(
            1,
            ctypes.byref(inp),
            ctypes.sizeof(INPUT)
        )

    for vk in vk_codes:
        send_vk(vk, 0)
        time.sleep(0.03)

    for vk in reversed(vk_codes):
        send_vk(vk, KEYEVENTF_KEYUP)
        time.sleep(0.03)

