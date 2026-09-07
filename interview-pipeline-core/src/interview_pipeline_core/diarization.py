"""Lazy pyannote.audio diarization adapter."""

from __future__ import annotations

import importlib.util

from .config import PipelineConfig
from .merge import DiarSegment


def pyannote_available() -> bool:
    try:
        return importlib.util.find_spec("pyannote.audio") is not None
    except ModuleNotFoundError:
        return False


def diarize_pyannote(audio_path: str, config: PipelineConfig) -> list[DiarSegment]:
    from pyannote.audio import Pipeline  # type: ignore

    if not config.hf_token:
        raise RuntimeError(
            "Diarization requires HF_TOKEN for pyannote/speaker-diarization-3.1."
        )

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1", use_auth_token=config.hf_token
    )
    try:
        import torch  # type: ignore

        if torch.cuda.is_available():
            pipeline.to(torch.device("cuda"))
    except Exception:
        pass

    kwargs = {}
    if config.default_num_speakers:
        kwargs["num_speakers"] = config.default_num_speakers

    diarization = pipeline(audio_path, **kwargs)
    segments = [
        DiarSegment(speaker=speaker, start=float(turn.start), end=float(turn.end))
        for turn, _, speaker in diarization.itertracks(yield_label=True)
    ]
    segments.sort(key=lambda segment: segment.start)
    return segments

