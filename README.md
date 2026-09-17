# Adaptive Multimodal AI Interview & Candidate Assessment System

An AI-assisted hiring platform that screens candidates against a job description, invites eligible applicants to a live voice interview, and produces an assessment report for a human recruiter.

Final hiring decisions remain with the recruiter. The system does not perform facial analysis and does not make autonomous hire/reject decisions.

## Architecture overview

```
Recruiter creates job → JD Intelligence → persisted JobPosting
    → Candidate applies (CV + form) → CV Intelligence → Eligibility Engine
    → Application persisted
    → If eligible: 48-hour invitation token + SMTP email
    → Candidate opens /interview/{token}
    → Voice session (LiveKit) + voice worker (STT → Interview Intelligence → TTS)
    → Adaptive interview + answer evaluation
    → Final assessment persisted as InterviewResult
    → Recruiter dashboard / pipeline / assessment report
```

| Layer | Role in this repo |
|-------|-------------------|
| FastAPI backend | Apply, dashboard, voice session API, JD/CV/eligibility, assessment persistence |
| PostgreSQL + Alembic | Candidates, jobs, applications, invitation tokens, interview results |
| LiveKit | Real-time audio transport |
| Voice worker (`app.agents.worker`) | LiveKit Agents process: local Whisper STT, HTTP bridge to Interview Intelligence, ElevenLabs TTS with local fallback |
| Interview Intelligence | Interview plan, questions, adaptive control, answer evaluation, final report |
| Candidate UI | Application form + invitation interview flow |
| Recruiter UI | Jobs, pipeline, assessment, sessions, analytics |

`MockInterviewBridge` exists for tests only. The real interview path uses `InterviewIntelligenceBridge` inside the backend voice service and `HttpInterviewBridge` inside the LiveKit agent.

## Repository structure

```
├── backend/                 FastAPI app, Alembic, pytest
│   ├── app/main.py          API entrypoint
│   ├── app/agents/worker.py Voice worker entrypoint
│   ├── alembic/             Database migrations
│   ├── .env.example         Environment variable placeholders
│   └── tests/
├── frontend/candidate/      Candidate apply + interview UI (Vite, port 5173)
├── frontend/recruiter/      Recruiter dashboard (Vite, port 5174)
├── shared/contracts/        JSON integration contracts
├── docs/                    Architecture and API notes
└── voice_lab/               Experimental STT/TTS sandbox (not required for the demo)
```

## Prerequisites

- Python 3 with `pip` (this repo has been run with Python 3.13)
- Node.js + npm
- PostgreSQL
- ffmpeg on `PATH` (required by local Whisper STT for compressed audio)
- A LiveKit server (local OSS `livekit-server --dev`, or LiveKit Cloud)
- External accounts as needed: Google Gemini, ElevenLabs, Gmail SMTP (App Password)

## Local URLs and ports

These come from the project configuration, not invented values:

| Service | Command / config | URL |
|---------|------------------|-----|
| Backend API | Uvicorn default port 8000 | http://localhost:8000 |
| Health check | `GET /health` | http://localhost:8000/health |
| OpenAPI | FastAPI automatic docs | http://localhost:8000/docs |
| Candidate UI | `frontend/candidate/vite.config.js` `port: 5173` | http://localhost:5173 |
| Recruiter UI | `frontend/recruiter/vite.config.js` `port: 5174` | http://localhost:5174 |
| LiveKit (local tests) | tests use `localhost:7880` | `ws://127.0.0.1:7880` typical for OSS `--dev` |

The candidate Vite proxy and recruiter Vite proxy forward `/api` to `http://localhost:8000`.

## 1. PostgreSQL

Create an empty database for this project. The app and Alembic both read `DATABASE_URL` from `backend/.env`.

This repo uses SQLAlchemy 2 with `psycopg` (psycopg3). A typical URL is:

```text
postgresql+psycopg://USER:PASSWORD@localhost:5432/DBNAME
```

Do not commit the real URL.

## 2. Backend setup

```bash
cd backend
python -m venv venv
```

Windows:

```bash
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

macOS / Linux:

```bash
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `backend/.env` with real values. Never commit `.env`.

## 3. Alembic migrations

From `backend/`, with `DATABASE_URL` set:

```bash
cd backend
alembic upgrade head
```

Current migration head in this repo is `f13c7ba3c4f3` (invitation token columns on `applications`). Fresh databases apply `22e51fce5f78` then `f13c7ba3c4f3`.

## 4. Environment variables

Copy `backend/.env.example` only. Placeholders, never secrets:

| Variable | Required for | Notes |
|----------|--------------|--------|
| `DATABASE_URL` | Apply, dashboard, invitations, assessment persistence | PostgreSQL SQLAlchemy URL |
| `GEMINI_API_KEY` | JD parse, CV parse, eligibility semantic matching, answer evaluation | Primary LLM |
| `GEMINI_MODEL` | Optional | Defaults to `gemini-3.1-flash-lite` |
| `XAI_API_KEY` / `GROQ_API_KEY` | Optional | Opt-in LLM fallbacks; Gemini stays primary |
| `LIVEKIT_URL` | Real voice interview | Must match the LiveKit server |
| `LIVEKIT_API_KEY` | Real voice interview | Must match the LiveKit server |
| `LIVEKIT_API_SECRET` | Real voice interview | Must match the LiveKit server |
| `ELEVENLABS_API_KEY` | Spoken agent audio | Primary TTS |
| `ELEVENLABS_VOICE_ID` | Spoken agent audio | ElevenLabs voice |
| `STT_PROVIDER` | Optional | Default `whisper_local` |
| `WHISPER_MODEL_SIZE` | Optional | Default `small` |
| `TTS_PROVIDER` | Optional | Default `elevenlabs` (local MMS-TTS fallback on failure) |
| `BACKEND_API_BASE_URL` | Optional | Worker → API; default `http://localhost:8000/api/v1` |
| `SMTP_EMAIL` | Invitation email | Gmail address |
| `SMTP_APP_PASSWORD` | Invitation email | Gmail **App Password**, not the account password |
| `SMTP_HOST` | Invitation email | Default `smtp.gmail.com` |
| `SMTP_PORT` | Invitation email | Default `587` |
| `FRONTEND_BASE_URL` | Invitation links | **Must** be an absolute `http://` or `https://` URL. Local candidate UI: `http://localhost:5173` |
| `INTERVIEW_LINK_PATH_TEMPLATE` | Invitation links | Default `/interview/{token}` |

If LiveKit credentials are missing, the backend issues mock tokens and a real browser interview cannot connect.

If SMTP or `FRONTEND_BASE_URL` is missing, eligible applications still persist, but `invitation_sent` is false and no email is sent.

Frontend optional override: `VITE_API_BASE_URL`. Candidate defaults to `http://localhost:8000`. Recruiter defaults to `''` and uses the Vite `/api` proxy.

## 5. Start the stack

Use **separate terminals**. Working directory for backend commands is `backend/`.

### LiveKit

This repository does not vendor a LiveKit binary. A local OSS server in `--dev` mode is the verified local setup:

```bash
livekit-server --dev
```

On Windows the same flag is used on the downloaded binary, for example `.\livekit-server.exe --dev`.

Point `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET` at that server (or at LiveKit Cloud). Tests in this repo use `localhost:7880`.

### Backend

```bash
cd backend
python -m uvicorn app.main:app --reload
```

### Voice worker

```bash
cd backend
python -m app.agents.worker dev
```

This is a separate process from Uvicorn. It loads `backend/.env`, connects to LiveKit, and talks to Interview Intelligence over HTTP (`BACKEND_API_BASE_URL`).

### Candidate frontend

```bash
cd frontend/candidate
npm install
npm run dev
```

### Recruiter frontend

```bash
cd frontend/recruiter
npm install
npm run dev
```

## How the product flow works

### Candidate application

1. Recruiter publishes a job (`http://localhost:5174/jobs/new`). JD Intelligence parses the JD and stores a `JobPosting.parsed_profile`.
2. Candidate opens `http://localhost:5173` (or `/apply`).
3. Candidate selects an open job, fills identity / salary / availability, and uploads a PDF or DOCX CV (max 10 MB).
4. Backend extracts CV text, parses a candidate profile, runs the eligibility engine, and persists `Candidate` + `Application`.

### Invitation flow

- If `overall_eligible` is true, the backend creates a one-time interview token that expires in 48 hours and attempts SMTP.
- The email contains `FRONTEND_BASE_URL` + `INTERVIEW_LINK_PATH_TEMPLATE` (default `/interview/{token}`).
- The resolve API maps the token to an application and **does not return the token**.
- Invalid, expired, ineligible, or already-completed invitations are rejected.

### Interview

1. Candidate opens `/interview/{token}`.
2. After instructions, the UI creates a voice session for that application and calls start.
3. Start initializes **real** Interview Intelligence (not `MockInterviewBridge`), creates a LiveKit room, and returns a join token.
4. The voice worker joins, greets, and asks generated questions.
5. Local Whisper STT transcribes answers. Interview Intelligence evaluates them (Gemini) and selects the next adaptive question. TTS speaks the reply.
6. Ending the session (candidate, silence timeout, or end-intent) persists a real `InterviewResult` when genuine evaluations exist. Scores are never fabricated.

### Assessment and recruiter review

- Recruiter dashboard: `http://localhost:5174/`
- Pipeline / screening: `/pipeline` and `/pipeline/:applicationId`
- Assessment report: `/pipeline/:applicationId/assessment` (empty until an `InterviewResult` exists)
- Jobs: `/jobs`
- In-memory live sessions: `/sessions` (only while the backend process still holds the session)
- Analytics: `/analytics` (counts from persisted applications/jobs only; PDF metrics that the API does not return stay empty)

## Testing

Backend (from `backend/`):

```bash
cd backend
python -m pytest -q
```

Candidate:

```bash
cd frontend/candidate
npm run lint
npm run build
```

Recruiter:

```bash
cd frontend/recruiter
npm run lint
npm run build
```

There is no separate compile command beyond these.

## Demo data

There is **no seed script** and this repo does not fabricate candidate scores.

Create demo data through the product:

1. Recruiter → New Job Posting → publish (requires Gemini).
2. Candidate → apply with a real text-based PDF/DOCX (requires Gemini).
3. If eligible and SMTP is configured, use the emailed 48-hour link.
4. Complete a real interview (LiveKit + worker + STT/TTS + Gemini for evaluation).
5. Recruiter opens the application and assessment report.

### Safe reset

Do not delete rows on a database that holds real user data.

For a dedicated local demo database only:

1. Drop and recreate that PostgreSQL database.
2. `cd backend` and run `alembic upgrade head`.
3. Recreate jobs and applications through the UI.

Voice sessions are in-memory. Restarting Uvicorn clears `/sessions` without touching PostgreSQL.

If SMTP is not configured, an eligible application still has a token in `applications.interview_token`. An operator can build `FRONTEND_BASE_URL` + `/interview/{token}` from that column. Do not display tokens in the recruiter UI.

## External services

| Service | Needed for | If missing |
|---------|------------|------------|
| PostgreSQL | Almost all product APIs | Apply/dashboard/interview persistence fail |
| Gemini | JD/CV parse, eligibility matching, answer evaluation | Job publish and apply fail; interview evaluation fails |
| LiveKit | Real-time interview audio | Start may return mock tokens; browser cannot join a real room |
| Voice worker | Agent speech in the room | Candidate connects but hears no interviewer |
| faster-whisper (local) | STT | Worker cannot transcribe; ffmpeg needed for compressed audio |
| ElevenLabs | Primary TTS | Local MMS-TTS fallback may still speak |
| Gmail SMTP | Invitation email | Application persists; `invitation_sent` is false |

## Common troubleshooting

| Symptom | What to check |
|---------|----------------|
| Open roles fail to load | Backend not on port 8000; `DATABASE_URL`; `alembic upgrade head` |
| Apply fails analyzing CV | `GEMINI_API_KEY`; upload a text-based PDF/DOCX, not a scanned image |
| Eligible but no email | `SMTP_EMAIL`, `SMTP_APP_PASSWORD`, `FRONTEND_BASE_URL` as absolute `http(s)` URL |
| Invitation invalid/expired | Token is one-time and 48 hours; already completed interviews cannot reuse it |
| Interview start fails | Backend, LiveKit, worker; LiveKit env vars must be non-empty and matching |
| No spoken questions | Worker process; `BACKEND_API_BASE_URL`; ElevenLabs or local TTS fallback |
| Recruiter job publish times out / 500 | Gemini reachable; recruiter LLM calls wait up to 180s |
| Assessment empty | Interview must produce real answer evaluations; scores are never invented |
| `/sessions` empty after refresh | Voice sessions are in-memory on the API process |

## Team ownership

| Team member | Area |
|-------------|------|
| Amad | JD Intelligence, CV Intelligence, Eligibility Engine |
| Faizan | Interview Intelligence, evaluation, adaptive difficulty, assessment |
| Jazib | Voice (LiveKit, STT, TTS, worker), candidate UI, recruiter UI |

## Shared contracts

JSON files in `shared/contracts/` are integration boundaries. Changes should be agreed by the affected owners before merging.

## Architecture principles

- LiveKit transports audio. It does not score candidates.
- Interview Intelligence generates questions, evaluates answers, and builds the report.
- STT/TTS/LLM integrations are provider-shaped behind factories. The **current** interview STT is local Whisper; current primary TTS is ElevenLabs.
- No facial analysis. No autonomous hiring decision persistence.
