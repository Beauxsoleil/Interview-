"""Adapter from application settings to the reusable pipeline package."""

from interview_pipeline_core import PipelineConfig

from .config import settings


def pipeline_config() -> PipelineConfig:
    return PipelineConfig(
        backend=settings.pipeline_backend,
        whisper_model=settings.whisper_model,
        hf_token=settings.hf_token,
        default_num_speakers=settings.default_num_speakers,
        transcription_chunk_seconds=settings.transcription_chunk_seconds,
        transcription_overlap_seconds=settings.transcription_overlap_seconds,
        transcription_batch_size=settings.transcription_batch_size,
    )
