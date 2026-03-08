"""
Persistent assistive toolbar: always on top, no focus, dwell-activated.
Buttons: Keyboard | Tab Left | Tab Right | Back | Language | Exit.
Uses Canvas rectangles+text only (no Button/Label) to avoid event interception.
"""
import tkinter as tk
import threading
import time
import ctypes
import dwell_engine

_current_lang = "EN"
_LANGS = ["EN", "HI", "MR"]
_button_lockout_until = 0.0


def _cycle_language(toolbar_instance=None):
    """Cycle through available languages and update keyboard."""
    global _current_lang
    idx = _LANGS.index(_current_lang) if _current_lang in _LANGS else 0
    idx = (idx + 1) % len(_LANGS)
    _current_lang = _LANGS[idx]
    
    # Send Alt+Shift to switch input language
    def do():
        ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)  # Alt down
        ctypes.windll.user32.keybd_event(0x10, 0, 0, 0)  # Shift down
        time.sleep(0.03)
        ctypes.windll.user32.keybd_event(0x10, 0, 0x0002, 0)  # Shift up
        ctypes.windll.user32.keybd_event(0x12, 0, 0x0002, 0)  # Alt up
    
    threading.Thread(target=do, daemon=True).start()
    
    # Update keyboard language if keyboard is open
    if toolbar_instance and getattr(toolbar_instance, "_keyboard_ref", None):
        toolbar_instance._keyboard_ref.set_language(_current_lang)


class Toolbar:
    def __init__(self, exit_callback=None):
        self.root = tk.Tk()
        self.root.title("MotionQ Toolbar")
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)
        self.root.attributes("-disabled", True)
        self.root.configure(bg="#2d2d2d", padx=4, pady=4)

        self._keyboard_ref = None
        self._exit_callback = exit_callback
        self._canvas = tk.Canvas(
            self.root,
            bg="#2d2d2d",
            highlightthickness=0,
            width=900,
            height=40,
        )
        self._canvas.pack(fill=tk.BOTH, expand=True)
        self._key_regions = []  # [(label, x, y, w, h, callback, duration_ms?, name?), ...]

        # Define toolbar buttons
        specs = [
            ("Keyboard", self._on_keyboard, None),
            ("Tab Left", self._on_tab_left, None),
            ("Tab Right", self._on_tab_right, None),
            ("Back", self._on_back, None),
            ("Language", lambda: _cycle_language(self), None),
            ("Scroll Up", self._on_scroll_up, None),
            ("Scroll Down", self._on_scroll_down, None),
            ("Click", self._on_click, 800),
            ("Double Click", self._on_double_click, 800),
            ("Exit", self._on_exit, 2000),
        ]
        
        btn_w, btn_h = 80, 32
        pad = 4
        x = pad
        
        for item in specs:
            label = item[0]
            cb = item[1]
            duration_ms = item[2] if len(item) > 2 else None
            self._key_regions.append((label, x, pad, btn_w, btn_h, cb, duration_ms))
            x += btn_w + pad

    def set_keyboard(self, keyboard_instance):
        """Set reference to keyboard instance."""
        self._keyboard_ref = keyboard_instance

    def _on_keyboard(self):
        """Toggle keyboard visibility."""
        if self._keyboard_ref:
            if getattr(self._keyboard_ref, "_visible", False):
                self._keyboard_ref.hide()
            else:
                self._keyboard_ref.show(self)

    def _on_back(self):
        """Handle back button - hide keyboard or clear click mode."""
        if self._keyboard_ref and getattr(self._keyboard_ref, "_visible", False):
            self._keyboard_ref.hide()
            return
        
        mode = dwell_engine.get_click_mode()
        if mode is not None:
            dwell_engine.set_click_mode(None)
            self._draw_buttons()
            return
        
        # Alt+Left for browser back
        def do():
            ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)        # Alt down
            time.sleep(0.05)
            ctypes.windll.user32.keybd_event(0x25, 0, 0, 0)        # Left down
            time.sleep(0.05)
            ctypes.windll.user32.keybd_event(0x25, 0, 0x0002, 0)   # Left up
            ctypes.windll.user32.keybd_event(0x12, 0, 0x0002, 0)   # Alt up
        
        threading.Thread(target=do, daemon=True).start()

    def _on_tab_left(self):
        """Ctrl+Shift+Tab for cycling tabs backwards."""
        def do():
            ctypes.windll.user32.keybd_event(0x11, 0, 0, 0)        # Ctrl down
            time.sleep(0.03)
            ctypes.windll.user32.keybd_event(0x10, 0, 0, 0)        # Shift down
            time.sleep(0.03)
            ctypes.windll.user32.keybd_event(0x09, 0, 0, 0)        # Tab down
            time.sleep(0.03)
            ctypes.windll.user32.keybd_event(0x09, 0, 0x0002, 0)   # Tab up
            ctypes.windll.user32.keybd_event(0x10, 0, 0x0002, 0)   # Shift up
            ctypes.windll.user32.keybd_event(0x11, 0, 0x0002, 0)   # Ctrl up
        
        threading.Thread(target=do, daemon=True).start()

    def _on_tab_right(self):
        """Ctrl+Tab for cycling tabs forwards."""
        def do():
            ctypes.windll.user32.keybd_event(0x11, 0, 0, 0)        # Ctrl down
            time.sleep(0.03)
            ctypes.windll.user32.keybd_event(0x09, 0, 0, 0)        # Tab down
            time.sleep(0.03)
            ctypes.windll.user32.keybd_event(0x09, 0, 0x0002, 0)   # Tab up
            ctypes.windll.user32.keybd_event(0x11, 0, 0x0002, 0)   # Ctrl up
        
        threading.Thread(target=do, daemon=True).start()

    def _on_scroll_up(self):
        """Scroll up one notch."""
        MOUSEEVENTF_WHEEL = 0x0800

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

        i = INP()
        i.type = 0
        i.mi.dwFlags = MOUSEEVENTF_WHEEL
        i.mi.mouseData = 120  # Positive for up
        i.mi.dwExtraInfo = None
        ctypes.windll.user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INP))

    def _on_scroll_down(self):
        """Scroll down one notch."""
        MOUSEEVENTF_WHEEL = 0x0800

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

        i = INP()
        i.type = 0
        i.mi.dwFlags = MOUSEEVENTF_WHEEL
        i.mi.mouseData = 0xFFFFFF88  # -120 for down (unsigned)
        i.mi.dwExtraInfo = None
        ctypes.windll.user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INP))

    def _on_click(self):
        """Toggle single-click mode."""
        global _button_lockout_until
        if time.time() < _button_lockout_until:
            return
        
        mode = dwell_engine.get_click_mode()
        # Toggle single-click mode; mutually exclusive with double-click
        if mode == "single":
            dwell_engine.set_click_mode(None)
        else:
            dwell_engine.set_click_mode("single")
        
        # Redraw immediately so button color updates
        self._draw_buttons()
        _button_lockout_until = time.time() + 2.0

    def _on_double_click(self):
        """Toggle double-click mode."""
        global _button_lockout_until
        if time.time() < _button_lockout_until:
            return
        
        mode = dwell_engine.get_click_mode()
        # Toggle double-click mode; mutually exclusive with single-click
        if mode == "double":
            dwell_engine.set_click_mode(None)
        else:
            dwell_engine.set_click_mode("double")
        
        # Redraw immediately so button color updates
        self._draw_buttons()
        _button_lockout_until = time.time() + 2.0

    def _on_exit(self):
        """Exit the application."""
        print("[EXIT] Shutting down MotionQ")
        import os
        os._exit(0)

    def _draw_buttons(self):
        """Draw toolbar buttons on canvas."""
        self._canvas.delete("all")
        mode = dwell_engine.get_click_mode()
        
        for item in self._key_regions:
            label, x, y, w, h = item[0], item[1], item[2], item[3], item[4]
            
            # Determine button color based on state
            fill = "#3d3d3d"  # Default gray
            if label == "Click" and mode == "single":
                fill = "#00aa00"  # Green when click mode ON
            elif label == "Double Click" and mode == "double":
                fill = "#cc6600"  # Orange when double-click mode ON
            
            # Draw button rectangle
            self._canvas.create_rectangle(x, y, x + w, y + h, fill=fill, outline="#555")
            
            # Draw button text
            self._canvas.create_text(
                x + w // 2, y + h // 2, 
                text=label, fill="white", 
                font=("Segoe UI", 10)
            )

    def register_targets(self):
        """Register all toolbar buttons as dwell targets."""
        self._draw_buttons()
        self.root.update_idletasks()
        self.root.update()
        
        pad = 4
        for item in self._key_regions:
            label, lx, ly, lw, lh, cb = item[0], item[1], item[2], item[3], item[4], item[5]
            duration_ms = item[6] if len(item) > 6 else None
            
            # Calculate absolute screen coordinates
            screen_x = self.root.winfo_rootx() + pad + lx
            screen_y = self.root.winfo_rooty() + pad + ly
            
            # Register with dwell engine
            dwell_engine.register_target(
                screen_x, screen_y, lw, lh, cb, 
                name=label, duration_ms=duration_ms
            )

    def update(self):
        """Update the toolbar (call from main loop)."""
        self.root.update_idletasks()
        self.root.update()

    def destroy(self):
        """Clean up resources."""
        try:
            self.root.destroy()
        except tk.TclError:
            pass


def set_language(lang):
    """Global function to set current language."""
    global _current_lang
    _current_lang = lang