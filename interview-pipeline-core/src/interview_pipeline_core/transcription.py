"""WhisperX and Whisper transcription backends, imported lazily."""
from __future__ import annotations

import importlib.util

from .merge import TextUnit


def _has(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ModuleNotFoundError):
        return False


def whisperx_available() -> bool:
    return _has("whisperx")


def whisper_available() -> bool:
    return _has("whisper")


def transcribe_whisperx(audio_path: str, *, model_name: str = "base") -> dict:
    import whisperx  # type: ignore

    device = "cuda" if _cuda_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    model = whisperx.load_model(model_name, device, compute_type=compute_type)
    audio = whisperx.load_audio(audio_path)
    result = model.transcribe(audio, batch_size=16)
    language = result.get("language", "en")

    align_model, metadata = whisperx.load_align_model(
        language_code=language, device=device
    )
    aligned = whisperx.align(
        result["segments"], align_model, metadata, audio, device
    )

    units: list[TextUnit] = []
    for segment in aligned.get("segments", []):
        words = segment.get("words") or []
        if words:
            for word in words:
                if word.get("start") is None or word.get("end") is None:
                    continue
                units.append(
                    TextUnit(
                        start=word["start"],
                        end=word["end"],
                        text=word.get("word", ""),
                    )
                )
        else:
            units.append(
                TextUnit(
                    start=segment["start"],
                    end=segment["end"],
                    text=segment["text"],
                )
            )
    return {"language": language, "units": units}


def transcribe_whisper(audio_path: str, *, model_name: str = "base") -> dict:
    import whisper  # type: ignore

    model = whisper.load_model(model_name)
    result = model.transcribe(audio_path)
    units = [
        TextUnit(start=segment["start"], end=segment["end"], text=segment["text"])
        for segment in result.get("segments", [])
    ]
    return {"language": result.get("language", "en"), "units": units}


def _cuda_available() -> bool:
    try:
        import torch  # type: ignore

        return torch.cuda.is_available()
    except Exception:
        return False
