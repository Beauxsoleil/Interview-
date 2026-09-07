# Interview Transcription & Applicant Profiling

A private, single-recruiter web app for turning recorded interview audio into
diarized, speaker-labeled transcripts, structured applicant profiles, and
human-reviewed updates to the APPLEMDT/PIBASE applicant tracker.

> **Sensitive data:** this app stores health, legal, and demographic
> information. Audio, the SQLite database, extraction drafts, and sync audit logs
> remain on the host. The only application-level outbound connections are Gemini
> profile extraction and the explicitly confirmed Firebase Admin writes described
> below. Never expose this service directly to the public internet; the production
> deployment is reachable only through the recruiter's Tailscale network.

---

## What it does

1. **Upload** interview audio (`mp3` / `wav` / `m4a`).
2. **Diarize** with `pyannote.audio` to segment by speaker.
3. **Transcribe** with Whisper (or `whisperx` for word-level timestamps and
   better speaker/text alignment).
4. **Merge** into a labeled transcript (`Speaker 1: …`, `Speaker 2: …`).
5. **Rename** speakers after the fact (e.g. → *Interviewer* / *Applicant*).
6. **Extract** a structured applicant profile with the Gemini API — into a JSON
   schema first, then rendered as a readable summary card. Fields the transcript
   doesn't cover are flagged *"not mentioned"* rather than guessed.
7. **Organize** interviews by applicant, status, and custom labels, with a
   sortable/filterable list and full-text search across transcripts and profiles.
8. **Review and sync** proposed applicant fields into PIBASE. Existing values are
   shown beside Gemini's proposal, every structured field requires approval, and
   the recruiter summary is added as a new note rather than overwriting history.

### Runs without a GPU

The transcription/diarization pipeline is pluggable. When the heavy ML
dependencies aren't installed, the app falls back to a **stub backend** that
produces a realistic sample interview — so you can validate the whole flow
(upload → job → transcript → speaker rename → profile extraction) end-to-end
before setting up Whisper/pyannote. The header shows which backend is active.

---

## Architecture

```
interview-pipeline-core/
  pyproject.toml           installable, FastAPI/DB-independent audio pipeline
  src/interview_pipeline_core/
    diarization.py         pyannote wrapper (lazy import)
    transcription.py       whisperx / whisper wrapper (lazy import)
    merge.py               speaker <-> text merge logic
    stub.py                no-dependency sample backend
    runner.py              backend selection + orchestration
backend/   FastAPI + SQLAlchemy (SQLite) + a thread-pool job runner
  app/
    config.py            settings (local-only defaults)
    models.py            interviews, profiles, jobs, sync drafts/audit logs
    schemas.py           API + structured-profile schemas
    jobs.py              background transcription + profile jobs
    firestore_sync.py    privileged server-only PIBASE client
    sync_schemas.py      PIBASE extraction/review request schemas
    pipeline/
      profile.py         Gemini structured-output extraction
      sync_profile.py    Firestore-shaped Gemini extraction + 429 backoff
    routers/             applicants, interviews, labels, reviewed PIBASE sync
frontend/  React + Vite + Tailwind
  src/
    components/          list, transcript/profile, and PIBASE review flow
    lib/api.js           API client
```

**Data model:** each interview is one record tying together applicant,
interview date, audio file, transcript, and profile. Applicants can have
multiple interviews over time; interviews carry a status (Pending Review /
Priority / Approved / Rejected) and any number of custom labels.

---

## Setup

### 1. Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # optional — edit to enable profile extraction / real ML
uvicorn app.main:app --reload --port 8000
```

The API is now at `http://localhost:8000` (docs at `/docs`). With no `.env`
changes it runs the **stub pipeline** and profile extraction is off.

`requirements.txt` installs `../interview-pipeline-core` in editable mode. Keep
that directory beside `backend`; do not copy the old pipeline modules back into
the FastAPI package.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173  (proxies /api -> :8000)
```

Open http://localhost:5173 and upload an interview.

---

## Enabling real transcription & profile extraction

Edit `backend/.env`:

| Variable | Purpose |
| --- | --- |
| `GEMINI_API_KEY` | Enables Gemini profile extraction. Without it, transcription still works. |
| `PROFILE_MODEL` | Gemini model for extraction (default `gemini-3.6-flash`). |
| `HF_TOKEN` | HuggingFace token — required by pyannote to download the diarization model. |
| `PIPELINE_BACKEND` | `auto` (default) uses ML if installed, else stub; `stub` forces the sample backend. |
| `WHISPER_MODEL` | `tiny`…`large-v3` (default `base`). |
| `TRANSCRIPTION_CHUNK_SECONDS` | Bounded transcription window size (default `300`, or five minutes). |
| `TRANSCRIPTION_OVERLAP_SECONDS` | Context on each side of a window (default `8` seconds). |
| `TRANSCRIPTION_BATCH_SIZE` | WhisperX VAD batch size (default `1` for variable-length safety). |
| `DEFAULT_NUM_SPEAKERS` | Optional hint; leave blank to auto-detect. |
| `GOOGLE_APPLICATION_CREDENTIALS` | Absolute path to the PIBASE Firebase service-account JSON. Never place it in this repository. |
| `FIRESTORE_PROJECT_ID` | Required credential/project check; defaults to `pi-base-a3a09`. |

Install the ML stack (heavy; GPU recommended):

```bash
pip install -r requirements-ml.txt
```

With `whisperx` + `pyannote.audio` installed and `HF_TOKEN` set, uploads run
real diarization and transcription. The health badge in the UI switches from
*stub pipeline* to *ML pipeline*.

### Enabling reviewed PIBASE synchronization

Generate a dedicated Firebase service-account JSON for `pi-base-a3a09`. Store it
outside the Git checkout with permissions limited to the service user, then set
its absolute path in `GOOGLE_APPLICATION_CREDENTIALS`. The browser never receives
this credential: all matching and writes happen through FastAPI.

The service account bypasses client Firestore rules. Treat possession of the file
as administrative database access. Do not put the JSON in `.env`, a browser
bundle, shell history, logs, either repository, or a shared folder.

The recruiter workflow is deliberately two-stage:

1. Prepare a PIBASE review and select an existing applicant or create a new one.
2. Compare current and proposed values, approve individual fields, review the
   additive note, identify the approver, and confirm.

Archived applicants cannot be synchronized accidentally. The UI requires an
explicit unarchive choice and clears PIBASE's modern and legacy archive metadata.
Each confirmed operation is recorded in the local `sync_logs` SQLite table.

### Production on Oracle + Tailscale

Production runs as `interview-sync.service` under the unprivileged `ubuntu` user.
The service binds to the VM's Tailscale address on port 8000; it must not bind to
a public interface. The unit should use:

- `WorkingDirectory=/home/ubuntu/Interview-/backend`
- `EnvironmentFile=/home/ubuntu/Interview-/backend/.env`
- the virtual environment's `uvicorn`
- `UMask=0077` so newly created local data is private by default

After a code update, reinstall `backend/requirements.txt`, rebuild `frontend/`
with `npm run build`, restart the service, and verify `/api/health` through
Tailscale. The `pibase_sync_enabled` health field is true only when the configured
credential is a valid Firebase service-account JSON file for the expected
Firestore project.

---

## Build order

The project follows the intended incremental build order:

1. ✅ Audio upload + transcription (pipeline validated end-to-end via stub)
2. ✅ Diarization + speaker-merge logic
3. ✅ Applicant/interview data model + list UI
4. ✅ LLM profile extraction (structured JSON → summary card)
5. ✅ Labels, statuses, search/filter
6. ✅ Transcript UI: speaker rename + playback synced to text
7. ✅ Shared installable audio pipeline package
8. ✅ Human-reviewed PIBASE synchronization and durable audit log

---

## API overview

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/api/interviews` | Upload audio + create interview (starts a transcription job) |
| `GET` | `/api/interviews` | List with `q`, `status`, `label_id`, `applicant_id`, `sort`, `order` |
| `GET` | `/api/interviews/{id}` | Full detail (transcript + profile + latest job) |
| `PATCH` | `/api/interviews/{id}` | Update title / status / date / labels |
| `PATCH` | `/api/interviews/{id}/speakers` | Rename speakers, mark the applicant |
| `POST` | `/api/interviews/{id}/reprocess` | Re-run transcription |
| `POST` | `/api/interviews/{id}/extract-profile` | (Re)extract the profile |
| `GET` | `/api/interviews/{id}/audio` | Stream the stored audio |
| `GET` | `/api/health` | Which backends are active |
| `POST` | `/api/interviews/{id}/sync/extract` | Extract a PIBASE-shaped review draft; no Firestore write |
| `GET` | `/api/interviews/{id}/sync/candidates` | Search PIBASE applicants by name |
| `POST` | `/api/interviews/{id}/sync/proposal` | Compare proposed fields with the selected record |
| `POST` | `/api/interviews/{id}/sync/confirm` | Add the note and write only explicitly approved fields |
| `GET` | `/api/interviews/{id}/sync/logs` | Read the local sync audit trail |

---

## Notes & limitations (v1)

- Job runner is a single-worker thread pool — fine for one machine; swap for a
  real queue (Celery/RQ) if you need horizontal scale.
- Long recordings are decoded to mono 16 kHz audio and transcribed sequentially
  in five-minute windows with eight seconds of context. Each window owns a
  non-overlapping portion of the timeline, preventing duplicate boundary text.
- Application access is restricted at the network layer with Tailscale for a
  single operator. Do not open port 8000 publicly or treat an obscure URL as an
  authentication control.
- The stub backend's transcript is clearly synthetic sample content; it exists
  to exercise the pipeline, not to stand in for real transcription.
- Firestore name matching uses a small-collection contains scan and returns at
  most 20 candidates. Replace it with a dedicated search index if PIBASE grows
  beyond the intended single-recruiter scale.
