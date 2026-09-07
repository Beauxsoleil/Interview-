"""Pipeline backend selection and orchestration."""

from __future__ import annotations

from collections.abc import Callable

from . import diarization, stub, transcription
from .config import PipelineConfig
from .merge import merge, normalize_speaker_ids

ProgressCb = Callable[[int, str], None]


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

    if using_stub(config):
        callback(20, "stub: generating sample transcript")
        diarized, transcription_result = stub.stub_pipeline(audio_path)
        backend = "stub"
    else:
        callback(10, "diarization")
        diarized = diarization.diarize_pyannote(audio_path, config)

        callback(50, "transcription")
        if transcription.whisperx_available():
            transcription_result = transcription.transcribe_whisperx(audio_path, config)
            backend = "whisperx+pyannote"
        else:
            transcription_result = transcription.transcribe_whisper(audio_path, config)
            backend = "whisper+pyannote"

    callback(80, "merging speakers and text")
    turns = merge(diarized, transcription_result["units"])
    turns, speakers = normalize_speaker_ids(turns)

    callback(95, "finalizing")
    return {
        "language": transcription_result.get("language"),
        "turns": turns,
        "speakers": speakers,
        "backend": backend,
    }

