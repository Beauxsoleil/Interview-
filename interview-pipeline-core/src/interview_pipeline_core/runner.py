"""Pipeline orchestration and backend selection."""
from __future__ import annotations

from collections.abc import Callable

from . import diarization, stub, transcription
from .config import PipelineConfig
from .merge import DiarSegment, merge, normalize_speaker_ids

ProgressCb = Callable[[int, str], None]


def real_backend_available() -> bool:
    has_transcriber = (
        transcription.whisperx_available() or transcription.whisper_available()
    )
    return has_transcriber and diarization.pyannote_available()


def using_stub(config: PipelineConfig | None = None) -> bool:
    active_config = config or PipelineConfig()
    if active_config.pipeline_backend == "stub":
        return True
    return not real_backend_available()


def _noop(_progress: int, _stage: str) -> None:
    pass


def run_pipeline(
    audio_path: str,
    on_progress: ProgressCb | None = None,
    *,
    config: PipelineConfig | None = None,
) -> dict:
    """Run diarization, transcription, and speaker/text merge."""
    active_config = config or PipelineConfig()
    callback = on_progress or _noop

    if using_stub(active_config):
        callback(20, "stub: generating sample transcript")
        diar, transcription_result = stub.stub_pipeline(audio_path)
        backend = "stub"
    else:
        callback(10, "diarization")
        diar: list[DiarSegment] = diarization.diarize_pyannote(
            audio_path,
            hf_token=active_config.hf_token,
            default_num_speakers=active_config.default_num_speakers,
        )

        callback(50, "transcription")
        if transcription.whisperx_available():
            transcription_result = transcription.transcribe_whisperx(
                audio_path, model_name=active_config.whisper_model
            )
            backend = "whisperx+pyannote"
        else:
            transcription_result = transcription.transcribe_whisper(
                audio_path, model_name=active_config.whisper_model
            )
            backend = "whisper+pyannote"

    callback(80, "merging speakers and text")
    turns = merge(diar, transcription_result["units"])
    turns, speakers = normalize_speaker_ids(turns)

    callback(95, "finalizing")
    return {
        "language": transcription_result.get("language"),
        "turns": turns,
        "speakers": speakers,
        "backend": backend,
    }
