"""Pipeline backend selection and orchestration."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from . import diarization, stub, transcription
from .config import PipelineConfig
from .merge import merge, normalize_speaker_ids

ProgressCb = Callable[[int, str], None]
logger = logging.getLogger("interview.pipeline")


def real_backend_available() -> bool:
    has_transcriber = (
        transcription.whisperx_available() or transcription.whisper_available()
    )
    return has_transcriber and diarization.pyannote_available()


def using_stub(config: PipelineConfig) -> bool:
    if config.backend == "stub":
        return True
    if config.backend == "auto":
        return not real_backend_available()
    return False


def _noop(_progress: int, _stage: str) -> None:
    pass


def run_pipeline(
    audio_path: str,
    config: PipelineConfig,
    on_progress: ProgressCb | None = None,
) -> dict:
    """Run diarization, transcription, and merge into normalized turns."""
    callback = on_progress or _noop
    pipeline_started = time.perf_counter()
    timings: dict[str, float] = {}

    if using_stub(config):
        stage_started = time.perf_counter()
        callback(20, "stub: generating sample transcript")
        diarized, transcription_result = stub.stub_pipeline(audio_path)
        timings["stub"] = time.perf_counter() - stage_started
        backend = "stub"
    else:
        callback(10, "diarization")
        stage_started = time.perf_counter()
        diarized = diarization.diarize_pyannote(audio_path, config)
        timings["diarization"] = time.perf_counter() - stage_started

        callback(50, "transcription")
        stage_started = time.perf_counter()

        def on_chunk_progress(completed: int, total: int) -> None:
            progress = 50 + round(28 * completed / total)
            callback(progress, f"transcription: chunk {completed}/{total}")

        if transcription.whisperx_available():
            transcription_result = transcription.transcribe_whisperx(
                audio_path, config, on_chunk_progress=on_chunk_progress
            )
            backend = "whisperx+pyannote"
        else:
            transcription_result = transcription.transcribe_whisper(
                audio_path, config, on_chunk_progress=on_chunk_progress
            )
            backend = "whisper+pyannote"
        timings["transcription"] = time.perf_counter() - stage_started

    callback(80, "merging speakers and text")
    stage_started = time.perf_counter()
    turns = merge(diarized, transcription_result["units"])
    turns, speakers = normalize_speaker_ids(turns)
    timings["merge"] = time.perf_counter() - stage_started

    callback(95, "finalizing")
    timings["total"] = time.perf_counter() - pipeline_started
    logger.info(
        "Pipeline completed backend=%s timings=%s",
        backend,
        {name: round(seconds, 2) for name, seconds in timings.items()},
    )
    return {
        "language": transcription_result.get("language"),
        "turns": turns,
        "speakers": speakers,
        "backend": backend,
        "timings": timings,
    }
