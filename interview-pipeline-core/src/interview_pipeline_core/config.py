"""Configuration values required by the application-independent pipeline."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    """Runtime options supplied by whichever app is using the core package."""

    pipeline_backend: str = "auto"
    whisper_model: str = "base"
    hf_token: str | None = None
    default_num_speakers: int | None = None

    def __post_init__(self) -> None:
        if self.pipeline_backend not in {"auto", "stub"}:
            raise ValueError("pipeline_backend must be 'auto' or 'stub'.")
        if self.default_num_speakers is not None and self.default_num_speakers < 1:
            raise ValueError("default_num_speakers must be at least 1 when set.")
