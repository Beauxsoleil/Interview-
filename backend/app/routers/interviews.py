from __future__ import annotations

import json
import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.responses import FileResponse
from interview_pipeline_core.merge import render_text
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from .. import jobs
from ..audio_validation import AudioValidationError, validate_audio
from ..config import settings
from ..database import get_db
from ..models import (
    Applicant,
    Interview,
    Job,
    JobState,
    Label,
    SyncDraft,
    Transcript,
    utcnow,
)
from ..pipeline.profile import ProfileExtractionError
from ..schemas import (
    InterviewDetail,
    InterviewSummary,
    InterviewUpdate,
    JobOut,
    ProfileOut,
    SpeakerLabelUpdate,
    TranscriptUpdate,
    TranscriptOut,
)
from ..serializers import interview_detail, interview_summary

router = APIRouter(prefix="/api/interviews", tags=["interviews"])
logger = logging.getLogger("interview.uploads")

_QUERY_LOAD = (
    joinedload(Interview.applicant),
    joinedload(Interview.labels),
    joinedload(Interview.transcript),
    joinedload(Interview.profile),
    joinedload(Interview.jobs),
)


def _get_or_404(db: Session, interview_id: int) -> Interview:
    interview = (
        db.query(Interview)
        .options(*_QUERY_LOAD)
        .filter(Interview.id == interview_id)
        .first()
    )
    if not interview:
        raise HTTPException(404, "Interview not found.")
    return interview


def _resolve_applicant(
    db: Session, applicant_id: int | None, applicant_name: str | None
) -> Applicant:
    if applicant_id:
        a = db.get(Applicant, applicant_id)
        if not a:
            raise HTTPException(404, "Applicant not found.")
        return a
    name = (applicant_name or "").strip()
    if not name:
        raise HTTPException(400, "Provide applicant_id or applicant_name.")
    existing = (
        db.query(Applicant).filter(func.lower(Applicant.name) == name.lower()).first()
    )
    if existing:
        return existing
    a = Applicant(name=name)
    db.add(a)
    db.flush()
    return a


@router.post("", response_model=InterviewDetail, status_code=201)
async def create_interview(
    db: Session = Depends(get_db),
    audio: UploadFile = File(...),
    applicant_name: str | None = Form(None),
    applicant_id: int | None = Form(None),
    title: str | None = Form(None),
    interview_date: str | None = Form(None),
):
    ext = Path(audio.filename or "").suffix.lower()
    if ext not in settings.allowed_audio_extensions:
        raise HTTPException(
            400,
            f"Unsupported audio type '{ext}'. Allowed: "
            f"{', '.join(settings.allowed_audio_extensions)}",
        )

    required_free = settings.min_free_disk_bytes + settings.max_upload_bytes
    if shutil.disk_usage(settings.audio_dir).free < required_free:
        raise HTTPException(507, "Not enough free storage to accept this upload.")

    # Stream to a temporary file, then inspect its contents before creating data.
    stored_name = f"{uuid.uuid4().hex}{ext}"
    dest = settings.audio_dir / stored_name
    temporary = settings.audio_dir / f"{uuid.uuid4().hex}.upload"
    size = 0
    try:
        with temporary.open("wb") as f:
            while chunk := await audio.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(413, "Audio file exceeds the size limit.")
                f.write(chunk)
        if size == 0:
            raise HTTPException(400, "Audio file is empty.")
        try:
            metadata = validate_audio(temporary)
        except AudioValidationError as error:
            raise HTTPException(400, str(error)) from error
        temporary.replace(dest)
    except Exception:
        temporary.unlink(missing_ok=True)
        dest.unlink(missing_ok=True)
        raise

    parsed_date = _parse_date(interview_date)
    try:
        applicant = _resolve_applicant(db, applicant_id, applicant_name)
        interview = Interview(
            applicant_id=applicant.id,
            title=(title or "").strip() or None,
            interview_date=parsed_date,
            audio_filename=audio.filename,
            audio_path=str(dest),
            audio_duration_seconds=metadata.duration_seconds,
        )
        db.add(interview)
        db.commit()
        db.refresh(interview)
    except Exception:
        db.rollback()
        dest.unlink(missing_ok=True)
        raise

    jobs.enqueue_transcription(interview.id)

    return interview_detail(_get_or_404(db, interview.id))


def _parse_date(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(400, "interview_date must be ISO 8601.")


@router.get("", response_model=list[InterviewSummary])
def list_interviews(
    db: Session = Depends(get_db),
    status: str | None = None,
    label_id: int | None = None,
    applicant_id: int | None = None,
    q: str | None = None,
    sort: str = "date",  # date|status|applicant|created
    order: str = "desc",  # asc|desc
):
    query = (
        db.query(Interview)
        .options(*_QUERY_LOAD)
        .join(Applicant)
        .filter(Interview.delete_requested.is_(False))
    )

    if status:
        query = query.filter(Interview.status == status)
    if applicant_id:
        query = query.filter(Interview.applicant_id == applicant_id)
    if label_id:
        query = query.filter(Interview.labels.any(Label.id == label_id))
    if q:
        like = f"%{q.strip()}%"
        # Search across applicant name, title, transcript text, and profile JSON.
        query = (
            query.outerjoin(Interview.transcript)
            .outerjoin(Interview.profile)
            .filter(
                or_(
                    Applicant.name.ilike(like),
                    Interview.title.ilike(like),
                    Transcript.text.ilike(like),
                    _profile_search_clause(like),
                )
            )
        )

    sort_col = {
        "date": Interview.interview_date,
        "status": Interview.status,
        "applicant": Applicant.name,
        "created": Interview.created_at,
    }.get(sort, Interview.interview_date)
    sort_col = sort_col.asc() if order == "asc" else sort_col.desc()

    interviews = query.order_by(sort_col).distinct().all()
    return [interview_summary(i) for i in interviews]


def _profile_search_clause(like: str):
    from ..models import Profile

    return Profile.data_json.ilike(like)


@router.get("/{interview_id}", response_model=InterviewDetail)
def get_interview(interview_id: int, db: Session = Depends(get_db)):
    return interview_detail(_get_or_404(db, interview_id))


@router.patch("/{interview_id}", response_model=InterviewDetail)
def update_interview(
    interview_id: int, payload: InterviewUpdate, db: Session = Depends(get_db)
):
    interview = _get_or_404(db, interview_id)
    if payload.title is not None:
        interview.title = payload.title.strip() or None
    if payload.status is not None:
        interview.status = payload.status.strip()
    if payload.interview_date is not None:
        interview.interview_date = payload.interview_date
    if payload.label_ids is not None:
        labels = db.query(Label).filter(Label.id.in_(payload.label_ids)).all()
        interview.labels = labels
    db.commit()
    return interview_detail(_get_or_404(db, interview_id))


@router.delete("/{interview_id}", status_code=204)
def delete_interview(interview_id: int, db: Session = Depends(get_db)):
    interview = _get_or_404(db, interview_id)
    active_jobs = [
        job
        for job in interview.jobs
        if job.state in {JobState.QUEUED.value, JobState.RUNNING.value}
    ]
    if active_jobs:
        interview.delete_requested = True
        for job in active_jobs:
            job.state = JobState.CANCELLED.value
            job.stage = "cancellation requested"
            job.error = None
        db.commit()
        return

    audio_path = Path(interview.audio_path) if interview.audio_path else None
    db.delete(interview)
    db.commit()
    if audio_path:
        try:
            audio_path.unlink(missing_ok=True)
        except OSError:
            logger.exception("Could not remove orphaned audio for interview %s", interview_id)


@router.get("/{interview_id}/audio")
def get_audio(interview_id: int, db: Session = Depends(get_db)):
    interview = _get_or_404(db, interview_id)
    if not interview.audio_path or not Path(interview.audio_path).exists():
        raise HTTPException(404, "Audio file not found.")
    return FileResponse(
        interview.audio_path,
        filename=interview.audio_filename or "audio",
    )


@router.patch("/{interview_id}/speakers", response_model=TranscriptOut)
def update_speakers(
    interview_id: int, payload: SpeakerLabelUpdate, db: Session = Depends(get_db)
):
    interview = _get_or_404(db, interview_id)
    transcript = interview.transcript
    if not transcript:
        raise HTTPException(404, "Interview has no transcript yet.")

    if payload.speaker_labels is not None:
        current = json.loads(transcript.speaker_labels_json or "{}")
        current.update({k: v for k, v in payload.speaker_labels.items()})
        transcript.speaker_labels_json = json.dumps(current)
        # Re-render the plain-text transcript with the friendly names.
        turns = json.loads(transcript.segments_json)
        transcript.text = render_text(turns, current)

    if payload.applicant_speaker is not None:
        speakers = {item["speaker"] for item in json.loads(transcript.segments_json)}
        if payload.applicant_speaker not in speakers:
            raise HTTPException(400, "Applicant speaker must exist in the transcript.")
        transcript.applicant_speaker = payload.applicant_speaker

    _invalidate_derived_data(db, interview, transcript)
    db.commit()
    db.refresh(transcript)
    return TranscriptOut.from_orm_transcript(transcript)


def _invalidate_derived_data(db: Session, interview: Interview, transcript: Transcript) -> None:
    transcript.reviewed_at = None
    if interview.profile:
        db.delete(interview.profile)
    draft = db.query(SyncDraft).filter_by(interview_id=interview.id).first()
    if draft:
        db.delete(draft)


@router.patch("/{interview_id}/transcript", response_model=TranscriptOut)
def update_transcript(
    interview_id: int, payload: TranscriptUpdate, db: Session = Depends(get_db)
):
    interview = _get_or_404(db, interview_id)
    transcript = interview.transcript
    if not transcript:
        raise HTTPException(404, "Interview has no transcript yet.")
    segments = [segment.model_dump() for segment in payload.segments]
    transcript.segments_json = json.dumps(segments)
    transcript.text = render_text(
        segments, json.loads(transcript.speaker_labels_json or "{}")
    )
    transcript.revision += 1
    transcript.edited_at = utcnow()
    _invalidate_derived_data(db, interview, transcript)
    db.commit()
    db.refresh(transcript)
    return TranscriptOut.from_orm_transcript(transcript)


@router.post("/{interview_id}/transcript/review", response_model=TranscriptOut)
def review_transcript(interview_id: int, db: Session = Depends(get_db)):
    interview = _get_or_404(db, interview_id)
    transcript = interview.transcript
    if not transcript:
        raise HTTPException(404, "Interview has no transcript yet.")
    speakers = {item["speaker"] for item in json.loads(transcript.segments_json)}
    if not transcript.applicant_speaker or transcript.applicant_speaker not in speakers:
        raise HTTPException(
            400, "Select the applicant speaker before marking the transcript reviewed."
        )
    transcript.reviewed_at = utcnow()
    db.commit()
    db.refresh(transcript)
    return TranscriptOut.from_orm_transcript(transcript)


@router.post("/{interview_id}/reprocess", response_model=JobOut)
def reprocess(interview_id: int, db: Session = Depends(get_db)):
    interview = _get_or_404(db, interview_id)
    if not interview.audio_path:
        raise HTTPException(400, "Interview has no audio to reprocess.")
    job_id = jobs.enqueue_transcription(interview.id)
    job = db.get(Job, job_id)
    return JobOut.model_validate(job)


@router.post("/{interview_id}/extract-profile", response_model=ProfileOut)
def extract_profile(interview_id: int, db: Session = Depends(get_db)):
    interview = _get_or_404(db, interview_id)
    if not interview.transcript:
        raise HTTPException(400, "Interview has no transcript to profile.")
    if not interview.transcript.reviewed_at:
        raise HTTPException(
            409, "Review the transcript and applicant speaker before profile extraction."
        )
    try:
        # Runs in its own session; the returned instance is detached but fully
        # loaded, so serialize it directly (don't touch it with this session).
        profile = jobs.run_profile_extraction(interview.id)
    except ProfileExtractionError as e:
        raise HTTPException(400, str(e))
    return ProfileOut.from_orm_profile(profile)


@router.get("/{interview_id}/jobs", response_model=list[JobOut])
def list_jobs(interview_id: int, db: Session = Depends(get_db)):
    interview = _get_or_404(db, interview_id)
    return [JobOut.model_validate(j) for j in interview.jobs]
