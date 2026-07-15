"""Pipeline orchestration: choose a backend, run stages, return merged turns."""
from __future__ import annotations

from collections.abc import Callable

from ..config import settings
from . import diarization, stub, transcription
from .merge import DiarSegment, merge, normalize_speaker_ids

ProgressCb = Callable[[int, str], None]


def real_backend_available() -> bool:
    has_transcriber = (
        transcription.whisperx_available() or transcription.whisper_available()
    )
    return has_transcriber and diarization.pyannote_available()


def using_stub() -> bool:
    if settings.pipeline_backend == "stub":
        return True
    if settings.pipeline_backend == "auto":
        return not real_backend_available()
    return False


def _noop(_progress: int, _stage: str) -> None:
    pass


def run_pipeline(audio_path: str, on_progress: ProgressCb | None = None) -> dict:
    """Run diarization + transcription + merge.

    Returns {language, turns, speakers, backend}.
    """
    cb = on_progress or _noop

    if using_stub():
        cb(20, "stub: generating sample transcript")
        diar, tx = stub.stub_pipeline(audio_path)
        backend = "stub"
    else:
        cb(10, "diarization")
        diar: list[DiarSegment] = diarization.diarize_pyannote(audio_path)

        cb(50, "transcription")
        if transcription.whisperx_available():
            tx = transcription.transcribe_whisperx(audio_path)
            backend = "whisperx+pyannote"
        else:
            tx = transcription.transcribe_whisper(audio_path)
            backend = "whisper+pyannote"

    cb(80, "merging speakers and text")
    turns = merge(diar, tx["units"])
    turns, speakers = normalize_speaker_ids(turns)

    cb(95, "finalizing")
    return {
        "language": tx.get("language"),
        "turns": turns,
        "speakers": speakers,
        "backend": backend,
    }
