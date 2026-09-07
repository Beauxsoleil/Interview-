"""Background job runner.

A simple thread-pool task runner is enough for v1: transcription is slow and
must not block the request, but we don't need a full queue system yet. Each job
runs in its own thread with its own DB session and writes progress back to the
`jobs` table so the UI can poll.
"""
from __future__ import annotations

import json
import logging
import traceback
from concurrent.futures import ThreadPoolExecutor

from interview_pipeline_core import runner
from interview_pipeline_core.merge import render_text

from .database import SessionLocal
from .models import Interview, Job, JobState, Profile, SyncDraft, Transcript
from .pipeline import profile as profile_pipeline
from .pipeline_runtime import pipeline_config

logger = logging.getLogger("interview.jobs")

# Transcription is CPU/GPU-bound; keep concurrency low to avoid oversubscription.
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pipeline")


def enqueue_transcription(interview_id: int) -> int:
    """Create one queued job per interview, avoiding duplicate work."""
    db = SessionLocal()
    try:
        active = (
            db.query(Job)
            .filter(
                Job.interview_id == interview_id,
                Job.kind == "transcribe",
                Job.state.in_([JobState.QUEUED.value, JobState.RUNNING.value]),
            )
            .order_by(Job.created_at.desc())
            .first()
        )
        if active:
            return active.id
        job = Job(interview_id=interview_id, kind="transcribe", state=JobState.QUEUED.value)
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id
    finally:
        db.close()

    _executor.submit(_run_transcription_job, job_id)
    return job_id


def recover_interrupted_jobs() -> int:
    """Requeue the newest unfinished transcription for each interview on startup."""
    db = SessionLocal()
    recovered: list[int] = []
    try:
        active = (
            db.query(Job)
            .filter(
                Job.kind == "transcribe",
                Job.state.in_([JobState.QUEUED.value, JobState.RUNNING.value]),
            )
            .order_by(Job.interview_id, Job.created_at.desc())
            .all()
        )
        seen: set[int] = set()
        for job in active:
            if job.interview_id in seen:
                job.state = JobState.ERROR.value
                job.stage = "superseded"
                job.error = "Superseded by a newer processing job."
                continue
            seen.add(job.interview_id)
            job.state = JobState.QUEUED.value
            job.stage = "recovered after restart"
            job.progress = 0
            job.error = None
            recovered.append(job.id)
        db.commit()
    finally:
        db.close()
    for job_id in recovered:
        _executor.submit(_run_transcription_job, job_id)
    return len(recovered)


def _update_job(db, job: Job, **fields) -> None:
    for k, v in fields.items():
        setattr(job, k, v)
    db.add(job)
    db.commit()


def _run_transcription_job(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None:
            return
        interview = db.get(Interview, job.interview_id)
        if interview is None or not interview.audio_path:
            _update_job(db, job, state=JobState.ERROR.value, error="No audio file.")
            return

        _update_job(db, job, state=JobState.RUNNING.value, stage="starting", progress=1)

        def on_progress(pct: int, stage: str) -> None:
            _update_job(db, job, progress=pct, stage=stage)

        result = runner.run_pipeline(
            interview.audio_path,
            config=pipeline_config(),
            on_progress=on_progress,
        )

        turns = result["turns"]
        speakers: list[str] = result["speakers"]
        # Heuristic default: in a 2-speaker interview the applicant is usually
        # the second speaker to talk (the interviewer opens). Reviewers can
        # correct this in the UI.
        applicant_speaker = speakers[1] if len(speakers) > 1 else (
            speakers[0] if speakers else None
        )

        # Upsert transcript and invalidate every output derived from an older
        # revision. A reviewer must explicitly approve the new transcript.
        transcript = interview.transcript or Transcript(interview_id=interview.id)
        transcript.language = result.get("language")
        transcript.segments_json = json.dumps(turns)
        transcript.text = render_text(turns)
        transcript.speaker_labels_json = json.dumps({})
        transcript.applicant_speaker = applicant_speaker
        transcript.revision = (transcript.revision or 0) + 1
        transcript.reviewed_at = None
        transcript.edited_at = None
        if interview.profile:
            db.delete(interview.profile)
        draft = db.query(SyncDraft).filter_by(interview_id=interview.id).first()
        if draft:
            db.delete(draft)
        db.add(transcript)
        db.commit()

        _update_job(db, job, state=JobState.DONE.value, progress=100, stage="done")
    except Exception as e:  # noqa: BLE001
        logger.error("Job %s failed: %s\n%s", job_id, e, traceback.format_exc())
        try:
            job = db.get(Job, job_id)
            if job:
                _update_job(
                    db,
                    job,
                    state=JobState.ERROR.value,
                    error="Processing failed. Review server logs, then retry.",
                    stage="error",
                )
        except Exception:
            pass
    finally:
        db.close()


def _extract_and_save_profile(db, interview_id: int) -> Profile:
    interview = db.get(Interview, interview_id)
    if interview is None or interview.transcript is None:
        raise ValueError("Interview has no transcript to profile.")

    transcript = interview.transcript
    if not transcript.reviewed_at:
        raise ValueError("Transcript must be reviewed before profile extraction.")
    labels = json.loads(transcript.speaker_labels_json or "{}")
    applicant = transcript.applicant_speaker or "the applicant"
    applicant_role = labels.get(applicant, applicant)

    profile_data, model = profile_pipeline.extract_profile(
        transcript.text, applicant_role
    )

    profile = interview.profile or Profile(interview_id=interview.id)
    profile.data_json = profile_data.model_dump_json()
    profile.model = model
    profile.source_transcript_revision = transcript.revision
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def run_profile_extraction(interview_id: int) -> Profile:
    """Synchronous profile (re)extraction — used by the manual endpoint."""
    db = SessionLocal()
    try:
        return _extract_and_save_profile(db, interview_id)
    finally:
        db.close()
