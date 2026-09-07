"""Deterministic no-dependency backend for end-to-end development."""

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
        "diesel mechanics and I've been working as a mechanic since then.",
    ),
    (
        "SPEAKER_00",
        "Have you served in the military before, or done any prior service?",
    ),
    (
        "SPEAKER_01",
        "I did four years in the Army as a wheeled vehicle mechanic with an "
        "honorable discharge.",
    ),
    ("SPEAKER_00", "How is your physical health these days?"),
    (
        "SPEAKER_01",
        "Pretty good overall. I had knee surgery two years ago and it is fully healed.",
    ),
    ("SPEAKER_00", "Any legal history we should be aware of?"),
    (
        "SPEAKER_01",
        "I had a speeding ticket last year, but no arrests or anything like that.",
    ),
    ("SPEAKER_00", "Tell me about your family situation."),
    ("SPEAKER_01", "I'm married and we have two kids."),
    ("SPEAKER_00", "Do you have any tattoos, piercings, or brandings?"),
    (
        "SPEAKER_01",
        "I have tattoos on my forearm and shoulder and no piercings.",
    ),
    ("SPEAKER_00", "What are you hoping to get out of this opportunity?"),
    (
        "SPEAKER_01",
        "I want stability for my family and a chance to grow into a lead mechanic role.",
    ),
]


def stub_pipeline(_audio_path: str) -> tuple[list[DiarSegment], dict]:
    diarization: list[DiarSegment] = []
    units: list[TextUnit] = []
    timestamp = 0.0
    for speaker, text in _STUB_TURNS:
        duration = max(2.0, len(text.split()) * 0.4)
        diarization.append(
            DiarSegment(speaker=speaker, start=timestamp, end=timestamp + duration)
        )
        units.append(TextUnit(start=timestamp, end=timestamp + duration, text=text))
        timestamp += duration + 0.3
    return diarization, {"language": "en", "units": units}

