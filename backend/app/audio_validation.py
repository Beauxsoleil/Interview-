"""Validate uploaded media using ffprobe instead of trusting names or MIME types."""
from __future__ import annotations

import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import settings


class AudioValidationError(ValueError):
    pass


@dataclass(frozen=True)
class AudioMetadata:
    duration_seconds: float
    codec: str


def parse_ffprobe_output(raw: str) -> AudioMetadata:
    try:
        data = json.loads(raw)
        streams = [stream for stream in data.get("streams", []) if stream.get("codec_type") == "audio"]
        if not streams:
            raise AudioValidationError("The uploaded file does not contain a readable audio stream.")
        duration = float(data.get("format", {}).get("duration"))
        if not math.isfinite(duration) or duration <= 0:
            raise AudioValidationError("The audio duration is invalid.")
        codec = str(streams[0].get("codec_name") or "unknown")
        return AudioMetadata(duration_seconds=duration, codec=codec)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        if isinstance(error, AudioValidationError):
            raise
        raise AudioValidationError("The uploaded file is not readable audio.") from error


def validate_audio(path: Path) -> AudioMetadata:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries",
                "format=duration:stream=codec_type,codec_name", "-of", "json", str(path),
            ],
            capture_output=True,
            text=True,
            timeout=settings.ffprobe_timeout_seconds,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        raise AudioValidationError("Audio validation is unavailable. Ensure ffprobe is installed.") from error
    if result.returncode != 0:
        raise AudioValidationError("The uploaded file is corrupt or is not supported audio.")
    metadata = parse_ffprobe_output(result.stdout)
    if metadata.duration_seconds > settings.max_audio_duration_seconds:
        limit_minutes = settings.max_audio_duration_seconds // 60
        raise AudioValidationError(f"Audio exceeds the {limit_minutes}-minute duration limit.")
    return metadata
