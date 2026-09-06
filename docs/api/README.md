# API Documentation

> **Status**: Day 1 — Voice session endpoints defined (foundation only).

## Base URL

```
http://localhost:8000/api/v1
```

## Voice Session Endpoints

### Create Voice Session

```
POST /api/v1/voice/sessions
```

**Request Body:**
```json
{
  "candidate_id": "string",
  "job_id": "string",
  "language": "en"
}
```

**Response:**
```json
{
  "session_id": "uuid",
  "candidate_id": "string",
  "job_id": "string",
  "interview_status": "PENDING",
  "connection_status": "DISCONNECTED",
  "language": "en",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

---

### Get Voice Session

```
GET /api/v1/voice/sessions/{session_id}
```

**Response:** Same schema as creation response.

---

### Start Interview

```
POST /api/v1/voice/sessions/{session_id}/start
```

**Response:**
```json
{
  "status": "ok",
  "session_id": "uuid",
  "message": "Interview started"
}
```

---

### End Interview

```
POST /api/v1/voice/sessions/{session_id}/end
```

**Response:**
```json
{
  "status": "ok",
  "session_id": "uuid",
  "message": "Interview ended"
}
```

---

### Get Session Status

```
GET /api/v1/voice/sessions/{session_id}/status
```

**Response:**
```json
{
  "session_id": "uuid",
  "interview_status": "IN_PROGRESS",
  "connection_status": "CONNECTED",
  "current_question_id": "string | null",
  "current_question": "string | null"
}
```

## Planned Endpoints (Not Yet Implemented)

### Job Description Endpoints (Amad)
- `POST /api/v1/jobs` — Create job with description
- `GET /api/v1/jobs` — List jobs
- `GET /api/v1/jobs/{job_id}` — Get job details
- `GET /api/v1/jobs/{job_id}/requirements` — Get requirement profile

### Candidate Endpoints (Amad)
- `POST /api/v1/candidates` — Register candidate
- `POST /api/v1/candidates/{id}/cv` — Upload CV
- `GET /api/v1/candidates/{id}/profile` — Get parsed profile
- `POST /api/v1/candidates/{id}/eligibility` — Check eligibility

### Interview Intelligence Endpoints (Faizan)
- `POST /api/v1/interviews/{session_id}/evaluate` — Evaluate answer
- `GET /api/v1/interviews/{session_id}/next-question` — Get next question
- `GET /api/v1/interviews/{session_id}/plan` — Get interview plan

### Assessment Endpoints (Faizan)
- `GET /api/v1/assessments/{session_id}` — Get assessment report
- `GET /api/v1/assessments/{session_id}/scores` — Get skill scores
- `GET /api/v1/assessments/{session_id}/gaps` — Get gap analysis

### LiveKit Token Endpoints (Jazib)
- `POST /api/v1/voice/token` — Generate LiveKit room token

## API Design Principles

- RESTful conventions with consistent naming
- JSON request/response bodies
- Versioned endpoints (`/api/v1/`)
- Consistent error response format:
  ```json
  {
    "error": "error_code",
    "message": "Human-readable message",
    "details": {}
  }
  ```
- Authentication: TBD (JWT planned)
- Rate limiting: TBD
