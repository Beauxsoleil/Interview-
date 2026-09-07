"""Merge diarization (who spoke when) with transcription (what was said)."""

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
        midpoint = (unit.start + unit.end) / 2
        best_speaker = min(
            diar,
            key=lambda segment: min(
                abs(midpoint - segment.start), abs(midpoint - segment.end)
            ),
        ).speaker
    return best_speaker


def merge(diar: list[DiarSegment], units: list[TextUnit]) -> list[dict]:
    """Return chronological speaker turns."""
    if not units:
        return []

    labeled: list[tuple[str, TextUnit]] = []
    fallback_speaker = diar[0].speaker if diar else "Speaker 1"
    for unit in sorted(units, key=lambda item: item.start):
        labeled.append((_best_speaker(unit, diar) or fallback_speaker, unit))

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
    """Rename raw IDs to ``Speaker N`` in order of first appearance."""
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
    return "\n".join(
        f"{labels.get(turn['speaker']) or turn['speaker']}: {turn['text']}"
        for turn in turns
    )

