"""
services/emotion_service.py — per-frame facial emotion detection using DeepFace.

Shares the same base64-JPEG-frame input contract as vision_service.py so the
frontend can send one frame to both analyzers (see routers/interview.py).
"""
import base64
import logging
from typing import Dict

import numpy as np
import cv2
from deepface import DeepFace

logger = logging.getLogger(__name__)

EMOTIONS = ["happy", "neutral", "sad", "angry", "fear", "surprise", "disgust"]


def _decode_base64_image(base64_str: str) -> np.ndarray:
    if "," in base64_str:
        base64_str = base64_str.split(",", 1)[1]
    img_bytes = base64.b64decode(base64_str)
    arr = np.frombuffer(img_bytes, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def analyze_emotion(base64_image: str) -> Dict[str, float]:
    """
    Returns normalized emotion percentages, e.g.:
        {"happy": 22.4, "neutral": 55.1, "sad": 4.0, "angry": 2.1, "fear": 3.9, "surprise": 12.5}
    Falls back to a neutral-weighted distribution if no face is detected or
    DeepFace raises (e.g. no face found in frame).
    """
    fallback = {"happy": 10.0, "neutral": 70.0, "sad": 5.0, "angry": 5.0, "fear": 5.0, "surprise": 5.0}
    try:
        frame = _decode_base64_image(base64_image)
        analysis = DeepFace.analyze(
            frame, actions=["emotion"], enforce_detection=True, silent=True
        )
        # DeepFace returns a list when multiple faces are detected; take the first.
        result = analysis[0] if isinstance(analysis, list) else analysis
        raw_scores = result.get("emotion", {})

        # Collapse "disgust" into "angry" to match the 6-emotion UI/schema.
        scores = {
            "happy": raw_scores.get("happy", 0.0),
            "neutral": raw_scores.get("neutral", 0.0),
            "sad": raw_scores.get("sad", 0.0),
            "angry": raw_scores.get("angry", 0.0) + raw_scores.get("disgust", 0.0),
            "fear": raw_scores.get("fear", 0.0),
            "surprise": raw_scores.get("surprise", 0.0),
        }
        total = sum(scores.values()) or 1.0
        return {k: round((v / total) * 100, 1) for k, v in scores.items()}
    except Exception as exc:  # noqa: BLE001 — no face / model load issue, don't crash the interview
        logger.warning("DeepFace analysis failed, using fallback distribution: %s", exc)
        return fallback


def dominant_emotion(scores: Dict[str, float]) -> str:
    return max(scores, key=scores.get) if scores else "neutral"
