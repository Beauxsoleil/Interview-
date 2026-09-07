"""FastAPI application entrypoint.

Interview Transcription & Applicant Profiling — local-first backend.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from interview_pipeline_core import runner

from .config import settings
from .database import init_db
from .jobs import recover_interrupted_jobs
from .models import InterviewStatus
from .pipeline_runtime import pipeline_config
from .routers import applicants, interviews, labels, sync
from .firestore_sync import firebase_configured

# Create tables eagerly at import so the app works under uvicorn, tests, and
# any other entrypoint alike (create_all is idempotent and cheap on SQLite).
init_db()

@asynccontextmanager
async def lifespan(_app: FastAPI):
    recover_interrupted_jobs()
    yield


app = FastAPI(
    title="Interview Transcription & Applicant Profiling",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_allowed_origins),
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), geolocation=(), microphone=()"
    if not request.url.path.startswith(("/docs", "/redoc", "/openapi.json")):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; media-src 'self' blob:; connect-src 'self'"
        )
    if settings.enable_hsts:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


app.include_router(applicants.router)
app.include_router(interviews.router)
app.include_router(labels.router)
app.include_router(sync.router)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "pipeline_backend": (
            "stub" if runner.using_stub(pipeline_config()) else "ml"
        ),
        "real_backend_available": runner.real_backend_available(),
        "profile_extraction_enabled": bool(settings.gemini_api_key),
        "profile_model": settings.profile_model,
        "pibase_sync_enabled": firebase_configured(),
    }


@app.get("/api/meta")
def meta() -> dict:
    """Static options the UI needs (statuses, allowed types)."""
    return {
        "statuses": [s.value for s in InterviewStatus],
        "allowed_audio_extensions": list(settings.allowed_audio_extensions),
        "max_upload_bytes": settings.max_upload_bytes,
        "max_audio_duration_seconds": settings.max_audio_duration_seconds,
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
