# API Documentation

Interactive OpenAPI is served by FastAPI when the backend is running:

```
http://localhost:8000/docs
```

Base path for versioned product routes:

```
http://localhost:8000/api/v1
```

Health:

```
GET http://localhost:8000/health
```

## Current routers

These are the routers mounted in `backend/app/main.py`. Request/response fields are defined by the FastAPI/Pydantic models; use `/docs` as the source of truth.

| Prefix | Module | Purpose |
|--------|--------|---------|
| `/api/v1/jobs`, `/api/v1/jobs/{job_id}/apply`, `/api/v1/interview-invitations/resolve` | `app.api.routes.apply` | Public jobs list, candidate apply, invitation resolve |
| `/api/v1/voice/...` | `app.api.routes.voice` | Voice session create/start/end/status, next-question, candidate response |
| `/api/v1/dashboard/...` | `app.api.routes.dashboard` | Recruiter candidates, jobs, applications, interview results |
| `/analyze-jd`, `/analyze-cv`, `/match-experience`, `/check-eligibility`, `/submit-application` | `app.api.routes.pipeline` | Standalone JD/CV/eligibility helpers (recruiter job preview uses `/analyze-jd`) |

Error bodies use FastAPI's `{"detail": "..."}` shape. Invitation resolve never returns the raw token. Unhandled server errors return a generic detail string and do not include stack traces.

## Historical Day 1 notes

The voice session examples below remain valid for the voice router. Later product routes (apply, dashboard, invitation resolve) are not listed in the original Day 1 examples; use `/docs`.

## Voice session endpoints

### Create Voice Session

```
POST /api/v1/voice/sessions
```

**Request Body:**
```json
{
  "application_id": 1,
  "language": "en"
}
```

The session is bound to an existing eligible `Application`.

---

### Get Voice Session

```
GET /api/v1/voice/sessions/{session_id}
```

---

### Start Interview

```
POST /api/v1/voice/sessions/{session_id}/start
```

Returns LiveKit join fields (`livekit_url`, `token`, `room_name`, `identity`) when credentials are configured.

---

### End Interview

```
POST /api/v1/voice/sessions/{session_id}/end
```

Persists a real `InterviewResult` when genuine answer evaluations exist.

---

### Get Session Status

```
GET /api/v1/voice/sessions/{session_id}/status
```

### Next question / candidate response

Used by the LiveKit worker (`HttpInterviewBridge`):

```
GET  /api/v1/voice/sessions/{session_id}/next-question
POST /api/v1/voice/sessions/{session_id}/response
```

## API design notes

- JSON request/response bodies
- Versioned product endpoints under `/api/v1/`
- No authentication layer in the current demo
- Recruiter and candidate UIs proxy or call `http://localhost:8000`
