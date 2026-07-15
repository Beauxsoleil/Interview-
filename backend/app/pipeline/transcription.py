"""Transcription backends.

`transcribe(audio_path)` returns:
    {
      "language": "en",
      "units": [TextUnit(start, end, text), ...],   # word-level if available
    }

Two backends:
  * whisperx  -> word-level timestamps (best for speaker/text alignment)
  * whisper   -> segment-level timestamps (fallback)
The real backends are imported lazily so the app runs without torch installed.
"""
from __future__ import annotations

import importlib.util

from ..config import settings
from .merge import TextUnit


def _has(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def whisperx_available() -> bool:
    return _has("whisperx")


def whisper_available() -> bool:
    return _has("whisper")


def transcribe_whisperx(audio_path: str) -> dict:
    import whisperx  # type: ignore

    device = "cuda" if _cuda_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    model = whisperx.load_model(
        settings.whisper_model, device, compute_type=compute_type
    )
    audio = whisperx.load_audio(audio_path)
    result = model.transcribe(audio, batch_size=16)
    language = result.get("language", "en")

    # Align for word-level timestamps.
    align_model, metadata = whisperx.load_align_model(
        language_code=language, device=device
    )
    aligned = whisperx.align(
        result["segments"], align_model, metadata, audio, device
    )

    units: list[TextUnit] = []
    for seg in aligned.get("segments", []):
        words = seg.get("words") or []
        if words:
            for w in words:
                if w.get("start") is None or w.get("end") is None:
                    continue
                units.append(
                    TextUnit(start=w["start"], end=w["end"], text=w.get("word", ""))
                )
        else:
            units.append(
                TextUnit(start=seg["start"], end=seg["end"], text=seg["text"])
            )
    return {"language": language, "units": units}


def transcribe_whisper(audio_path: str) -> dict:
    import whisper  # type: ignore

    model = whisper.load_model(settings.whisper_model)
    result = model.transcribe(audio_path)
    units = [
        TextUnit(start=s["start"], end=s["end"], text=s["text"])
        for s in result.get("segments", [])
    ]
    return {"language": result.get("language", "en"), "units": units}


def _cuda_available() -> bool:
    try:
        import torch  # type: ignore

        return torch.cuda.is_available()
    except Exception:
        return False
