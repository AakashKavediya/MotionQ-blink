"""
Eye cursor control: gaze from frame -> cursor position with smoothing,
proximity slowdown and magnet pull near dwell targets. Does not open webcam.
"""
import cv2
import mediapipe as mp
import pyautogui
import numpy as np

import dwell_engine

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.001

PROXIMITY_RADIUS = 80
MAGNET_RADIUS = 40
MAGNET_FORCE = 0.2
SMOOTHING_FACTOR = 0.7  # prev * 0.7 + new * 0.3

# Module-level state (no webcam opened here)
_face_mesh = None
_prev_cursor = None
_screen_w = None
_screen_h = None

# Eye landmarks (MediaPipe)
_LEFT_IRIS = [474, 475, 476, 477]
_RIGHT_IRIS = [469, 470, 471, 472]
_SENSITIVITY = 3.0


def _get_face_mesh():
    global _face_mesh
    if _face_mesh is None:
        _face_mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
    return _face_mesh


def _iris_to_screen(iris_x, iris_y, frame_w, frame_h):
    """Map normalized iris position (0-1) to screen coordinates."""
    global _screen_w, _screen_h
    if _screen_w is None or _screen_h is None:
        _screen_w, _screen_h = pyautogui.size()
    center_x, center_y = 0.5, 0.5
    offset_x = (iris_x - center_x) * _SENSITIVITY
    offset_y = (iris_y - center_y) * _SENSITIVITY
    if abs(offset_x) > 0.1:
        offset_x = np.sign(offset_x) * (abs(offset_x) ** 1.2)
    if abs(offset_y) > 0.1:
        offset_y = np.sign(offset_y) * (abs(offset_y) ** 1.2)
    screen_x = _screen_w / 2 + offset_x * _screen_w
    screen_y = _screen_h / 2 + offset_y * _screen_h
    return screen_x, screen_y


def _dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def process_eye_frame(frame):
    """
    Detect gaze from frame, compute cursor position with weighted smoothing,
    proximity slowdown and magnet near dwell targets, clamp to screen, move cursor.
    Returns (cursor_x, cursor_y). If no face, returns previous position or (screen_w/2, screen_h/2).
    """
    global _prev_cursor, _screen_w, _screen_h
    if _screen_w is None or _screen_h is None:
        _screen_w, _screen_h = pyautogui.size()

    frame = cv2.flip(frame, 1)
    frame_h, frame_w, _ = frame.shape
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = _get_face_mesh().process(rgb)

    if not results.multi_face_landmarks:
        if _prev_cursor is not None:
            return _prev_cursor[0], _prev_cursor[1], False
        return (_screen_w / 2, _screen_h / 2, False)

    landmarks = results.multi_face_landmarks[0].landmark
    left_ix = np.mean([landmarks[i].x for i in _LEFT_IRIS])
    left_iy = np.mean([landmarks[i].y for i in _LEFT_IRIS])
    right_ix = np.mean([landmarks[i].x for i in _RIGHT_IRIS])
    right_iy = np.mean([landmarks[i].y for i in _RIGHT_IRIS])
    iris_x = (left_ix + right_ix) / 2
    iris_y = (left_iy + right_iy) / 2

    new_x, new_y = _iris_to_screen(iris_x, iris_y, frame_w, frame_h)

    # Proximity and magnet from dwell targets
    targets = dwell_engine.get_targets()
    for t in targets:
        cx = t["x"] + t["width"] / 2
        cy = t["y"] + t["height"] / 2
        d = _dist((new_x, new_y), (cx, cy))
        if d <= MAGNET_RADIUS:
            # Magnetic pull toward center
            new_x = new_x + (cx - new_x) * MAGNET_FORCE
            new_y = new_y + (cy - new_y) * MAGNET_FORCE
        elif d <= PROXIMITY_RADIUS:
            # Slow movement
            if _prev_cursor is not None:
                dx = new_x - _prev_cursor[0]
                dy = new_y - _prev_cursor[1]
                new_x = _prev_cursor[0] + dx * 0.4
                new_y = _prev_cursor[1] + dy * 0.4
            else:
                new_x = new_x * 0.4 + (_screen_w / 2) * 0.6
                new_y = new_y * 0.4 + (_screen_h / 2) * 0.6

    # Weighted smoothing: cursor = (prev * 0.7) + (new * 0.3)
    if _prev_cursor is not None:
        cursor_x = _prev_cursor[0] * SMOOTHING_FACTOR + new_x * (1 - SMOOTHING_FACTOR)
        cursor_y = _prev_cursor[1] * SMOOTHING_FACTOR + new_y * (1 - SMOOTHING_FACTOR)
    else:
        cursor_x, cursor_y = new_x, new_y

    cursor_x = max(0, min(_screen_w, cursor_x))
    cursor_y = max(0, min(_screen_h, cursor_y))

    pyautogui.moveTo(cursor_x, cursor_y, duration=0.005)
    _prev_cursor = (cursor_x, cursor_y)
    return (cursor_x, cursor_y, True)
