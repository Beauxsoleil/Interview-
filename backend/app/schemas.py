"""Pydantic schemas for the API and for structured profile extraction."""
from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

# --------------------------------------------------------------------------
# Applicant profile schema
#
# The LLM extracts INTO this schema (structured JSON), and the UI renders a
# card from it. Every field is optional and defaults to the sentinel
# "not mentioned" rather than being guessed. Free-text notes capture goals,
# motivations, and other flags.
# --------------------------------------------------------------------------

NOT_MENTIONED = "not mentioned"


class ProfileField(BaseModel):
    """A single extracted field with the supporting evidence."""

    value: str = Field(
        default=NOT_MENTIONED,
        description="Extracted value, or 'not mentioned' if the transcript does "
        "not cover it. Never guess.",
    )
    evidence: str | None = Field(
        default=None,
        description="Short quote or paraphrase from the transcript supporting "
        "the value, or null if not mentioned.",
    )


class ApplicantProfile(BaseModel):
    age: ProfileField = Field(default_factory=ProfileField)
    physical_health: ProfileField = Field(default_factory=ProfileField)
    prior_service_history: ProfileField = Field(default_factory=ProfileField)
    legal_history: ProfileField = Field(default_factory=ProfileField)
    education_level: ProfileField = Field(default_factory=ProfileField)
    marital_status: ProfileField = Field(default_factory=ProfileField)
    number_of_dependents: ProfileField = Field(default_factory=ProfileField)
    tattoos_brandings_piercings: ProfileField = Field(default_factory=ProfileField)
    free_text_notes: str = Field(
        default="",
        description="Free-text summary: stated goals, motivations, and other "
        "relevant flags. Empty string if nothing notable.",
    )


# --------------------------------------------------------------------------
# Request / response models
# --------------------------------------------------------------------------


class ApplicantCreate(BaseModel):
    name: str
    notes: str | None = None


class ApplicantOut(BaseModel):
    id: int
    name: str
    notes: str | None
    created_at: datetime
    interview_count: int = 0

    model_config = {"from_attributes": True}


class LabelCreate(BaseModel):
    name: str
    color: str = "#64748b"


class LabelOut(BaseModel):
    id: int
    name: str
    color: str

    model_config = {"from_attributes": True}


class TranscriptSegment(BaseModel):
    speaker: str
    start: float
    end: float
    text: str


class TranscriptOut(BaseModel):
    id: int
    language: str | None
    text: str
    segments: list[TranscriptSegment]
    speaker_labels: dict[str, str]
    applicant_speaker: str | None
    created_at: datetime

    @classmethod
    def from_orm_transcript(cls, t) -> "TranscriptOut":
        return cls(
            id=t.id,
            language=t.language,
            text=t.text,
            segments=[TranscriptSegment(**s) for s in json.loads(t.segments_json)],
            speaker_labels=json.loads(t.speaker_labels_json),
            applicant_speaker=t.applicant_speaker,
            created_at=t.created_at,
        )


class ProfileOut(BaseModel):
    id: int
    data: ApplicantProfile
    model: str | None
    created_at: datetime

    @classmethod
    def from_orm_profile(cls, p) -> "ProfileOut":
        return cls(
            id=p.id,
            data=ApplicantProfile.model_validate(json.loads(p.data_json)),
            model=p.model,
            created_at=p.created_at,
        )


class JobOut(BaseModel):
    id: int
    kind: str
    state: str
    progress: int
    stage: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InterviewSummary(BaseModel):
    """Row shape for the sortable/filterable list view."""

    id: int
    applicant_id: int
    applicant_name: str
    title: str | None
    interview_date: datetime
    status: str
    labels: list[LabelOut]
    has_transcript: bool
    has_profile: bool
    latest_job: JobOut | None
    created_at: datetime


class InterviewDetail(InterviewSummary):
    audio_filename: str | None
    transcript: TranscriptOut | None
    profile: ProfileOut | None


class InterviewUpdate(BaseModel):
    title: str | None = None
    status: str | None = None
    interview_date: datetime | None = None
    label_ids: list[int] | None = None


class SpeakerLabelUpdate(BaseModel):
    """Rename raw speakers -> roles and mark which one is the applicant."""

    speaker_labels: dict[str, str] | None = None
    applicant_speaker: str | None = None

    @field_validator("speaker_labels")
    @classmethod
    def _strip(cls, v):
        if v is None:
            return v
        return {k: (val or "").strip() for k, val in v.items()}
