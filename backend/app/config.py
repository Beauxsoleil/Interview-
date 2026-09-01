"""Application configuration.

All settings are local-only by default. This app stores health, legal, and
demographic information, so nothing is sent to third-party analytics and audio
lives on local disk. The only outbound call is to the Claude API for profile
extraction, and that only happens if an API key is configured.
"""
from __future__ import annotations

from pathlib import Path

from interview_pipeline_core import PipelineConfig
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    # Storage
    data_dir: Path = DATA_DIR
    database_url: str = f"sqlite:///{DATA_DIR / 'app.db'}"

    # Audio uploads
    allowed_audio_extensions: tuple[str, ...] = (".mp3", ".wav", ".m4a")
    max_upload_bytes: int = 500 * 1024 * 1024  # 500 MB

    # --- Claude (profile extraction) ---
    anthropic_api_key: str | None = None
    profile_model: str = "claude-opus-4-8"

    # --- Transcription / diarization ---
    # "auto"    -> use whisperx/whisper + pyannote if installed, else stub
    # "stub"    -> always use the deterministic stub backend (no ML deps)
    pipeline_backend: str = "auto"
    whisper_model: str = "base"  # tiny|base|small|medium|large-v3
    # HuggingFace token required by pyannote to download the diarization model.
    hf_token: str | None = None
    # Optional hint; if None, diarization decides the number of speakers.
    default_num_speakers: int | None = None

    @field_validator(
        "anthropic_api_key", "hf_token", "default_num_speakers", mode="before"
    )
    @classmethod
    def _blank_env_is_none(cls, v):
        """Treat blank values in .env (e.g. a copied .env.example) as unset."""
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def audio_dir(self) -> Path:
        return self.data_dir / "audio"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)

    def pipeline_config(self) -> PipelineConfig:
        """Translate app settings into the shared pipeline's explicit config."""
        return PipelineConfig(
            pipeline_backend=self.pipeline_backend,
            whisper_model=self.whisper_model,
            hf_token=self.hf_token,
            default_num_speakers=self.default_num_speakers,
        )


settings = Settings()
settings.ensure_dirs()
