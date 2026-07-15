"""FastAPI application entrypoint.

Interview Transcription & Applicant Profiling — local-first backend.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import init_db
from .models import InterviewStatus
from .pipeline import runner
from .routers import applicants, interviews, labels

app = FastAPI(title="Interview Transcription & Applicant Profiling", version="0.1.0")

# Local-first: the frontend dev server runs on a different port. In production
# you'd serve the built frontend from the same origin and tighten this.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()


app.include_router(applicants.router)
app.include_router(interviews.router)
app.include_router(labels.router)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "pipeline_backend": "stub" if runner.using_stub() else "ml",
        "real_backend_available": runner.real_backend_available(),
        "profile_extraction_enabled": bool(settings.anthropic_api_key),
        "profile_model": settings.profile_model,
    }


@app.get("/api/meta")
def meta() -> dict:
    """Static options the UI needs (statuses, allowed types)."""
    return {
        "statuses": [s.value for s in InterviewStatus],
        "allowed_audio_extensions": list(settings.allowed_audio_extensions),
    }
