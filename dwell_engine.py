"""
Simple dwell engine for MotionQ.

- Toolbar / keyboard / other UI elements register rectangular targets.
- When the gaze-controlled cursor dwells on a target for DWELL_TIME seconds,
  that target's callback is fired.
- The dwell progress is shown as a small circle window that follows the cursor.
"""
import time
import math
import threading
import ctypes
import ctypes.wintypes
import traceback
import tkinter as tk
import pyautogui

# Configuration constants
DWELL_TIME = 1.5   # total seconds to hold still before click
STILL_RADIUS = 50    # pixels — how much movement is allowed while dwelling
DOUBLE_CLICK_RADIUS = 40   # px — "same position" for double click
DOUBLE_CLICK_WINDOW = 0.6  # seconds — time window for double click
CLICK_COOLDOWN = 1.0       # seconds between clicks when click-mode is armed

# Global state variables
_start_pos = None  # current dwell origin (cursor position)
_start_time = None  # when dwell at this position started
_last_click_pos = None
_last_click_time = 0.0
_click_mode = None  # None | "single" | "double"
_targets = []  # for eyefeature magnet; toolbar/keyboard register here
_circle_win = "dwell_circle"
_win_size = 80

_dwell_state = None  # state for target-based dwell (current target, etc.)
_click_dwell_state = None  # separate dwell state for click-mode when not over a target
_overlay_root = None
_overlay_canvas = None


def get_targets():
    """Return list of registered targets."""
    return list(_targets)


def clear_targets():
    """Remove all registered targets and reset dwell state."""
    global _targets, _start_pos, _start_time, _last_click_pos, _last_click_time
    global _dwell_state, _click_dwell_state
    _targets = []
    _start_pos = None
    _start_time = None
    _last_click_pos = None
    _last_click_time = 0.0
    _dwell_state = None
    _click_dwell_state = None


def register_target(x, y, width, height, callback, stability_radius=None, name=None, duration_ms=None):
    """
    Register a dwell target. Structure: x, y, width, height, callback, stability_radius (optional),
    name (optional, for debug), duration_ms (optional override for this target only).
    Last registered target has priority when overlapping.
    """
    _targets.append({
        "x": int(x), 
        "y": int(y), 
        "width": int(width), 
        "height": int(height),
        "callback": callback, 
        "name": name or "target", 
        "duration_ms": duration_ms,
    })


def _get_target_at(cursor_x, cursor_y):
    """Return the last-registered target containing (cursor_x, cursor_y), or None."""
    for t in reversed(_targets):
        x, y, w, h = t["x"], t["y"], t["width"], t["height"]
        if x <= cursor_x <= x + w and y <= cursor_y <= y + h:
            return t
    return None


def init():
    """Create the small transparent Tk window used to show dwell progress."""
    global _overlay_root, _overlay_canvas
    if _overlay_root is not None:
        return
    try:
        _overlay_root = tk.Toplevel()
        _overlay_root.overrideredirect(True)
        _overlay_root.attributes("-topmost", True)
        _overlay_root.attributes("-disabled", True)
        _overlay_root.configure(bg="black")
        _overlay_root.geometry(f"{_win_size}x{_win_size}+{-200}+{-200}")
        _overlay_root.attributes("-transparentcolor", "black")

        _overlay_canvas = tk.Canvas(
            _overlay_root,
            width=_win_size,
            height=_win_size,
            bg="black",
            highlightthickness=0,
        )
        _overlay_canvas.pack()

        # Ensure window is realized so we can get a real HWND
        _overlay_root.update_idletasks()
        _overlay_root.update()

        # Make window click-through using extended styles
        try:
            hwnd = _overlay_root.winfo_id()
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT)
        except Exception as e:
            print(f"Click-through setup failed (non-critical): {e}")
    except tk.TclError as e:
        print(f"Tk overlay error: {e}")
        _overlay_root = None
        _overlay_canvas = None


def _hide():
    """Hide the dwell ring window off-screen."""
    if _overlay_root is None:
        return
    try:
        _overlay_canvas.delete("all")
        _overlay_root.geometry(f"{_win_size}x{_win_size}+{-200}+{-200}")
        _overlay_root.update_idletasks()
        _overlay_root.update()
    except tk.TclError:
        pass


def _show_circle(screen_x, screen_y, progress):
    """Draw the dwell progress ring centered on the given screen coords."""
    if _overlay_root is None or _overlay_canvas is None:
        init()
    if _overlay_root is None or _overlay_canvas is None:
        return
    try:
        # Position the small window around the cursor position
        win_x = int(screen_x) - _win_size // 2
        win_y = int(screen_y) - _win_size // 2
        _overlay_root.geometry(f"{_win_size}x{_win_size}+{win_x}+{win_y}")
        _overlay_root.lift()
        _overlay_root.attributes("-topmost", True)

        _overlay_canvas.delete("all")
        c = (_win_size // 2, _win_size // 2)
        r = 28

        # Dark grey track ring
        _overlay_canvas.create_oval(
            c[0] - r, c[1] - r,
            c[0] + r, c[1] + r,
            outline="#444444",
            width=4,
        )

        # Blue progress arc sweeping clockwise from top
        extent = 360 * float(progress)
        _overlay_canvas.create_arc(
            c[0] - r, c[1] - r,
            c[0] + r, c[1] + r,
            start=90,
            extent=-extent,
            style=tk.ARC,
            outline="#3399ff",
            width=5,
        )

        _overlay_root.update_idletasks()
        _overlay_root.update()
    except tk.TclError as e:
        print(f"Circle drawing error: {e}")


# ── click ─────────────────────────────────────────────────────────────────────

def _fire_click(x, y, is_double=False):
    """Fire a mouse click at the specified coordinates."""
    def do():
        import time as T
        try:
            ctypes.windll.user32.SetCursorPos(x, y)
            T.sleep(0.1)

            hwnd = ctypes.windll.user32.WindowFromPoint(ctypes.wintypes.POINT(x, y))
            if hwnd:
                root_hwnd = ctypes.windll.user32.GetAncestor(hwnd, 2)
                target_hwnd = root_hwnd if root_hwnd else hwnd
                cur = ctypes.windll.kernel32.GetCurrentThreadId()
                fg = ctypes.windll.user32.GetForegroundWindow()
                fg_thread = ctypes.windll.user32.GetWindowThreadProcessId(fg, None)
                ctypes.windll.user32.AttachThreadInput(cur, fg_thread, True)
                ctypes.windll.user32.AllowSetForegroundWindow(-1)
                ctypes.windll.user32.SetForegroundWindow(target_hwnd)
                ctypes.windll.user32.BringWindowToTop(target_hwnd)
                ctypes.windll.user32.AttachThreadInput(cur, fg_thread, False)
                T.sleep(0.2)
                try:
                    import keyboard_ui
                    keyboard_ui.set_last_target(target_hwnd)
                except Exception:
                    pass

            class MI(ctypes.Structure):
                _fields_ = [
                    ("dx", ctypes.c_long),
                    ("dy", ctypes.c_long),
                    ("mouseData", ctypes.c_ulong),
                    ("dwFlags", ctypes.c_ulong),
                    ("time", ctypes.c_ulong),
                    ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
                ]
                
            class INP(ctypes.Structure):
                _fields_ = [("type", ctypes.c_ulong), ("mi", MI)]

            def fire(flags):
                i = INP()
                i.type = 0
                i.mi.dwFlags = flags
                i.mi.dwExtraInfo = None
                ctypes.windll.user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INP))

            fire(0x0002)   # mouse down
            T.sleep(0.05)
            fire(0x0004)   # mouse up
            if is_double:
                T.sleep(0.1)
                fire(0x0002)
                T.sleep(0.05)
                fire(0x0004)
            print(f"[CLICK] Fired {'double' if is_double else 'single'} at ({x}, {y})")
        except Exception as e:
            print(f"Click error: {e}")

    threading.Thread(target=do, daemon=True).start()


def click_at_cursor(double=False):
    """Public helper for toolbar: click at current OS cursor position."""
    x, y = pyautogui.position()
    _fire_click(int(x), int(y), is_double=double)


def set_click_mode(mode):
    """Set global click mode: None, 'single', or 'double'."""
    global _click_mode
    if mode not in (None, "single", "double"):
        mode = None
    _click_mode = mode


def get_click_mode():
    """Return current click mode: None, 'single', or 'double'."""
    return _click_mode


# ── main update — call this every frame with current cursor position ───────────

def update(cursor_x, cursor_y):
    """
    Per-frame dwell update.

    - If cursor is over a registered target, show a dwell circle and fire the
      target's callback after DWELL_TIME seconds of stable gaze.
    - If cursor is not over any target, hide the circle and reset dwell state.
    """
    global _start_pos, _start_time, _dwell_state, _click_dwell_state
    global _last_click_pos, _last_click_time, _click_mode

    now = time.time()
    pos = (int(cursor_x), int(cursor_y))

    target = _get_target_at(pos[0], pos[1])

    if target is None:
        # No UI target under cursor
        _dwell_state = None

        if _click_mode is None:
            # Click mode OFF: just hide the ring and reset
            _click_dwell_state = None
            _start_pos = None
            _start_time = None
            _hide()
            return

        # Click mode ON: treat current cursor position as a dwell target
        if _click_dwell_state is None:
            _click_dwell_state = {
                "start_time": now,
                "cursor_start": pos,
            }
            _start_pos = pos
            _start_time = now
            _show_circle(pos[0], pos[1], 0.0)
            return

        # Check stability for click-mode dwell
        dist = math.hypot(
            pos[0] - _click_dwell_state["cursor_start"][0],
            pos[1] - _click_dwell_state["cursor_start"][1],
        )
        if dist > STILL_RADIUS:
            # Too much movement; restart dwell at new position
            _click_dwell_state["start_time"] = now
            _click_dwell_state["cursor_start"] = pos
            _start_pos = pos
            _start_time = now
            _show_circle(pos[0], pos[1], 0.0)
            return

        # Compute progress for click-mode dwell
        elapsed = now - _click_dwell_state["start_time"]
        progress = min(1.0, elapsed / DWELL_TIME)
        _show_circle(pos[0], pos[1], progress)

        if progress >= 1.0 and (now - _last_click_time) >= CLICK_COOLDOWN:
            px, py = pos
            is_double = (_click_mode == "double")
            _last_click_pos = (px, py)
            _last_click_time = now
            _click_dwell_state = None
            _start_pos = None
            _start_time = None
            _hide()
            _fire_click(px, py, is_double=is_double)
        return

    # We are over a registered UI target: clear any click-mode dwell
    _click_dwell_state = None

    # Center of the target for drawing
    center_x = target["x"] + target["width"] // 2
    center_y = target["y"] + target["height"] // 2

    if _dwell_state is None or _dwell_state.get("target") is not target:
        # New target or first time: start dwell tracking
        _dwell_state = {
            "target": target,
            "start_time": now,
            "cursor_start": pos,
        }
        _start_pos = pos
        _start_time = now
        _show_circle(center_x, center_y, 0.0)
        return

    # Same target: check stability
    dist = math.hypot(
        pos[0] - _dwell_state["cursor_start"][0],
        pos[1] - _dwell_state["cursor_start"][1]
    )
    if dist > STILL_RADIUS:
        # Too much movement; restart dwell on the same target
        _dwell_state["start_time"] = now
        _dwell_state["cursor_start"] = pos
        _start_pos = pos
        _start_time = now
        _show_circle(center_x, center_y, 0.0)
        return

    # Compute progress and draw (use per-target duration if provided)
    elapsed = now - _dwell_state["start_time"]
    dwell_sec = (target.get("duration_ms") / 1000.0) if target.get("duration_ms") else DWELL_TIME
    progress = min(1.0, elapsed / dwell_sec)
    _show_circle(center_x, center_y, progress)

    if progress >= 1.0:
        cb = target.get("callback")
        _dwell_state = None
        _start_pos = None
        _start_time = None
        _hide()
        if cb is not None:
            try:
                cb()
            except Exception as e:
                print(f"Target callback error: {e}")
                traceback.print_exc()