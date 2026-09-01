"""Merge diarization (who spoke when) with transcription (what was said).

Each transcribed unit is assigned to the diarization speaker whose interval
overlaps it most. Consecutive units from the same speaker are then collapsed
into readable speaker turns.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DiarSegment:
    speaker: str
    start: float
    end: float


@dataclass
class TextUnit:
    start: float
    end: float
    text: str


def _best_speaker(unit: TextUnit, diar: list[DiarSegment]) -> str | None:
    best_speaker: str | None = None
    best_overlap = 0.0
    for segment in diar:
        overlap = min(unit.end, segment.end) - max(unit.start, segment.start)
        if overlap > best_overlap:
            best_overlap = overlap
            best_speaker = segment.speaker
    if best_speaker is None and diar:
        mid = (unit.start + unit.end) / 2
        best_speaker = min(
            diar,
            key=lambda segment: min(
                abs(mid - segment.start), abs(mid - segment.end)
            ),
        ).speaker
    return best_speaker


def merge(diar: list[DiarSegment], units: list[TextUnit]) -> list[dict]:
    """Return chronological `{speaker, start, end, text}` turns."""
    if not units:
        return []

    labeled: list[tuple[str, TextUnit]] = []
    fallback_speaker = diar[0].speaker if diar else "Speaker 1"
    for unit in sorted(units, key=lambda item: item.start):
        speaker = _best_speaker(unit, diar) or fallback_speaker
        labeled.append((speaker, unit))

    turns: list[dict] = []
    for speaker, unit in labeled:
        text = unit.text.strip()
        if not text:
            continue
        if turns and turns[-1]["speaker"] == speaker:
            turns[-1]["text"] = f"{turns[-1]['text']} {text}".strip()
            turns[-1]["end"] = unit.end
        else:
            turns.append(
                {
                    "speaker": speaker,
                    "start": unit.start,
                    "end": unit.end,
                    "text": text,
                }
            )
    return turns


def normalize_speaker_ids(turns: list[dict]) -> tuple[list[dict], list[str]]:
    """Normalize raw speaker ids in order of first appearance."""
    mapping: dict[str, str] = {}
    order: list[str] = []
    for turn in turns:
        raw = turn["speaker"]
        if raw not in mapping:
            mapping[raw] = f"Speaker {len(mapping) + 1}"
            order.append(mapping[raw])
        turn["speaker"] = mapping[raw]
    return turns, order


def render_text(
    turns: list[dict], speaker_labels: dict[str, str] | None = None
) -> str:
    """Render turns as a readable labeled transcript."""
    labels = speaker_labels or {}
    lines = []
    for turn in turns:
        name = labels.get(turn["speaker"]) or turn["speaker"]
        lines.append(f"{name}: {turn['text']}")
    return "\n".join(lines)
