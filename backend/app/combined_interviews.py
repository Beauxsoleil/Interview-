"""Non-destructive construction of one interview from reviewed source parts."""

from __future__ import annotations

import json
from collections.abc import Sequence

from interview_pipeline_core.merge import render_text
from sqlalchemy.orm import Session

from .models import Interview, InterviewStatus, JobState, SyncDraft, Transcript


class CombinedInterviewError(ValueError):
    pass


def _source_role(source: Interview, raw_speaker: str, part_number: int) -> str:
    transcript = source.transcript
    assert transcript is not None
    if raw_speaker == transcript.applicant_speaker:
        return "Applicant"
    labels = json.loads(transcript.speaker_labels_json or "{}")
    label = str(labels.get(raw_speaker) or "").strip()
    if label and label.casefold() != "applicant":
        return label
    speakers = {item["speaker"] for item in json.loads(transcript.segments_json)}
    if len(speakers) == 2:
        return "Interviewer"
    return f"Part {part_number} — {raw_speaker}"


def build_combined_segments(sources: Sequence[Interview]) -> tuple[list[dict], float]:
    combined: list[dict] = []
    offset = 0.0
    for position, source in enumerate(sources, start=1):
        transcript = source.transcript
        if transcript is None:
            raise CombinedInterviewError("Every recording needs a transcript.")
        source_segments = json.loads(transcript.segments_json)
        fallback_duration = max((float(item["end"]) for item in source_segments), default=0.0)
        duration = source.audio_duration_seconds or fallback_duration
        for item in source_segments:
            local_start = float(item["start"])
            local_end = float(item["end"])
            combined.append(
                {
                    "speaker": _source_role(source, item["speaker"], position),
                    "start": offset + local_start,
                    "end": offset + local_end,
                    "text": item["text"],
                    "source_interview_id": source.id,
                    "source_start": local_start,
                    "source_end": local_end,
                    "part_number": position,
                }
            )
        offset += duration
    return combined, offset


def _validate_sources(sources: Sequence[Interview], requested_count: int) -> None:
    if len(sources) != requested_count:
        raise CombinedInterviewError("One or more selected interviews no longer exist.")
    applicant_ids = {source.applicant_id for source in sources}
    if len(applicant_ids) != 1:
        raise CombinedInterviewError("All recordings must belong to the same applicant.")
    for source in sources:
        if source.is_combined or source.combined_parent_id:
            raise CombinedInterviewError(
                "A selected interview is already part of a combined interview."
            )
        if not source.transcript or not source.transcript.reviewed_at:
            raise CombinedInterviewError(
                "Review every source transcript before combining recordings."
            )
        if not source.transcript.applicant_speaker:
            raise CombinedInterviewError(
                "Select the applicant speaker in every source transcript first."
            )
        if any(
            job.state in {JobState.QUEUED.value, JobState.RUNNING.value}
            for job in source.jobs
        ):
            raise CombinedInterviewError(
                "Wait for all selected recordings to finish processing."
            )


def create_combined_interview(
    db: Session, source_ids: list[int], title: str | None = None
) -> Interview:
    records = db.query(Interview).filter(Interview.id.in_(source_ids)).all()
    by_id = {record.id: record for record in records}
    sources = [by_id[source_id] for source_id in source_ids if source_id in by_id]
    _validate_sources(sources, len(source_ids))

    segments, duration = build_combined_segments(sources)
    first = sources[0]
    combined = Interview(
        applicant_id=first.applicant_id,
        title=(title or "").strip() or "Combined interview",
        interview_date=first.interview_date,
        status=InterviewStatus.PENDING_REVIEW.value,
        audio_duration_seconds=duration,
        is_combined=True,
    )
    db.add(combined)
    db.flush()
    for position, source in enumerate(sources, start=1):
        source.combined_parent_id = combined.id
        source.part_number = position

    languages = [source.transcript.language for source in sources if source.transcript]
    transcript = Transcript(
        interview_id=combined.id,
        language=next((language for language in languages if language), None),
        text=render_text(segments),
        segments_json=json.dumps(segments),
        speaker_labels_json=json.dumps({"Applicant": "Applicant"}),
        applicant_speaker="Applicant",
        revision=1,
    )
    db.add(transcript)
    db.commit()
    db.refresh(combined)
    return combined


def rebuild_combined_interview(db: Session, combined: Interview) -> Interview:
    if not combined.is_combined or len(combined.source_parts) < 2:
        raise CombinedInterviewError("This is not a multi-part interview.")
    sources = list(combined.source_parts)
    for source in sources:
        if not source.transcript or not source.transcript.reviewed_at:
            raise CombinedInterviewError(
                "Review every source transcript before rebuilding."
            )
    segments, duration = build_combined_segments(sources)
    transcript = combined.transcript
    if transcript is None:
        transcript = Transcript(interview_id=combined.id)
    transcript.text = render_text(segments)
    transcript.segments_json = json.dumps(segments)
    transcript.speaker_labels_json = json.dumps({"Applicant": "Applicant"})
    transcript.applicant_speaker = "Applicant"
    transcript.revision = (transcript.revision or 0) + 1
    transcript.reviewed_at = None
    combined.audio_duration_seconds = duration
    combined.combined_needs_rebuild = False
    if combined.profile:
        db.delete(combined.profile)
    draft = db.query(SyncDraft).filter_by(interview_id=combined.id).first()
    if draft:
        db.delete(draft)
    db.add(transcript)
    db.commit()
    db.refresh(combined)
    return combined


def mark_combined_parent_stale(db: Session, source: Interview) -> None:
    parent = source.combined_parent
    if not parent:
        return
    parent.combined_needs_rebuild = True
    if parent.transcript:
        parent.transcript.reviewed_at = None
    if parent.profile:
        db.delete(parent.profile)
    draft = db.query(SyncDraft).filter_by(interview_id=parent.id).first()
    if draft:
        db.delete(draft)
