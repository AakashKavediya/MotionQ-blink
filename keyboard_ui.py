"""
Virtual keyboard: dwell-operated overlay, EN / HI / MR layouts, prediction bar.
Uses Canvas only (no Button/Label) to prevent event interception and system hang.
"""
import json
import os
import time
import threading
import tkinter as tk
from pynput.keyboard import Key, Controller as KeyController

import dwell_engine

# Global variable to store last target window
_last_target_hwnd = None

def set_last_target(hwnd):
    """Store the last target window handle for keyboard focus."""
    global _last_target_hwnd
    _last_target_hwnd = hwnd

def get_last_target():
    """Return the last target window handle."""
    return _last_target_hwnd

_key_controller = KeyController()
_script_dir = os.path.dirname(os.path.abspath(__file__))

# Keyboard layouts
_EN_LAYOUT = [
    ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"],
    ["a", "s", "d", "f", "g", "h", "j", "k", "l"],
    ["z", "x", "c", "v", "b", "n", "m", "⌫"],
    [" ", "↵"],
]
_HI_LAYOUT = [
    ["अ", "आ", "इ", "ई", "उ", "ऊ", "ए", "ऐ", "ओ", "औ"],
    ["क", "ख", "ग", "घ", "ङ", "च", "छ", "ज", "झ"],
    ["ट", "ठ", "ड", "ढ", "ण", "त", "थ", "द", "ध", "⌫"],
    [" ", "↵"],
]
_MR_LAYOUT = [
    ["अ", "आ", "इ", "ई", "उ", "ऊ", "ए", "ऐ", "ओ", "औ"],
    ["क", "ख", "ग", "घ", "ङ", "च", "छ", "ज", "झ"],
    ["ट", "ठ", "ड", "ढ", "ण", "त", "थ", "द", "ध", "⌫"],
    [" ", "↵"],
]

KEY_SIZE = 80
PREDICTION_DEBOUNCE_MS = 200
PREDICTION_MIN_CHARS = 2


def _load_predictions_hi():
    """Load Hindi predictions from JSON file."""
    path = os.path.join(_script_dir, "prediction_hi.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading Hindi predictions: {e}")
    return {}


def _load_predictions_mr():
    """Load Marathi predictions from JSON file."""
    path = os.path.join(_script_dir, "prediction_mr.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading Marathi predictions: {e}")
    return {}


def _english_predictions(prefix):
    """Generate English word predictions."""
    try:
        from wordfreq import word_frequency
        prefix = prefix.lower()
        if len(prefix) < 2:
            return []
        _common = (
            "the and that have with this for not you are but can his they from she "
            "when your would there what about which their will each make how said "
        ).split()
        seen = set()
        words = []
        for w in _common:
            if w not in seen and w.startswith(prefix):
                seen.add(w)
                words.append((w, word_frequency(w, "en")))
        words.sort(key=lambda x: -x[1])
        return [w for w, _ in words[:3]]
    except ImportError:
        # Fallback if wordfreq not installed
        common_words = ["the", "and", "for", "you", "are", "can", "with", "have"]
        return [w for w in common_words if w.startswith(prefix)][:3]
    except Exception as e:
        print(f"English prediction error: {e}")
        return []


class VirtualKeyboard:
    def __init__(self, toolbar_instance=None):
        self.root = tk.Toplevel()
        self.root.title("MotionQ Keyboard")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.92)
        self.root.attributes("-disabled", True)
        self.root.config(cursor="none")
        self.root.withdraw()

        self._visible = False
        self._toolbar_ref = toolbar_instance
        self.window = self.root
        self._toolbar = toolbar_instance
        self._lang = "EN"
        self._input_buffer = ""
        self._last_prediction_time = 0
        self._predictions = []
        self._pred_hi = _load_predictions_hi()
        self._pred_mr = _load_predictions_mr()

        self._canvas = tk.Canvas(self.root, bg="#1a1a1a", highlightthickness=0)
        self._canvas.pack(fill=tk.BOTH, expand=True)
        self._key_regions = []  # [(char, x, y, w, h, callback), ...]
        self._pred_regions = []  # [(text, x, y, w, h, callback), ...]
        self._keys = []  # [{char, canvas_x, canvas_y, width, height}, ...]

    def set_toolbar(self, toolbar_instance):
        """Set the toolbar reference."""
        self._toolbar_ref = toolbar_instance
        self._toolbar = toolbar_instance

    def _get_layout(self):
        """Get current keyboard layout based on language."""
        if self._lang == "HI":
            return _HI_LAYOUT
        if self._lang == "MR":
            return _MR_LAYOUT
        return _EN_LAYOUT

    def _draw_ui(self):
        """Draw the keyboard UI on canvas."""
        self._canvas.delete("all")
        self._key_regions.clear()
        self._pred_regions.clear()
        self._keys.clear()

        # Draw prediction bar
        pred_h = 36
        self._canvas.create_rectangle(0, 0, 800, pred_h, fill="#2d2d2d", outline="")
        for i in range(3):
            txt = self._predictions[i] if i < len(self._predictions) else ""
            x, y = 8 + i * 110, 4
            w, h = 100, 28
            self._canvas.create_rectangle(x, y, x + w, y + h, fill="#3d3d3d", outline="#555")
            self._canvas.create_text(x + w // 2, y + h // 2, text=txt, fill="white", font=("Segoe UI", 11))
            idx = i
            self._pred_regions.append((txt, x, y, w, h, lambda j=idx: self._on_prediction_select(j)))

        # Draw keyboard keys
        layout = self._get_layout()
        key_sz = KEY_SIZE
        start_y = pred_h + 8
        
        for row_idx, row in enumerate(layout):
            # Calculate row width with special key sizes
            row_w = 0
            for ch in row:
                if ch == " ":
                    row_w += (key_sz * 5) + 4
                elif ch == "↵":
                    row_w += (key_sz * 2) + 4
                elif ch == "⌫":
                    row_w += (key_sz * 2) + 4
                else:
                    row_w += (key_sz + 4)
            
            start_x = (800 - row_w) // 2 + 4
            x_cursor = start_x
            
            for col_idx, char in enumerate(row):
                y = start_y + row_idx * (key_sz + 4)
                w = key_sz
                
                if char == " ":
                    w = key_sz * 5
                elif char in ("↵", "⌫"):
                    w = key_sz * 2
                
                x = x_cursor
                self._canvas.create_rectangle(x, y, x + w, y + key_sz, fill="#3d3d3d", outline="#555")
                
                # Display label
                if char == " ":
                    label = "SPACE"
                elif char == "↵":
                    label = "ENTER"
                elif char == "⌫":
                    label = "BACK"
                else:
                    label = char
                
                self._canvas.create_text(x + w // 2, y + key_sz // 2, text=label, fill="white", font=("Segoe UI", 14))
                
                ch = char
                self._key_regions.append((ch, x, y, w, key_sz, lambda c=ch: self._type_character(c)))
                self._keys.append({
                    "char": ch, 
                    "canvas_x": x, 
                    "canvas_y": y, 
                    "width": w, 
                    "height": key_sz
                })
                
                x_cursor += w + 4

    def show(self, toolbar_instance=None):
        """Show keyboard and register all targets correctly."""
        if self._visible:
            return
        
        if toolbar_instance:
            self._toolbar = toolbar_instance
            self._toolbar_ref = toolbar_instance
        
        self._visible = True
        self._predictions = []
        self._draw_ui()

        # Position at bottom of screen
        try:
            import pyautogui
            sw, sh = pyautogui.size()
            self.window.geometry(f"800x400+{(sw - 800) // 2}+{sh - 400 - 50}")
        except Exception:
            self.window.geometry("800x400")

        # Show window
        self.window.deiconify()
        self.window.attributes("-topmost", True)
        self.window.update_idletasks()

        # Wait for window to fully render and position on screen
        threading.Timer(0.4, self._register_all_targets_after_show).start()

    def hide(self):
        """Hide keyboard and restore only toolbar targets."""
        if not self._visible:
            return
        self._visible = False
        self.window.withdraw()

        # Restore only toolbar targets
        dwell_engine.clear_targets()
        if self._toolbar:
            self._toolbar.register_targets()

        print("[KEYBOARD] Hidden. Toolbar targets restored.")

    def toggle(self):
        """Toggle keyboard visibility."""
        if self._visible:
            self.hide()
        else:
            if self._toolbar_ref:
                self.show(self._toolbar_ref)
            else:
                self.show(None)

    def set_language(self, lang):
        """Set keyboard language."""
        if self._lang == lang:
            return
        self._lang = lang
        self._input_buffer = ""
        self._predictions = []
        if self._visible:
            self._draw_ui()
            threading.Timer(0.1, self._register_all_targets_after_show).start()

    def _register_all_targets_after_show(self):
        """
        Called after show() to ensure window coordinates are settled.
        Registers toolbar targets first, then keyboard targets.
        """
        # Step 1 — clear everything
        dwell_engine.clear_targets()

        # Step 2 — register toolbar buttons first
        if self._toolbar:
            self._toolbar.register_targets()

        # Step 3 — register prediction bar slots
        self.window.update_idletasks()
        root_x = self.window.winfo_rootx()
        root_y = self.window.winfo_rooty()
        
        for txt, lx, ly, lw, lh, cb in self._pred_regions:
            dwell_engine.register_target(
                root_x + lx, root_y + ly, lw, lh, cb,
                name="pred",
            )

        # Step 4 — register each keyboard key
        for key in self._keys:
            screen_x = root_x + key["canvas_x"]
            screen_y = root_y + key["canvas_y"]

            def make_callback(char):
                def callback():
                    self._type_character(char)
                return callback

            dwell_engine.register_target(
                screen_x,
                screen_y,
                key["width"],
                key["height"],
                make_callback(key["char"]),
                name=f"key:{key['char']}",
            )

        print(f"[KEYBOARD] Registered {len(self._keys)} key targets")
        print(f"[KEYBOARD] Total targets now: {len(dwell_engine.get_targets())}")

    def register_targets(self):
        """Backwards compatibility - same as _register_all_targets_after_show."""
        self._register_all_targets_after_show()

    def _type_character(self, char):
        """Type a character using Windows API."""
        def do_type():
            import ctypes
            import ctypes.wintypes
            import time
            
            # Always get a valid target window
            target = get_last_target() or ctypes.windll.user32.GetForegroundWindow()

            if target:
                current_thread = ctypes.windll.kernel32.GetCurrentThreadId()
                fg_hwnd = ctypes.windll.user32.GetForegroundWindow()
                fg_thread = ctypes.windll.user32.GetWindowThreadProcessId(fg_hwnd, None)
                ctypes.windll.user32.AttachThreadInput(current_thread, fg_thread, True)
                ctypes.windll.user32.AllowSetForegroundWindow(-1)
                ctypes.windll.user32.SetForegroundWindow(target)
                ctypes.windll.user32.AttachThreadInput(current_thread, fg_thread, False)
                time.sleep(0.05)

            # Define input structures
            class KI(ctypes.Structure):
                _fields_ = [
                    ("wVk", ctypes.c_ushort),
                    ("wScan", ctypes.c_ushort),
                    ("dwFlags", ctypes.c_ulong),
                    ("time", ctypes.c_ulong),
                    ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
                ]
                
            class INP(ctypes.Structure):
                _fields_ = [("type", ctypes.c_ulong), ("ki", KI)]

            # Handle different key types
            if char == "⌫":
                # Backspace
                def fire_vk(vk, flags):
                    i = INP()
                    i.type = 1
                    i.ki.wVk = vk
                    i.ki.dwFlags = flags
                    i.ki.dwExtraInfo = None
                    ctypes.windll.user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INP))
                
                fire_vk(0x08, 0)
                time.sleep(0.05)
                fire_vk(0x08, 0x0002)
                
            elif char == "↵":
                # Enter
                def fire_vk(vk, flags):
                    i = INP()
                    i.type = 1
                    i.ki.wVk = vk
                    i.ki.dwFlags = flags
                    i.ki.dwExtraInfo = None
                    ctypes.windll.user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INP))
                
                fire_vk(0x0D, 0)
                time.sleep(0.05)
                fire_vk(0x0D, 0x0002)
                
            elif char == " ":
                # Space
                def fire_vk(vk, flags):
                    i = INP()
                    i.type = 1
                    i.ki.wVk = vk
                    i.ki.dwFlags = flags
                    i.ki.dwExtraInfo = None
                    ctypes.windll.user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INP))
                
                fire_vk(0x20, 0)
                time.sleep(0.05)
                fire_vk(0x20, 0x0002)
                
            else:
                # All other characters - use Unicode
                KEYEVENTF_UNICODE = 0x0004
                KEYEVENTF_KEYUP = 0x0002

                def fire_unicode(scan, flags):
                    i = INP()
                    i.type = 1
                    i.ki.wVk = 0
                    i.ki.wScan = scan
                    i.ki.dwFlags = flags
                    i.ki.dwExtraInfo = None
                    ctypes.windll.user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INP))
                
                # Type each character
                for ch in char:
                    code = ord(ch)
                    fire_unicode(code, KEYEVENTF_UNICODE)
                    time.sleep(0.02)
                    fire_unicode(code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)
                    time.sleep(0.02)

            print(f"[KEYBOARD] Typed: {char}")

        threading.Thread(target=do_type, daemon=True).start()

    def _on_prediction_select(self, index):
        """Handle prediction selection."""
        self.root.attributes("-disabled", True)
        try:
            if index < len(self._predictions):
                word = self._predictions[index]
                for c in word:
                    self._type_character(c)
                self._input_buffer = ""
                self._predictions = []
                self._draw_ui()
                if self._visible:
                    threading.Timer(0.1, self._register_all_targets_after_show).start()
        finally:
            self.root.attributes("-disabled", True)

    def _update_predictions_debounced(self):
        """Debounced prediction update."""
        now = time.time() * 1000
        if now - self._last_prediction_time < PREDICTION_DEBOUNCE_MS:
            return
        self._last_prediction_time = now
        self._update_predictions()

    def _update_predictions(self):
        """Update word predictions based on current input buffer."""
        if len(self._input_buffer) < PREDICTION_MIN_CHARS:
            self._predictions = []
        else:
            prefix = self._input_buffer
            if self._lang == "EN":
                self._predictions = _english_predictions(prefix)
            elif self._lang == "HI":
                preds = self._pred_hi.get(prefix, [])
                if isinstance(preds, dict):
                    self._predictions = list(preds.keys())[:3]
                else:
                    self._predictions = preds[:3]
            else:  # MR
                preds = self._pred_mr.get(prefix, [])
                if isinstance(preds, dict):
                    self._predictions = list(preds.keys())[:3]
                else:
                    self._predictions = preds[:3]
                    
        if self._visible:
            self._draw_ui()
            threading.Timer(0.1, self._register_all_targets_after_show).start()

    def update(self):
        """Update the keyboard (call from main loop)."""
        if not self._visible:
            return
        self._update_predictions_debounced()
        self.root.update_idletasks()
        self.root.update()

    def destroy(self):
        """Clean up resources."""
        self.hide()
        try:
            self.root.destroy()
        except tk.TclError:
            pass


def set_language(lang):
    """Global function to set keyboard language."""
    pass