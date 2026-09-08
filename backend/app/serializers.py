"""Helpers to build response schemas from ORM objects."""
from __future__ import annotations

from .models import Interview, Job
from .schemas import (
    InterviewDetail,
    InterviewPartOut,
    InterviewSummary,
    JobOut,
    LabelOut,
    ProfileOut,
    TranscriptOut,
)


def _latest_job(interview: Interview) -> JobOut | None:
    jobs: list[Job] = interview.jobs
    if not jobs:
        return None
    return JobOut.model_validate(jobs[0])


def interview_summary(interview: Interview) -> InterviewSummary:
    return InterviewSummary(
        id=interview.id,
        applicant_id=interview.applicant_id,
        applicant_name=interview.applicant.name if interview.applicant else "",
        title=interview.title,
        interview_date=interview.interview_date,
        audio_filename=interview.audio_filename,
        audio_duration_seconds=interview.audio_duration_seconds,
        status=interview.status,
        labels=[LabelOut.model_validate(l) for l in interview.labels],
        has_transcript=interview.transcript is not None,
        has_profile=interview.profile is not None,
        transcript_reviewed=bool(interview.transcript and interview.transcript.reviewed_at),
        is_combined=interview.is_combined,
        part_count=len(interview.source_parts) if interview.is_combined else 1,
        combined_needs_rebuild=interview.combined_needs_rebuild,
        latest_job=_latest_job(interview),
        created_at=interview.created_at,
    )


def interview_detail(interview: Interview) -> InterviewDetail:
    base = interview_summary(interview).model_dump()
    offset = 0.0
    parts = []
    for position, part in enumerate(interview.source_parts, start=1):
        parts.append(
            InterviewPartOut(
                id=part.id,
                position=part.part_number or position,
                audio_filename=part.audio_filename,
                audio_duration_seconds=part.audio_duration_seconds,
                offset_seconds=offset,
                transcript_revision=part.transcript.revision if part.transcript else None,
                transcript_reviewed=bool(part.transcript and part.transcript.reviewed_at),
            )
        )
        offset += part.audio_duration_seconds or 0.0
    return InterviewDetail(
        **base,
        transcript=TranscriptOut.from_orm_transcript(interview.transcript)
        if interview.transcript
        else None,
        profile=ProfileOut.from_orm_profile(interview.profile)
        if interview.profile
        else None,
        parts=parts,
    )
