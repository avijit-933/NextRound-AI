"""
services/speech_service.py — converts recorded interview-answer audio into text
using OpenAI's Whisper. The model is loaded once and reused across requests
since loading it is the expensive part.

Note: Whisper needs ffmpeg available on PATH in the deployment environment.
"""
import logging
import os
import tempfile

import whisper

from config import settings

logger = logging.getLogger(__name__)

_model = None


def get_model():
    """Lazily load the Whisper model (base/small/medium/large)."""
    global _model
    if _model is None:
        logger.info("Loading Whisper model: %s", settings.WHISPER_MODEL_SIZE)
        _model = whisper.load_model(settings.WHISPER_MODEL_SIZE)
    return _model


def transcribe_audio_file(filepath: str, language: str = "en") -> str:
    """Transcribe a saved audio file (wav/mp3/webm) to text."""
    model = get_model()
    result = model.transcribe(filepath, language=language, fp16=False)
    return result.get("text", "").strip()


def transcribe_audio_bytes(audio_bytes: bytes, suffix: str = ".webm", language: str = "en") -> str:
    """Convenience wrapper for transcribing an in-memory audio blob (e.g. straight
    from a FastAPI UploadFile) without the caller managing a temp file."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        return transcribe_audio_file(tmp_path, language=language)
    finally:
        os.unlink(tmp_path)
