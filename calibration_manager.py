"""
Calibration: run_full_calibration (5-point gaze + head neutral), run_quick_calibration (lighting only).
Saves to profile's file (via profile_manager). No smile data.
"""
import json
import os
import time
import cv2
import mediapipe as mp
import pyautogui
import numpy as np

import profile_manager

# Use current profile path from profile_manager
def _get_path():
    return profile_manager.get_current_profile_path()


def load():
    """Load calibration data from current profile file."""
    path = _get_path()
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save(data):
    """Save full profile data (including calibration) to current profile file."""
    path = _get_path()
    if not path:
        return
    existing = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            pass
    existing.update(data)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)


def get_head_calibration():
    """Return head dict (neutral_y, tilt_threshold) for head.py."""
    d = load()
    return d.get("head")


def set_head_calibration(neutral_y, tilt_threshold=15.0):
    d = load()
    if "head" not in d:
        d["head"] = {}
    d["head"]["neutral_y"] = float(neutral_y)
    d["head"]["tilt_threshold"] = float(tilt_threshold)
    save(d)


def get_gaze_calibration():
    return load().get("gaze", {})


def set_gaze_calibration(calibration_points, screen_width=None, screen_height=None):
    sw = screen_width or pyautogui.size()[0]
    sh = screen_height or pyautogui.size()[1]
    d = load()
    d["gaze"] = {
        "calibration_points": list(calibration_points),
        "screen_width": sw,
        "screen_height": sh,
    }
    save(d)


def get_lighting():
    return load().get("lighting", {"brightness_offset": 0, "contrast_scale": 1.0})


def set_lighting(brightness_offset, contrast_scale):
    d = load()
    d["lighting"] = {"brightness_offset": float(brightness_offset), "contrast_scale": float(contrast_scale)}
    save(d)


def get_dwell_calibration():
    return load().get("dwell", {"duration_ms": 800, "entry_delay_ms": 300, "stability_radius": 25})


def run_full_calibration():
    """
    5-point gaze calibration + head tilt neutral capture. Hands-free: 3s countdown per point, no key press.
    """
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    if not cap.isOpened():
        print("ERROR: Cannot access webcam for calibration")
        return
    mp_face = mp.solutions.face_mesh
    face_mesh = mp_face.FaceMesh(refine_landmarks=True, max_num_faces=1)
    screen_w, screen_h = pyautogui.size()

    points = [
        ("Center", 0.5, 0.5),
        ("Top Left", 0.2, 0.2),
        ("Top Right", 0.8, 0.2),
        ("Bottom Left", 0.2, 0.8),
        ("Bottom Right", 0.8, 0.8),
    ]

    overlay_name = "MotionQ Calibration"
    cv2.namedWindow(overlay_name, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(overlay_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    calibration_points = []

    for idx, (label, sx, sy) in enumerate(points, start=1):
        point_center = (int(sx * screen_w), int(sy * screen_h))
        countdown_sec = 3.0
        flash_sec = 1.0
        phase = "countdown"
        phase_start = time.time()
        last_iris = None

        while True:
            now = time.time()
            ret, frame = cap.read()
            if not ret:
                break

            rgb = cv2.cvtColor(cv2.flip(frame, 1), cv2.COLOR_BGR2RGB)
            results = face_mesh.process(rgb)
            if results.multi_face_landmarks:
                lm = results.multi_face_landmarks[0].landmark
                left_ix = sum(lm[j].x for j in [474, 475, 476, 477]) / 4
                left_iy = sum(lm[j].y for j in [474, 475, 476, 477]) / 4
                right_ix = sum(lm[j].x for j in [469, 470, 471, 472]) / 4
                right_iy = sum(lm[j].y for j in [469, 470, 471, 472]) / 4
                iris_x = (left_ix + right_ix) / 2
                iris_y = (left_iy + right_iy) / 2
                last_iris = (iris_x, iris_y)

            overlay = np.zeros((screen_h, screen_w, 3), dtype=np.uint8)
            radius = 60
            thickness = 4

            if phase == "countdown":
                elapsed = now - phase_start
                progress = min(1.0, elapsed / countdown_sec)
                cv2.circle(overlay, point_center, radius, (0, 255, 255), -1)
                text = f"Look at this dot — {label}"
                cv2.putText(overlay, text, (50, screen_h // 2 + 120), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
                cv2.ellipse(overlay, point_center, (radius + 15, radius + 15), 0, -90, -90 + 360 * progress, (0, 255, 255), thickness)
                if elapsed >= countdown_sec:
                    if last_iris is not None:
                        ix, iy = last_iris
                        calibration_points.append({"iris": [ix, iy], "screen": [sx, sy]})
                    phase = "flash"
                    phase_start = now
            elif phase == "flash":
                cv2.circle(overlay, point_center, radius + 10, (0, 255, 0), -1)
                cv2.putText(overlay, "Captured", (50, screen_h // 2 + 120), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
                if now - phase_start >= flash_sec:
                    break

            cv2.imshow(overlay_name, overlay)
            if cv2.waitKey(1) & 0xFF == 27:
                cap.release()
                cv2.destroyAllWindows()
                return

    if calibration_points:
        set_gaze_calibration(calibration_points, screen_w, screen_h)
        print("Gaze calibration saved.")

    # Head neutral: automatic capture
    print("Calibrating head neutral position")
    countdown_sec = 3.0
    point_center = (screen_w // 2, screen_h // 2)
    start = time.time()
    neutral_samples = []

    while True:
        now = time.time()
        ret, frame = cap.read()
        if not ret:
            break
        frame_flipped = cv2.flip(frame, 1)
        h, w, _ = frame_flipped.shape
        rgb = cv2.cvtColor(frame_flipped, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(rgb)
        if results.multi_face_landmarks:
            nose_y = results.multi_face_landmarks[0].landmark[1].y * h
            neutral_samples.append(nose_y)

        overlay = np.zeros((screen_h, screen_w, 3), dtype=np.uint8)
        radius = 60
        thickness = 4
        elapsed = now - start
        progress = min(1.0, elapsed / countdown_sec)
        cv2.circle(overlay, point_center, radius, (0, 255, 255), -1)
        cv2.putText(overlay, "Hold head neutral — capturing", (50, screen_h // 2 + 120), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        cv2.ellipse(overlay, point_center, (radius + 15, radius + 15), 0, -90, -90 + 360 * progress, (0, 255, 255), thickness)
        cv2.imshow(overlay_name, overlay)
        if cv2.waitKey(1) & 0xFF == 27:
            break
        if elapsed >= countdown_sec:
            break

    if neutral_samples:
        neutral_y = sum(neutral_samples) / len(neutral_samples)
        set_head_calibration(neutral_y)
        print("Head calibration saved.")

    complete_overlay = np.zeros((screen_h, screen_w, 3), dtype=np.uint8)
    cv2.putText(complete_overlay, "Calibration Complete", (screen_w // 2 - 300, screen_h // 2), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3)
    cv2.imshow(overlay_name, complete_overlay)
    cv2.waitKey(2000)

    cap.release()
    cv2.destroyAllWindows()


def run_quick_calibration():
    """
    Single center-point, 5 seconds hands-free. Adjusts lighting only.
    """
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    if not cap.isOpened():
        return
    screen_w, screen_h = pyautogui.size()
    overlay_name = "MotionQ Quick Calibration"
    cv2.namedWindow(overlay_name, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(overlay_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    start = time.time()
    duration = 5.0
    samples = []
    center = (screen_w // 2, screen_h // 2)
    radius = 60

    while True:
        now = time.time()
        ret, frame = cap.read()
        if not ret:
            break
        h, w = frame.shape[:2]
        cx, cy = w // 2, h // 2
        crop = frame[cy - 50:cy + 50, cx - 50:cx + 50]
        if crop.size:
            mean_val = float(crop.mean())
            samples.append(mean_val)

        overlay = np.zeros((screen_h, screen_w, 3), dtype=np.uint8)
        elapsed = now - start
        progress = min(1.0, elapsed / duration)
        cv2.circle(overlay, center, radius, (0, 255, 255), -1)
        cv2.putText(overlay, "Look at the center dot — calibrating lighting", (50, screen_h // 2 + 120), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        cv2.ellipse(overlay, center, (radius + 15, radius + 15), 0, -90, -90 + 360 * progress, (0, 255, 255), 4)
        cv2.imshow(overlay_name, overlay)
        if cv2.waitKey(1) & 0xFF == 27:
            break
        if elapsed >= duration:
            break

    cap.release()
    cv2.destroyWindow(overlay_name)
    if samples:
        avg = sum(samples) / len(samples)
        brightness_offset = 128 - avg
        contrast_scale = 1.0
        set_lighting(brightness_offset, contrast_scale)
