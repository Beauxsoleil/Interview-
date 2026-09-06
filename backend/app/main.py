"""FastAPI application entrypoint.

Interview Transcription & Applicant Profiling — local-first backend.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import init_db
from .models import InterviewStatus
from .pipeline import runner
from .routers import applicants, interviews, labels

# Create tables eagerly at import so the app works under uvicorn, tests, and
# any other entrypoint alike (create_all is idempotent and cheap on SQLite).
init_db()

app = FastAPI(title="Interview Transcription & Applicant Profiling", version="0.1.0")

# Local-first: the frontend dev server runs on a different port. In production
# you'd serve the built frontend from the same origin and tighten this.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(applicants.router)
app.include_router(interviews.router)
app.include_router(labels.router)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "pipeline_backend": "stub" if runner.using_stub() else "ml",
        "real_backend_available": runner.real_backend_available(),
        "profile_extraction_enabled": bool(settings.gemini_api_key),
        "profile_model": settings.profile_model,
    }


@app.get("/api/meta")
def meta() -> dict:
    """Static options the UI needs (statuses, allowed types)."""
    return {
        "statuses": [s.value for s in InterviewStatus],
        "allowed_audio_extensions": list(settings.allowed_audio_extensions),
    }


# Serve the production React bundle from the same origin as the API. API and
# documentation routes above take precedence; all other paths fall back to the
# SPA entrypoint so browser refreshes work with React Router.
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="frontend-assets",
    )

    @app.get("/{frontend_path:path}", include_in_schema=False)
    def frontend(frontend_path: str):
        if frontend_path == "api" or frontend_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")

        requested = (FRONTEND_DIST / frontend_path).resolve()
        if requested.is_relative_to(FRONTEND_DIST) and requested.is_file():
            return FileResponse(requested)
        return FileResponse(FRONTEND_DIST / "index.html")
