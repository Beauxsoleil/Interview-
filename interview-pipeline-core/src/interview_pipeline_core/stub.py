"""Deterministic, dependency-free sample interview pipeline."""
from __future__ import annotations

from .merge import DiarSegment, TextUnit

_STUB_TURNS: list[tuple[str, str]] = [
    (
        "SPEAKER_00",
        "Hi, thanks for coming in today. Can you start by telling me a bit about yourself?",
    ),
    (
        "SPEAKER_01",
        "Sure. I'm twenty-six years old. I finished my associate's degree in "
        "diesel mechanics a couple of years ago and I've been working as a "
        "mechanic since then.",
    ),
    (
        "SPEAKER_00",
        "Great. Have you served in the military before, or done any prior service?",
    ),
    (
        "SPEAKER_01",
        "Yeah, I did four years in the Army as a wheeled vehicle mechanic. "
        "Honorable discharge. That's actually why I'm interested in this role.",
    ),
    ("SPEAKER_00", "Understood. How's your physical health these days?"),
    (
        "SPEAKER_01",
        "Pretty good overall. I had a knee surgery about two years ago but "
        "it's fully healed now and I stay active.",
    ),
    ("SPEAKER_00", "Any legal history we should be aware of?"),
    (
        "SPEAKER_01",
        "Nothing serious. I had a speeding ticket last year, that's it. "
        "No arrests or anything like that.",
    ),
    ("SPEAKER_00", "Tell me about your family situation."),
    (
        "SPEAKER_01",
        "I'm married and we have two kids, a three-year-old and a baby on "
        "the way. My family is a big part of why I want steady work.",
    ),
    ("SPEAKER_00", "Do you have any tattoos, piercings, or brandings?"),
    (
        "SPEAKER_01",
        "I've got a couple of tattoos on my forearm and one on my shoulder. "
        "No piercings.",
    ),
    (
        "SPEAKER_00",
        "Last question — what are you hoping to get out of this opportunity?",
    ),
    (
        "SPEAKER_01",
        "Honestly, I want stability for my family and a chance to grow. I'm a "
        "hard worker and I'd like to eventually move into a lead mechanic role.",
    ),
]


def stub_pipeline(_audio_path: str) -> tuple[list[DiarSegment], dict]:
    """Return diarization and transcription data for the canned interview."""
    diar: list[DiarSegment] = []
    units: list[TextUnit] = []
    timestamp = 0.0
    for speaker, text in _STUB_TURNS:
        duration = max(2.0, len(text.split()) * 0.4)
        diar.append(
            DiarSegment(
                speaker=speaker,
                start=timestamp,
                end=timestamp + duration,
            )
        )
        units.append(
            TextUnit(start=timestamp, end=timestamp + duration, text=text)
        )
        timestamp += duration + 0.3

    return diar, {"language": "en", "units": units}
