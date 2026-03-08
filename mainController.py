"""
MotionQ runtime engine: single entry point. Eye cursor, head scroll, dwell, toolbar, keyboard.
Only this file opens the webcam. Face detection every FACE_DETECT_INTERVAL; face lost freezes cursor and shows indicator.
"""
import sys
import os
# Allow running as python motionq/motionq_engine.py from project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2
import time
import argparse
import tkinter as tk
import pyautogui
from pynput import keyboard as kb

# Import all required modules
try:
    from eyefeature import process_eye_frame
    from head import process_head_frame
    import dwell_engine
    import toolbar
    import keyboard_ui
    import calibration_manager
    import profile_manager
except ImportError as e:
    print(f"ERROR: Failed to import module: {e}")
    print("Make sure all required files are in the same directory:")
    print("  - eyefeature.py")
    print("  - head.py")
    print("  - dwell_engine.py")
    print("  - toolbar.py")
    print("  - keyboard_ui.py")
    print("  - calibration_manager.py")
    print("  - profile_manager.py")
    sys.exit(1)

# Configuration constants
FACE_DETECT_INTERVAL = 10
FACE_LOST_THRESHOLD = 5
TARGET_FRAME_TIME = 0.07  # ~14 FPS
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
PREVIEW_WIDTH = 320
PREVIEW_HEIGHT = 240

_shutdown_requested = False


def main(profile_name):
    global _shutdown_requested
    
    # Load profile
    try:
        profile = profile_manager.load_profile(profile_name)
    except Exception as e:
        print(f"Warning: Could not load profile '{profile_name}': {e}")
        profile = {}
    
    # Set dwell timing from profile if available
    try:
        dwell_cal = profile.get("dwell", {})
        if hasattr(dwell_engine, 'set_timing'):
            dwell_engine.set_timing(
                entry_delay_ms=dwell_cal.get("entry_delay_ms", 500),
                duration_ms=dwell_cal.get("duration_ms", 300),
                stability_radius=dwell_cal.get("stability_radius", 20),
            )
    except Exception as e:
        print(f"Warning: Could not set dwell timing: {e}")
    
    # Run quick calibration
    try:
        calibration_manager.run_quick_calibration()
    except Exception as e:
        print(f"Warning: Calibration failed: {e}")
        print("Continuing with default calibration...")

    # Initialize webcam
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)

    if not cap.isOpened():
        print("ERROR: Cannot access webcam")
        print("Please check:")
        print("  - Webcam is connected")
        print("  - No other app is using the webcam")
        print("  - Camera permissions are granted")
        return

    def shutdown():
        """Gracefully shutdown the application"""
        global _shutdown_requested
        print("Shutdown requested...")
        _shutdown_requested = True

    # Get screen dimensions
    screen_w, screen_h = pyautogui.size()
    
    # Initialize UI components
    try:
        toolbar_ui = toolbar.Toolbar(shutdown_callback=shutdown)
    except TypeError:
        # Fallback if shutdown_callback parameter doesn't exist
        toolbar_ui = toolbar.Toolbar()
        # Set callback manually if possible
        if hasattr(toolbar_ui, 'set_shutdown_callback'):
            toolbar_ui.set_shutdown_callback(shutdown)
    
    # Initialize dwell engine
    try:
        if hasattr(dwell_engine, 'init'):
            dwell_engine.init()
    except Exception as e:
        print(f"Warning: dwell_engine.init() failed: {e}")
    
    # Initialize keyboard
    try:
        keyboard = keyboard_ui.VirtualKeyboard(toolbar_ui)
    except TypeError:
        # Fallback if toolbar parameter doesn't exist
        keyboard = keyboard_ui.VirtualKeyboard()
    
    # Connect toolbar and keyboard
    if hasattr(toolbar_ui, 'set_keyboard'):
        toolbar_ui.set_keyboard(keyboard)
    if hasattr(keyboard, 'set_toolbar'):
        keyboard.set_toolbar(toolbar_ui)
    
    # Position toolbar at top center
    toolbar_ui.root.update_idletasks()
    toolbar_width = 700
    toolbar_x = (screen_w - toolbar_width) // 2
    toolbar_ui.root.geometry(f"{toolbar_width}x40+{toolbar_x}+0")
    
    # Register dwell targets
    try:
        if hasattr(dwell_engine, 'clear_targets'):
            dwell_engine.clear_targets()
    except Exception as e:
        print(f"Warning: clear_targets failed: {e}")
    
    try:
        if hasattr(toolbar_ui, 'register_targets'):
            toolbar_ui.register_targets()
    except Exception as e:
        print(f"Warning: register_targets failed: {e}")
    
    # Count registered targets for debugging
    try:
        if hasattr(dwell_engine, 'get_targets'):
            targets = dwell_engine.get_targets()
            print(f"[DWELL] Startup: {len(targets)} targets registered")
    except Exception:
        pass

    # Initialize tracking variables
    frame_count = 0
    face_lost_counter = 0
    tracking_lost_overlay = None
    last_cursor = pyautogui.position()
    preview_enabled = True
    preview_window = "MotionQ Preview"

    # Setup preview window
    try:
        cv2.namedWindow(preview_window, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(preview_window, PREVIEW_WIDTH, PREVIEW_HEIGHT)
        cv2.moveWindow(preview_window, screen_w - PREVIEW_WIDTH - 20, 20)
        cv2.setWindowProperty(preview_window, cv2.WND_PROP_TOPMOST, 1)
    except Exception as e:
        print(f"Preview window error: {e}")
        preview_enabled = False

    # Keyboard listener for ESC
    def on_press(key):
        if key == kb.Key.esc:
            shutdown()

    listener = kb.Listener(on_press=on_press)
    listener.start()

    try:
        while True:
            if _shutdown_requested:
                break
                
            frame_start = time.time()

            ret, frame = cap.read()
            if not ret:
                print("ERROR: Failed to read frame from webcam")
                break

            frame_count += 1

            # Process eye tracking
            try:
                if face_lost_counter >= FACE_LOST_THRESHOLD:
                    cursor_x, cursor_y = last_cursor
                    face_detected = False
                else:
                    result = process_eye_frame(frame)
                    if len(result) == 3:
                        cursor_x, cursor_y, face_detected = result
                    else:
                        # Fallback if function returns different format
                        cursor_x, cursor_y = result[:2]
                        face_detected = result[2] if len(result) > 2 else True
                    
                    last_cursor = (cursor_x, cursor_y)
                    
                    if not face_detected:
                        face_lost_counter += 1
                    else:
                        face_lost_counter = 0
            except Exception as e:
                print(f"Eye tracking error: {e}")
                cursor_x, cursor_y = last_cursor
                face_detected = False

            # Show tracking lost overlay
            if face_lost_counter >= FACE_LOST_THRESHOLD:
                if tracking_lost_overlay is None:
                    tracking_lost_overlay = tk.Toplevel()
                    tracking_lost_overlay.overrideredirect(True)
                    tracking_lost_overlay.attributes("-topmost", True)
                    tracking_lost_overlay.geometry("200x40+10+10")
                    tracking_lost_overlay.configure(bg="red")
                    lbl = tk.Label(
                        tracking_lost_overlay,
                        text="Tracking lost - look at camera",
                        fg="white",
                        bg="red",
                        font=("Segoe UI", 10, "bold"),
                    )
                    lbl.pack(fill=tk.BOTH, expand=True)
            else:
                if tracking_lost_overlay is not None:
                    try:
                        tracking_lost_overlay.destroy()
                    except tk.TclError:
                        pass
                    tracking_lost_overlay = None

            # Process head movement
            try:
                process_head_frame(frame)
            except Exception as e:
                # Non-critical error, just log
                if frame_count % 100 == 0:
                    print(f"Head tracking error: {e}")

            # Update dwell engine
            try:
                if hasattr(dwell_engine, 'update'):
                    dwell_engine.update(cursor_x, cursor_y)
            except Exception as e:
                if frame_count % 100 == 0:
                    print(f"Dwell update error: {e}")

            # Update UI components
            try:
                toolbar_ui.update()
            except Exception as e:
                if frame_count % 100 == 0:
                    print(f"Toolbar update error: {e}")
                    
            try:
                keyboard.update()
            except Exception as e:
                if frame_count % 100 == 0:
                    print(f"Keyboard update error: {e}")
                    
            try:
                if hasattr(dwell_engine, 'tick_overlay'):
                    dwell_engine.tick_overlay()
            except Exception as e:
                pass  # Silent fail for overlay

            # Update preview window
            if preview_enabled:
                try:
                    small = cv2.resize(frame, (PREVIEW_WIDTH, PREVIEW_HEIGHT))
                    
                    # Draw cursor position
                    px = int(max(0, min(screen_w, cursor_x)) / screen_w * PREVIEW_WIDTH)
                    py = int(max(0, min(screen_h, cursor_y)) / screen_h * PREVIEW_HEIGHT)
                    cv2.drawMarker(
                        small, (px, py), (0, 255, 0), 
                        markerType=cv2.MARKER_CROSS, 
                        markerSize=12, 
                        thickness=2
                    )
                    
                    # Draw border based on tracking status
                    border_color = (0, 255, 0) if face_lost_counter < FACE_LOST_THRESHOLD else (0, 0, 255)
                    cv2.rectangle(small, (0, 0), (PREVIEW_WIDTH - 1, PREVIEW_HEIGHT - 1), border_color, 2)
                    
                    # Add tracking lost text
                    if face_lost_counter >= FACE_LOST_THRESHOLD:
                        cv2.putText(
                            small, "Tracking Lost", (10, 30), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, border_color, 2
                        )
                    
                    cv2.imshow(preview_window, small)
                    cv2.setWindowProperty(preview_window, cv2.WND_PROP_TOPMOST, 1)
                except Exception as e:
                    if frame_count % 100 == 0:
                        print(f"Preview error: {e}")

            # Handle keyboard input
            key = cv2.waitKey(1) & 0xFF
            if key == 27:  # ESC
                shutdown()
                break
            if key in (ord("t"), ord("T")):
                preview_enabled = not preview_enabled
                if not preview_enabled:
                    try:
                        cv2.destroyWindow(preview_window)
                    except Exception:
                        pass
                else:
                    try:
                        cv2.namedWindow(preview_window, cv2.WINDOW_NORMAL)
                        cv2.resizeWindow(preview_window, PREVIEW_WIDTH, PREVIEW_HEIGHT)
                        cv2.moveWindow(preview_window, screen_w - PREVIEW_WIDTH - 20, 20)
                        cv2.setWindowProperty(preview_window, cv2.WND_PROP_TOPMOST, 1)
                    except Exception:
                        preview_enabled = False

            # Frame timing
            frame_time = time.time() - frame_start
            if frame_time > 0.2:
                print(f"[WARN] Slow frame: {frame_time * 1000:.1f} ms")
                
            if frame_time < TARGET_FRAME_TIME:
                time.sleep(TARGET_FRAME_TIME - frame_time)

    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        # Clean shutdown
        print("Cleaning up resources...")
        
        try:
            listener.stop()
        except Exception:
            pass
            
        try:
            cap.release()
        except Exception:
            pass
            
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
            
        if tracking_lost_overlay is not None:
            try:
                tracking_lost_overlay.destroy()
            except tk.TclError:
                pass
                
        try:
            toolbar_ui.destroy()
        except Exception:
            pass
            
        try:
            keyboard.destroy()
        except Exception:
            pass
            
        try:
            if hasattr(dwell_engine, 'clear_targets'):
                dwell_engine.clear_targets()
        except Exception:
            pass
            
        print("Shutdown complete")
        sys.exit(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MotionQ Eye Tracking Engine")
    parser.add_argument("--profile", default="default", help="Profile name to use")
    parser.add_argument("--calibrate", action="store_true", help="Run full calibration then exit (for first-run from Rust)")
    
    args = parser.parse_args()
    
    if args.calibrate:
        print(f"Running calibration for profile: {args.profile}")
        try:
            profile_manager.load_profile(args.profile)
            calibration_manager.run_full_calibration()
            print("Calibration complete!")
        except Exception as e:
            print(f"Calibration failed: {e}")
            sys.exit(1)
    else:
        print(f"Starting MotionQ with profile: {args.profile}")
        main(args.profile)