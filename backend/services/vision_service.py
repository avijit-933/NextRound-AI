"""
services/vision_service.py — per-frame webcam analysis using OpenCV + MediaPipe
Face Mesh: face detection/visibility, multiple-face detection, approximate eye
contact percentage, and head pose bucket (Centered / Left / Right / Up / Down).

The frontend sends periodic JPEG frames (base64) from the browser's webcam via
the /api/interview/{id}/vision-frame endpoint; this module analyzes one frame
at a time and is stateless between calls (aggregation happens in the router).
"""
import base64
import logging
from typing import Dict

import cv2
import mediapipe as mp
import numpy as np

logger = logging.getLogger(__name__)

mp_face_mesh = mp.solutions.face_mesh

# Key landmark indices (MediaPipe Face Mesh topology) used for a lightweight
# head-pose / gaze approximation without a full 3D solvePnP model.
NOSE_TIP = 1
LEFT_EYE_OUTER = 33
RIGHT_EYE_OUTER = 263
CHIN = 152
FOREHEAD = 10

_face_mesh = None


def _get_face_mesh():
    global _face_mesh
    if _face_mesh is None:
        _face_mesh = mp_face_mesh.FaceMesh(
            static_image_mode=True,
            max_num_faces=2,
            refine_landmarks=True,
            min_detection_confidence=0.5,
        )
    return _face_mesh


def _decode_base64_image(base64_str: str) -> np.ndarray:
    if "," in base64_str:  # strip a possible "data:image/jpeg;base64," prefix
        base64_str = base64_str.split(",", 1)[1]
    img_bytes = base64.b64decode(base64_str)
    arr = np.frombuffer(img_bytes, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def analyze_frame(base64_image: str) -> Dict:
    """
    Returns:
        {
          "face_visible": bool,
          "multiple_faces_detected": bool,
          "eye_contact_pct": float,   # 0-100 approximation
          "head_pose": "Centered" | "Left" | "Right" | "Up" | "Down",
        }
    """
    try:
        frame = _decode_base64_image(base64_image)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to decode webcam frame: %s", exc)
        return {"face_visible": False, "multiple_faces_detected": False,
                "eye_contact_pct": 0.0, "head_pose": "Unknown"}

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = _get_face_mesh().process(rgb)

    if not results.multi_face_landmarks:
        return {"face_visible": False, "multiple_faces_detected": False,
                "eye_contact_pct": 0.0, "head_pose": "Unknown"}

    multiple_faces = len(results.multi_face_landmarks) > 1
    landmarks = results.multi_face_landmarks[0].landmark
    h, w = frame.shape[:2]

    def point(idx):
        lm = landmarks[idx]
        return np.array([lm.x * w, lm.y * h])

    nose = point(NOSE_TIP)
    left_eye = point(LEFT_EYE_OUTER)
    right_eye = point(RIGHT_EYE_OUTER)
    chin = point(CHIN)
    forehead = point(FOREHEAD)

    # Horizontal pose: how centered the nose is between the two eye-outer points
    eye_midpoint_x = (left_eye[0] + right_eye[0]) / 2
    eye_span = abs(right_eye[0] - left_eye[0]) or 1
    horizontal_offset = (nose[0] - eye_midpoint_x) / eye_span

    # Vertical pose: nose position relative to forehead-chin span
    vertical_span = abs(chin[1] - forehead[1]) or 1
    vertical_offset = (nose[1] - (forehead[1] + vertical_span * 0.5)) / vertical_span

    if horizontal_offset > 0.15:
        head_pose = "Right"
    elif horizontal_offset < -0.15:
        head_pose = "Left"
    elif vertical_offset > 0.2:
        head_pose = "Down"
    elif vertical_offset < -0.2:
        head_pose = "Up"
    else:
        head_pose = "Centered"

    # Eye contact approximation: highest when head pose is centered, decays
    # with how far off-center the nose is (proxy for a full gaze-vector model).
    offset_magnitude = min(1.0, (abs(horizontal_offset) + abs(vertical_offset)))
    eye_contact_pct = max(0.0, 100.0 * (1 - offset_magnitude))

    return {
        "face_visible": True,
        "multiple_faces_detected": multiple_faces,
        "eye_contact_pct": round(eye_contact_pct, 1),
        "head_pose": head_pose,
    }
