"""Dependency-free runtime configuration for the shared ML pipeline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    """Values supplied by a host application when it runs the pipeline."""

    backend: str = "auto"
    whisper_model: str = "base"
    hf_token: str | None = None
    default_num_speakers: int | None = None
    transcription_chunk_seconds: int = 300
    transcription_overlap_seconds: int = 8
    transcription_batch_size: int = 1

    def __post_init__(self) -> None:
        if self.backend not in {"auto", "stub", "ml"}:
            raise ValueError("backend must be one of: auto, stub, ml")
        if self.transcription_chunk_seconds <= 0:
            raise ValueError("transcription_chunk_seconds must be positive")
        if self.transcription_overlap_seconds < 0:
            raise ValueError("transcription_overlap_seconds cannot be negative")
        if (
            self.transcription_overlap_seconds * 2
            >= self.transcription_chunk_seconds
        ):
            raise ValueError("transcription overlap must be less than half a chunk")
        if self.transcription_batch_size <= 0:
            raise ValueError("transcription_batch_size must be positive")
