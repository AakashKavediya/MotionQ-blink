"""
Head tilt scrolling: tilt relative to calibrated neutral_y, 3-frame threshold
to avoid tremor. Does not open webcam.
"""
import cv2
import pyautogui
import mediapipe as mp
import calibration_manager

# Configuration constants
TILT_FRAME_THRESHOLD = 3
SCROLL_AMOUNT = 30

# Nose landmark index (MediaPipe face mesh)
_NOSE_INDEX = 1

_face_mesh = None
_tilt_frame_count = 0
_last_scroll_direction = None  # "up", "down", or None


def _get_face_mesh():
    """Initialize and return MediaPipe face mesh."""
    global _face_mesh
    if _face_mesh is None:
        _face_mesh = mp.solutions.face_mesh.FaceMesh(refine_landmarks=True)
    return _face_mesh


def process_head_frame(frame):
    """
    Detect head tilt from frame relative to calibrated neutral_y.
    Require TILT_FRAME_THRESHOLD consecutive frames of sustained tilt before scrolling.
    Reset frame counter when head returns to neutral.
    """
    global _tilt_frame_count, _last_scroll_direction

    # Get calibration data
    try:
        cal = calibration_manager.get_head_calibration()
        if not cal:
            return
        neutral_y = cal.get("neutral_y")
        if neutral_y is None:
            return
    except Exception as e:
        print(f"Head calibration error: {e}")
        return

    # Flip frame for mirror effect
    frame = cv2.flip(frame, 1)
    frame_h, frame_w, _ = frame.shape
    
    # Process with MediaPipe
    try:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = _get_face_mesh().process(rgb)
    except Exception as e:
        print(f"MediaPipe processing error: {e}")
        return

    if not results or not results.multi_face_landmarks:
        _tilt_frame_count = 0
        _last_scroll_direction = None
        return

    # Get nose position
    try:
        nose = results.multi_face_landmarks[0].landmark[_NOSE_INDEX]
        nose_y = nose.y * frame_h
    except (IndexError, AttributeError) as e:
        print(f"Nose detection error: {e}")
        _tilt_frame_count = 0
        _last_scroll_direction = None
        return

    # Use tilt threshold from calibration (default 20.0 if not present)
    threshold = cal.get("tilt_threshold", 20.0)
    dy = nose_y - neutral_y

    # Determine tilt direction
    if dy > threshold:
        direction = "down"
    elif dy < -threshold:
        direction = "up"
    else:
        # Neutral position - reset counters
        _tilt_frame_count = 0
        _last_scroll_direction = None
        return

    # Count consecutive frames in same direction
    if direction == _last_scroll_direction:
        _tilt_frame_count += 1
    else:
        _tilt_frame_count = 1
        _last_scroll_direction = direction

    # Trigger scroll after threshold reached
    if _tilt_frame_count >= TILT_FRAME_THRESHOLD:
        try:
            if direction == "down":
                # Scroll down (negative value)
                pyautogui.scroll(-SCROLL_AMOUNT)
            else:
                # Scroll up (positive value)
                pyautogui.scroll(SCROLL_AMOUNT)
            
            # Reset frame count to avoid continuous scrolling every frame
            # Keep direction the same to allow continued scrolling with new frames
            _tilt_frame_count = 0
        except Exception as e:
            print(f"Scroll error: {e}")