from __future__ import annotations

import json
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
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from .. import jobs
from ..config import settings
from ..database import get_db
from ..models import Applicant, Interview, Job, Label, Transcript
from ..pipeline.merge import render_text
from ..pipeline.profile import ProfileExtractionError
from ..schemas import (
    InterviewDetail,
    InterviewSummary,
    InterviewUpdate,
    JobOut,
    ProfileOut,
    SpeakerLabelUpdate,
    TranscriptOut,
)
from ..serializers import interview_detail, interview_summary

router = APIRouter(prefix="/api/interviews", tags=["interviews"])

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
    db.commit()
    db.refresh(a)
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

    applicant = _resolve_applicant(db, applicant_id, applicant_name)

    # Save the audio to local disk under a unique name.
    stored_name = f"{uuid.uuid4().hex}{ext}"
    dest = settings.audio_dir / stored_name
    size = 0
    with dest.open("wb") as f:
        while chunk := await audio.read(1024 * 1024):
            size += len(chunk)
            if size > settings.max_upload_bytes:
                f.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(413, "Audio file exceeds the size limit.")
            f.write(chunk)

    parsed_date = _parse_date(interview_date)
    interview = Interview(
        applicant_id=applicant.id,
        title=(title or "").strip() or None,
        interview_date=parsed_date,
        audio_filename=audio.filename,
        audio_path=str(dest),
    )
    db.add(interview)
    db.commit()
    db.refresh(interview)

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
    query = db.query(Interview).options(*_QUERY_LOAD).join(Applicant)

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
    if interview.audio_path:
        Path(interview.audio_path).unlink(missing_ok=True)
    db.delete(interview)
    db.commit()


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
        transcript.applicant_speaker = payload.applicant_speaker

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
