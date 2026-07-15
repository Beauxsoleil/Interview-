"""Helpers to build response schemas from ORM objects."""
from __future__ import annotations

from .models import Interview, Job
from .schemas import (
    InterviewDetail,
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
        status=interview.status,
        labels=[LabelOut.model_validate(l) for l in interview.labels],
        has_transcript=interview.transcript is not None,
        has_profile=interview.profile is not None,
        latest_job=_latest_job(interview),
        created_at=interview.created_at,
    )


def interview_detail(interview: Interview) -> InterviewDetail:
    base = interview_summary(interview).model_dump()
    return InterviewDetail(
        **base,
        audio_filename=interview.audio_filename,
        transcript=TranscriptOut.from_orm_transcript(interview.transcript)
        if interview.transcript
        else None,
        profile=ProfileOut.from_orm_profile(interview.profile)
        if interview.profile
        else None,
    )
