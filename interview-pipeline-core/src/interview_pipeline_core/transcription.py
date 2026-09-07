"""Lazy WhisperX and OpenAI Whisper transcription adapters."""

from __future__ import annotations

import importlib.util
import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

from .config import PipelineConfig
from .merge import TextUnit

logger = logging.getLogger("interview.pipeline.transcription")
ChunkProgressCb = Callable[[int, int], None]


def _has(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except ModuleNotFoundError:
        return False


def whisperx_available() -> bool:
    return _has("whisperx")


def whisper_available() -> bool:
    return _has("whisper")


@dataclass(frozen=True, slots=True)
class AudioWindow:
    """A bounded model input and the non-overlapping timeline it owns."""

    audio_start: float
    audio_end: float
    keep_start: float
    keep_end: float


def audio_windows(
    duration: float, chunk_seconds: float, overlap_seconds: float
) -> list[AudioWindow]:
    """Return context-overlapped windows with deterministic output ownership."""
    if duration <= 0:
        return []

    windows: list[AudioWindow] = []
    keep_start = 0.0
    while keep_start < duration:
        keep_end = min(duration, keep_start + chunk_seconds)
        windows.append(
            AudioWindow(
                audio_start=max(0.0, keep_start - overlap_seconds),
                audio_end=min(duration, keep_end + overlap_seconds),
                keep_start=keep_start,
                keep_end=keep_end,
            )
        )
        keep_start = keep_end
    return windows


def _owned_units(units: list[TextUnit], window: AudioWindow) -> list[TextUnit]:
    """Offset local timestamps and retain each word/segment exactly once."""
    owned: list[TextUnit] = []
    final_window = window.keep_end == window.audio_end
    for unit in units:
        start = float(unit.start) + window.audio_start
        end = float(unit.end) + window.audio_start
        midpoint = (start + end) / 2
        if midpoint < window.keep_start:
            continue
        if midpoint > window.keep_end or (midpoint == window.keep_end and not final_window):
            continue
        owned.append(TextUnit(start=start, end=end, text=unit.text))
    return owned


def _chunked_transcribe(
    audio,
    sample_rate: int,
    config: PipelineConfig,
    transcribe,
    on_chunk_progress: ChunkProgressCb | None = None,
):
    duration = len(audio) / sample_rate
    units: list[TextUnit] = []
    language: str | None = None
    windows = audio_windows(
        duration,
        config.transcription_chunk_seconds,
        config.transcription_overlap_seconds,
    )
    for index, window in enumerate(windows, start=1):
        start_sample = round(window.audio_start * sample_rate)
        end_sample = round(window.audio_end * sample_rate)
        started = time.perf_counter()
        result = transcribe(audio[start_sample:end_sample])
        language = language or result.get("language")
        units.extend(_owned_units(result.get("units", []), window))
        logger.info(
            "Transcription chunk %s/%s completed (audio=%.1fs, elapsed=%.2fs)",
            index,
            len(windows),
            window.audio_end - window.audio_start,
            time.perf_counter() - started,
        )
        if on_chunk_progress:
            on_chunk_progress(index, len(windows))
    return {"language": language or "en", "units": units}


@lru_cache(maxsize=3)
def _load_whisperx_model(model_name: str, device: str, compute_type: str):
    import whisperx  # type: ignore

    logger.info(
        "Loading WhisperX model %s (device=%s, compute_type=%s)",
        model_name,
        device,
        compute_type,
    )
    return whisperx.load_model(model_name, device, compute_type=compute_type)


@lru_cache(maxsize=2)
def _load_whisperx_aligner(language: str, device: str):
    import whisperx  # type: ignore

    logger.info(
        "Loading WhisperX alignment model (language=%s, device=%s)",
        language,
        device,
    )
    return whisperx.load_align_model(language_code=language, device=device)


def transcribe_whisperx(
    audio_path: str,
    config: PipelineConfig,
    on_chunk_progress: ChunkProgressCb | None = None,
) -> dict:
    import whisperx  # type: ignore

    device = "cuda" if _cuda_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    model = _load_whisperx_model(config.whisper_model, device, compute_type)
    audio = whisperx.load_audio(audio_path)

    def transcribe_chunk(chunk) -> dict:
        # batch_size=1 is deliberate: WhisperX VAD produces variable-length
        # segments, and larger batches can fail while stacking those tensors.
        result = model.transcribe(chunk, batch_size=config.transcription_batch_size)
        language = result.get("language", "en")
        align_model, metadata = _load_whisperx_aligner(language, device)
        aligned = whisperx.align(
            result["segments"], align_model, metadata, chunk, device
        )

        chunk_units: list[TextUnit] = []
        for segment in aligned.get("segments", []):
            words = segment.get("words") or []
            if words:
                for word in words:
                    if word.get("start") is None or word.get("end") is None:
                        continue
                    chunk_units.append(
                        TextUnit(
                            start=word["start"],
                            end=word["end"],
                            text=word.get("word", ""),
                        )
                    )
            else:
                chunk_units.append(
                    TextUnit(
                        start=segment["start"],
                        end=segment["end"],
                        text=segment["text"],
                    )
                )
        return {"language": language, "units": chunk_units}

    return _chunked_transcribe(
        audio,
        16_000,
        config,
        transcribe_chunk,
        on_chunk_progress=on_chunk_progress,
    )


@lru_cache(maxsize=3)
def _load_whisper_model(model_name: str):
    import whisper  # type: ignore

    logger.info("Loading OpenAI Whisper model %s", model_name)
    return whisper.load_model(model_name)


def transcribe_whisper(
    audio_path: str,
    config: PipelineConfig,
    on_chunk_progress: ChunkProgressCb | None = None,
) -> dict:
    import whisper  # type: ignore

    model = _load_whisper_model(config.whisper_model)
    audio = whisper.load_audio(audio_path)

    def transcribe_chunk(chunk) -> dict:
        result = model.transcribe(chunk)
        units = [
            TextUnit(
                start=segment["start"],
                end=segment["end"],
                text=segment["text"],
            )
            for segment in result.get("segments", [])
        ]
        return {"language": result.get("language", "en"), "units": units}

    return _chunked_transcribe(
        audio,
        16_000,
        config,
        transcribe_chunk,
        on_chunk_progress=on_chunk_progress,
    )


def _cuda_available() -> bool:
    try:
        import torch  # type: ignore

        return torch.cuda.is_available()
    except Exception:
        return False
