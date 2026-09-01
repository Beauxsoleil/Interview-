"""Diarization backend using pyannote.audio, imported lazily."""
from __future__ import annotations

import importlib.util

from .merge import DiarSegment


def pyannote_available() -> bool:
    try:
        return importlib.util.find_spec("pyannote.audio") is not None
    except (ImportError, ModuleNotFoundError):
        return False


def diarize_pyannote(
    audio_path: str,
    *,
    hf_token: str | None,
    default_num_speakers: int | None = None,
) -> list[DiarSegment]:
    from pyannote.audio import Pipeline  # type: ignore

    if not hf_token:
        raise RuntimeError(
            "Diarization requires a HuggingFace token (HF_TOKEN) to download "
            "the pyannote/speaker-diarization-3.1 model."
        )

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1", use_auth_token=hf_token
    )
    try:
        import torch  # type: ignore

        if torch.cuda.is_available():
            pipeline.to(torch.device("cuda"))
    except Exception:
        pass

    kwargs = {}
    if default_num_speakers:
        kwargs["num_speakers"] = default_num_speakers

    diarization = pipeline(audio_path, **kwargs)
    segments: list[DiarSegment] = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        segments.append(
            DiarSegment(speaker=speaker, start=float(turn.start), end=float(turn.end))
        )
    segments.sort(key=lambda segment: segment.start)
    return segments
