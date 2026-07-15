"""Merge diarization (who spoke when) with transcription (what was said).

The strategy: assign each transcribed unit (word if available, else segment) to
the diarization speaker whose interval overlaps it most. Then collapse
consecutive units from the same speaker into speaker turns.
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
    for d in diar:
        overlap = min(unit.end, d.end) - max(unit.start, d.start)
        if overlap > best_overlap:
            best_overlap = overlap
            best_speaker = d.speaker
    if best_speaker is None and diar:
        # No overlap (e.g. word between turns): fall back to nearest by midpoint.
        mid = (unit.start + unit.end) / 2
        best_speaker = min(
            diar, key=lambda d: min(abs(mid - d.start), abs(mid - d.end))
        ).speaker
    return best_speaker


def merge(
    diar: list[DiarSegment], units: list[TextUnit]
) -> list[dict]:
    """Return speaker turns: [{speaker, start, end, text}] in chronological order."""
    if not units:
        return []

    labeled: list[tuple[str, TextUnit]] = []
    fallback_speaker = diar[0].speaker if diar else "Speaker 1"
    for u in sorted(units, key=lambda x: x.start):
        speaker = _best_speaker(u, diar) or fallback_speaker
        labeled.append((speaker, u))

    turns: list[dict] = []
    for speaker, u in labeled:
        text = u.text.strip()
        if not text:
            continue
        if turns and turns[-1]["speaker"] == speaker:
            turns[-1]["text"] = f"{turns[-1]['text']} {text}".strip()
            turns[-1]["end"] = u.end
        else:
            turns.append(
                {"speaker": speaker, "start": u.start, "end": u.end, "text": text}
            )
    return turns


def normalize_speaker_ids(turns: list[dict]) -> tuple[list[dict], list[str]]:
    """Rename raw diarization ids (SPEAKER_00, ...) to 'Speaker 1', 'Speaker 2'
    in order of first appearance. Returns (turns, ordered_speaker_names)."""
    mapping: dict[str, str] = {}
    order: list[str] = []
    for t in turns:
        raw = t["speaker"]
        if raw not in mapping:
            mapping[raw] = f"Speaker {len(mapping) + 1}"
            order.append(mapping[raw])
        t["speaker"] = mapping[raw]
    return turns, order


def render_text(turns: list[dict], speaker_labels: dict[str, str] | None = None) -> str:
    """Render turns as a readable labeled transcript."""
    labels = speaker_labels or {}
    lines = []
    for t in turns:
        name = labels.get(t["speaker"]) or t["speaker"]
        lines.append(f"{name}: {t['text']}")
    return "\n".join(lines)
