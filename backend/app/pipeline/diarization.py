"""Diarization backend (pyannote.audio).

`diarize(audio_path)` returns a list of DiarSegment(speaker, start, end).
Imported lazily so the app runs without pyannote/torch installed.
"""
from __future__ import annotations

import importlib.util

from ..config import settings
from .merge import DiarSegment


def pyannote_available() -> bool:
    return importlib.util.find_spec("pyannote.audio") is not None


def diarize_pyannote(audio_path: str) -> list[DiarSegment]:
    from pyannote.audio import Pipeline  # type: ignore

    if not settings.hf_token:
        raise RuntimeError(
            "Diarization requires a HuggingFace token (HF_TOKEN) to download "
            "the pyannote/speaker-diarization-3.1 model."
        )

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1", use_auth_token=settings.hf_token
    )
    try:
        import torch  # type: ignore

        if torch.cuda.is_available():
            pipeline.to(torch.device("cuda"))
    except Exception:
        pass

    kwargs = {}
    if settings.default_num_speakers:
        kwargs["num_speakers"] = settings.default_num_speakers

    diarization = pipeline(audio_path, **kwargs)
    segments: list[DiarSegment] = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        segments.append(
            DiarSegment(speaker=speaker, start=float(turn.start), end=float(turn.end))
        )
    segments.sort(key=lambda s: s.start)
    return segments
