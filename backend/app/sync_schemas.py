"""Typed API and Gemini schemas for reviewed PIBASE synchronization."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

NOT_MENTIONED = "not mentioned"
FIRESTORE_SYNC_FIELDS = (
    "age",
    "priorService",
    "physicalHealth",
    "legalIssues",
    "educationLevel",
    "maritalStatus",
    "dependents",
    "tattoosBrandsPiercings",
    "generalArea",
)


class ExtractedSyncField(BaseModel):
    value: str | int | None = Field(
        default=NOT_MENTIONED,
        description="Stated value or exactly 'not mentioned'; never guess.",
    )
    evidence: str | None = Field(
        default=None,
        description="Short transcript quote or paraphrase, or null.",
    )


class FirestoreSyncExtraction(BaseModel):
    applicant_name: ExtractedSyncField = Field(default_factory=ExtractedSyncField)
    age: ExtractedSyncField = Field(default_factory=ExtractedSyncField)
    priorService: ExtractedSyncField = Field(default_factory=ExtractedSyncField)
    physicalHealth: ExtractedSyncField = Field(default_factory=ExtractedSyncField)
    legalIssues: ExtractedSyncField = Field(default_factory=ExtractedSyncField)
    educationLevel: ExtractedSyncField = Field(default_factory=ExtractedSyncField)
    maritalStatus: ExtractedSyncField = Field(default_factory=ExtractedSyncField)
    dependents: ExtractedSyncField = Field(default_factory=ExtractedSyncField)
    tattoosBrandsPiercings: ExtractedSyncField = Field(
        default_factory=ExtractedSyncField
    )
    generalArea: ExtractedSyncField = Field(default_factory=ExtractedSyncField)
    free_text_notes: str = ""

    @field_validator("age", "dependents")
    @classmethod
    def validate_numbers(cls, field: ExtractedSyncField) -> ExtractedSyncField:
        value = field.value
        if isinstance(value, str) and value.strip().isdigit():
            field.value = int(value.strip())
        elif value is not None and not isinstance(value, int) and value != NOT_MENTIONED:
            field.value = NOT_MENTIONED
            field.evidence = None
        return field

    @field_validator("educationLevel")
    @classmethod
    def validate_education(cls, field: ExtractedSyncField) -> ExtractedSyncField:
        allowed = {NOT_MENTIONED, "", "HS Diploma", "GED", "Some College", "Degree"}
        if field.value not in allowed:
            field.value = ""
        return field

    @field_validator("maritalStatus")
    @classmethod
    def validate_marital(cls, field: ExtractedSyncField) -> ExtractedSyncField:
        allowed = {NOT_MENTIONED, "", "Single", "Married", "Divorced", "Other"}
        if field.value not in allowed:
            field.value = ""
        return field


class FirestoreApplicant(BaseModel):
    id: str
    name: str = ""
    phone: str = ""
    statusStage: str = ""
    archived: bool = False
    data: dict = Field(default_factory=dict)


class SyncExtractOut(BaseModel):
    extraction: FirestoreSyncExtraction
    model: str


class SyncProposalRequest(BaseModel):
    applicant_id: str | None = None
    create_new: bool = False
    new_applicant_name: str | None = None


class ProposedChange(BaseModel):
    field: str
    current_value: str | int | None = None
    proposed_value: str | int | None = None
    evidence: str | None = None
    changed: bool


class SyncProposalOut(BaseModel):
    target: FirestoreApplicant | None
    create_new: bool
    archived: bool
    changes: list[ProposedChange]
    note: str


class SyncConfirmRequest(SyncProposalRequest):
    approved_fields: list[str] = Field(default_factory=list)
    approved_by: str = Field(min_length=1, max_length=255)
    unarchive: bool = False

    @field_validator("approved_fields")
    @classmethod
    def only_known_fields(cls, fields: list[str]) -> list[str]:
        unknown = set(fields) - set(FIRESTORE_SYNC_FIELDS)
        if unknown:
            raise ValueError(f"Unsupported sync fields: {', '.join(sorted(unknown))}")
        return list(dict.fromkeys(fields))


class SyncLogOut(BaseModel):
    id: int
    interview_id: int
    firestore_applicant_id: str
    note_id: str
    approved_by: str
    fields_written: list[str]
    created_at: datetime


class SyncConfirmOut(BaseModel):
    applicant_id: str
    note_id: str
    fields_written: list[str]
    unarchived: bool
    log: SyncLogOut
