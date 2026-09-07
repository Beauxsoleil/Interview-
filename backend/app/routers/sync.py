"""Reviewed Interview-to-PIBASE synchronization endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..firestore_sync import (
    ArchivedApplicantError,
    FirestoreConfigurationError,
    FirestoreGateway,
    SyncConflictError,
    get_firestore_gateway,
)
from ..models import Interview, SyncDraft, SyncLog
from ..pipeline.sync_profile import GeminiRateLimitError, SyncProfileError, extract_sync_profile
from ..sync_schemas import (
    FIRESTORE_SYNC_FIELDS,
    NOT_MENTIONED,
    FirestoreApplicant,
    FirestoreSyncExtraction,
    ProposedChange,
    SyncConfirmOut,
    SyncConfirmRequest,
    SyncExtractOut,
    SyncLogOut,
    SyncProposalOut,
    SyncProposalRequest,
)

router = APIRouter(prefix="/api/interviews/{interview_id}/sync", tags=["pibase-sync"])


def _gateway() -> FirestoreGateway:
    try:
        return get_firestore_gateway()
    except FirestoreConfigurationError as error:
        raise HTTPException(503, str(error)) from error


def _interview(db: Session, interview_id: int) -> Interview:
    interview = db.get(Interview, interview_id)
    if not interview:
        raise HTTPException(404, "Interview not found.")
    return interview


def _draft(db: Session, interview_id: int) -> FirestoreSyncExtraction:
    draft = db.query(SyncDraft).filter_by(interview_id=interview_id).first()
    if not draft:
        raise HTTPException(409, "Run sync extraction before proposing a write.")
    interview = _interview(db, interview_id)
    if (
        not interview.transcript
        or draft.source_transcript_revision != interview.transcript.revision
    ):
        raise HTTPException(
            409, "The transcript changed after extraction. Run sync extraction again."
        )
    return FirestoreSyncExtraction.model_validate_json(draft.data_json)


def _field_value(extraction: FirestoreSyncExtraction, field: str):
    value = getattr(extraction, field).value
    if value == NOT_MENTIONED:
        return None
    # An out-of-set education/marital answer is normalized to blank for manual
    # entry, but blank must never become a proposal to erase an existing value.
    if field in {"educationLevel", "maritalStatus"} and value == "":
        return None
    return value


def _log_out(log: SyncLog) -> SyncLogOut:
    return SyncLogOut(
        id=log.id,
        interview_id=log.interview_id,
        firestore_applicant_id=log.firestore_applicant_id,
        note_id=log.note_id,
        approved_by=log.approved_by,
        fields_written=json.loads(log.fields_written_json),
        created_at=log.created_at,
    )


@router.post("/extract", response_model=SyncExtractOut)
def extract(interview_id: int, db: Session = Depends(get_db)):
    interview = _interview(db, interview_id)
    if not interview.transcript:
        raise HTTPException(400, "Interview has no transcript.")
    transcript = interview.transcript
    if not transcript.reviewed_at:
        raise HTTPException(
            409, "Review the transcript and applicant speaker before PIBASE extraction."
        )
    labels = json.loads(transcript.speaker_labels_json or "{}")
    applicant = transcript.applicant_speaker or "the applicant"
    try:
        extraction, model = extract_sync_profile(
            transcript.text, labels.get(applicant, applicant)
        )
    except GeminiRateLimitError as error:
        raise HTTPException(
            429,
            {"message": str(error), "retry_after": error.retry_after_seconds},
            headers={"Retry-After": str(error.retry_after_seconds)},
        ) from error
    except SyncProfileError as error:
        raise HTTPException(400, str(error)) from error

    draft = db.query(SyncDraft).filter_by(interview_id=interview_id).first()
    if not draft:
        draft = SyncDraft(interview_id=interview_id, data_json="{}", model=model)
    draft.data_json = extraction.model_dump_json()
    draft.model = model
    draft.source_transcript_revision = transcript.revision
    db.add(draft)
    db.commit()
    return SyncExtractOut(extraction=extraction, model=model)


@router.get("/candidates", response_model=list[FirestoreApplicant])
def candidates(
    interview_id: int,
    q: str | None = Query(default=None, max_length=255),
    db: Session = Depends(get_db),
    gateway: FirestoreGateway = Depends(_gateway),
):
    interview = _interview(db, interview_id)
    draft = _draft(db, interview.id)
    default_name = draft.applicant_name.value
    query = q if q is not None else ("" if default_name == NOT_MENTIONED else str(default_name))
    return gateway.search_applicants(query)


def _target(
    payload: SyncProposalRequest, gateway: FirestoreGateway
) -> FirestoreApplicant | None:
    if payload.create_new:
        if payload.applicant_id:
            raise HTTPException(400, "Choose an existing applicant or create new, not both.")
        return None
    if not payload.applicant_id:
        raise HTTPException(400, "Select an applicant or choose create new.")
    target = gateway.get_applicant(payload.applicant_id)
    if not target:
        raise HTTPException(404, "PIBASE applicant not found.")
    return target


@router.post("/proposal", response_model=SyncProposalOut)
def proposal(
    interview_id: int,
    payload: SyncProposalRequest,
    db: Session = Depends(get_db),
    gateway: FirestoreGateway = Depends(_gateway),
):
    _interview(db, interview_id)
    extraction = _draft(db, interview_id)
    target = _target(payload, gateway)
    current = target.data if target else {}
    changes = []
    for field in FIRESTORE_SYNC_FIELDS:
        proposed = _field_value(extraction, field)
        changes.append(
            ProposedChange(
                field=field,
                current_value=current.get(field),
                proposed_value=proposed,
                evidence=getattr(extraction, field).evidence,
                changed=proposed is not None and proposed != current.get(field),
            )
        )
    return SyncProposalOut(
        target=target,
        create_new=payload.create_new,
        archived=bool(target and target.archived),
        changes=changes,
        note=extraction.free_text_notes,
    )


@router.post("/confirm", response_model=SyncConfirmOut)
def confirm(
    interview_id: int,
    payload: SyncConfirmRequest,
    db: Session = Depends(get_db),
    gateway: FirestoreGateway = Depends(_gateway),
):
    interview = _interview(db, interview_id)
    existing_log = (
        db.query(SyncLog)
        .filter_by(interview_id=interview.id, request_id=payload.request_id)
        .first()
    )
    if existing_log:
        return SyncConfirmOut(
            applicant_id=existing_log.firestore_applicant_id,
            note_id=existing_log.note_id,
            fields_written=json.loads(existing_log.fields_written_json),
            unarchived=False,
            log=_log_out(existing_log),
        )
    extraction = _draft(db, interview.id)
    target = _target(payload, gateway)
    if target and target.archived and not payload.unarchive:
        raise HTTPException(
            409, "This applicant is archived; explicitly unarchive before syncing."
        )

    approved_values = {
        field: _field_value(extraction, field)
        for field in payload.approved_fields
        if _field_value(extraction, field) is not None
    }
    extracted_name = extraction.applicant_name.value
    new_name = payload.new_applicant_name or (
        None if extracted_name == NOT_MENTIONED else str(extracted_name)
    )
    note = extraction.free_text_notes.strip() or (
        f"Interview {interview.id} reviewed; no additional summary was extracted."
    )
    try:
        applicant_id, note_id, unarchived = gateway.write_reviewed_sync(
            applicant_id=target.id if target else None,
            new_applicant_name=new_name,
            approved_values=approved_values,
            note=note,
            interview_id=interview.id,
            approved_by=payload.approved_by.strip(),
            unarchive=payload.unarchive,
            request_id=payload.request_id,
            expected_values=payload.expected_values,
        )
    except ArchivedApplicantError as error:
        raise HTTPException(409, str(error)) from error
    except SyncConflictError as error:
        raise HTTPException(409, str(error)) from error
    except ValueError as error:
        raise HTTPException(400, str(error)) from error

    fields_written = list(approved_values)
    log = SyncLog(
        request_id=payload.request_id,
        interview_id=interview.id,
        firestore_applicant_id=applicant_id,
        note_id=note_id,
        approved_by=payload.approved_by.strip(),
        fields_written_json=json.dumps(fields_written),
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return SyncConfirmOut(
        applicant_id=applicant_id,
        note_id=note_id,
        fields_written=fields_written,
        unarchived=unarchived,
        log=_log_out(log),
    )


@router.get("/logs", response_model=list[SyncLogOut])
def logs(interview_id: int, db: Session = Depends(get_db)):
    _interview(db, interview_id)
    records = (
        db.query(SyncLog)
        .filter_by(interview_id=interview_id)
        .order_by(SyncLog.created_at.desc())
        .all()
    )
    return [_log_out(record) for record in records]
