# Interview Transcription & Applicant Profiling

A local-first web app for turning recorded interview audio into diarized,
speaker-labeled transcripts and structured applicant profiles.

> **Sensitive data:** this app stores health, legal, and demographic
> information. It is built local-only by default — audio and the SQLite database
> live on local disk, there is no third-party analytics, and the only outbound
> network call is to the Claude API for profile extraction (only when you
> configure an API key).

---

## What it does

1. **Upload** interview audio (`mp3` / `wav` / `m4a`).
2. **Diarize** with `pyannote.audio` to segment by speaker.
3. **Transcribe** with Whisper (or `whisperx` for word-level timestamps and
   better speaker/text alignment).
4. **Merge** into a labeled transcript (`Speaker 1: …`, `Speaker 2: …`).
5. **Rename** speakers after the fact (e.g. → *Interviewer* / *Applicant*).
6. **Extract** a structured applicant profile with the Claude API — into a JSON
   schema first, then rendered as a readable summary card. Fields the transcript
   doesn't cover are flagged *"not mentioned"* rather than guessed.
7. **Organize** interviews by applicant, status, and custom labels, with a
   sortable/filterable list and full-text search across transcripts and profiles.

### Runs without a GPU

The transcription/diarization pipeline is pluggable. When the heavy ML
dependencies aren't installed, the app falls back to a **stub backend** that
produces a realistic sample interview — so you can validate the whole flow
(upload → job → transcript → speaker rename → profile extraction) end-to-end
before setting up Whisper/pyannote. The header shows which backend is active.

---

## Architecture

```
backend/   FastAPI + SQLAlchemy (SQLite) + a thread-pool job runner
  app/
    config.py            settings (local-only defaults)
    models.py            Applicant, Interview, Transcript, Profile, Label, Job
    schemas.py           API + structured-profile schemas
    jobs.py              background transcription + profile jobs
    pipeline/
      diarization.py     pyannote wrapper (lazy import)
      transcription.py   whisperx / whisper wrapper (lazy import)
      merge.py           speaker <-> text merge logic
      stub.py            no-dependency sample backend
      runner.py          backend selection + orchestration
      profile.py         Claude structured-output extraction
    routers/             applicants, interviews, labels
frontend/  React + Vite + Tailwind
  src/
    components/          list, detail, upload, transcript, profile card
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
| `ANTHROPIC_API_KEY` | Enables Claude profile extraction. Without it, transcription still works. |
| `PROFILE_MODEL` | Claude model for extraction (default `claude-opus-4-8`). |
| `HF_TOKEN` | HuggingFace token — required by pyannote to download the diarization model. |
| `PIPELINE_BACKEND` | `auto` (default) uses ML if installed, else stub; `stub` forces the sample backend. |
| `WHISPER_MODEL` | `tiny`…`large-v3` (default `base`). |
| `DEFAULT_NUM_SPEAKERS` | Optional hint; leave blank to auto-detect. |

Install the ML stack (heavy; GPU recommended):

```bash
pip install -r requirements-ml.txt
```

With `whisperx` + `pyannote.audio` installed and `HF_TOKEN` set, uploads run
real diarization and transcription. The health badge in the UI switches from
*stub pipeline* to *ML pipeline*.

---

## Build order

The project follows the intended incremental build order:

1. ✅ Audio upload + transcription (pipeline validated end-to-end via stub)
2. ✅ Diarization + speaker-merge logic
3. ✅ Applicant/interview data model + list UI
4. ✅ LLM profile extraction (structured JSON → summary card)
5. ✅ Labels, statuses, search/filter
6. ✅ Transcript UI: speaker rename + playback synced to text

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

---

## Notes & limitations (v1)

- Job runner is a single-worker thread pool — fine for one machine; swap for a
  real queue (Celery/RQ) if you need horizontal scale.
- No auth — intended for local/single-operator use. Add authentication before
  putting this on a shared network given the sensitivity of the data.
- The stub backend's transcript is clearly synthetic sample content; it exists
  to exercise the pipeline, not to stand in for real transcription.
