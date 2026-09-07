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

    def __post_init__(self) -> None:
        if self.backend not in {"auto", "stub", "ml"}:
            raise ValueError("backend must be one of: auto, stub, ml")

