"""Lazy pyannote.audio diarization adapter."""

from __future__ import annotations

import importlib.util
import logging
from functools import lru_cache

from .config import PipelineConfig
from .merge import DiarSegment

logger = logging.getLogger("interview.pipeline.diarization")


def pyannote_available() -> bool:
    try:
        return importlib.util.find_spec("pyannote.audio") is not None
    except ModuleNotFoundError:
        return False


@lru_cache(maxsize=2)
def _load_pipeline(hf_token: str, use_cuda: bool):
    from pyannote.audio import Pipeline  # type: ignore

    logger.info("Loading Pyannote diarization model (cuda=%s)", use_cuda)
    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1", use_auth_token=hf_token
    )
    if use_cuda:
        import torch  # type: ignore

        pipeline.to(torch.device("cuda"))
    return pipeline


def diarize_pyannote(audio_path: str, config: PipelineConfig) -> list[DiarSegment]:
    if not config.hf_token:
        raise RuntimeError(
            "Diarization requires HF_TOKEN for pyannote/speaker-diarization-3.1."
        )

    pipeline = _load_pipeline(config.hf_token, _cuda_available())

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


def _cuda_available() -> bool:
    try:
        import torch  # type: ignore

        return torch.cuda.is_available()
    except Exception:
        return False
