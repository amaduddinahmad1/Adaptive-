# Adaptive Multimodal AI Interview & Candidate Assessment System

## Project Purpose

An AI-powered platform that automates candidate screening, conducts adaptive voice interviews, and generates comprehensive assessment reports — while keeping final hiring decisions with the human recruiter.

## High-Level Workflow

```
Recruiter creates job → JD Analysis → Requirement Profile
    → Candidate applies (CV + form) → AI Screening → Eligibility
    → Interview Link → LiveKit → Pipecat → Interview LLM
    → Adaptive Interview → Skill Scores + Gap Analysis
    → Assessment Report → Recruiter Dashboard
```

## Team Ownership

| Team Member | Responsibilities |
|-------------|------------------|
| **Amad** | JD Intelligence, CV Intelligence, Eligibility Engine |
| **Faizan** | Interview Intelligence, Question Generation, CV Claim Verification, Adaptive Difficulty, Assessment & Scoring, Gap Analysis |
| **Jazib** | Voice Interview (LiveKit + Pipecat), STT, TTS, Candidate Interview UI, Recruiter Dashboard, Final Report UI |

## Current Status

🏗️ **Day 1 Complete** — Voice foundation, candidate interview UI, and recruiter dashboard shell implemented.

### What's Implemented (Day 1)

| Component | Status | Details |
|-----------|--------|---------|
| STT Abstraction | ✅ Foundation | Abstract provider + mock implementation |
| TTS Abstraction | ✅ Foundation | Abstract provider + mock implementation |
| LiveKit Foundation | ✅ Foundation | Config + service structure (SDK pending) |
| Pipecat Foundation | ✅ Foundation | Pipeline + interview bridge structure |
| Voice Service | ✅ Foundation | Session management, pipeline coordination |
| Voice Schemas | ✅ Complete | Session, STT, TTS schemas with enums |
| API Routes | ✅ Foundation | Voice session CRUD endpoints |
| Candidate UI | ✅ Complete | Premium interview interface with mock demo |
| Recruiter Dashboard | ✅ Complete | Dashboard shell with mock data |
| Backend Tests | ✅ Basic | Schema, STT, TTS, voice service tests |
| Documentation | ✅ Complete | Architecture, API, voice docs |

### What's Mocked

- STT transcription (returns placeholder text)
- TTS synthesis (returns placeholder audio bytes)
- LiveKit room/token management (placeholder methods)
- Pipecat pipeline processing (structural foundation)
- Interview Intelligence (mock bridge interface)
- Session storage (in-memory dict)
- Frontend API calls (mock data in hooks/services)

### What's NOT Implemented

- Real STT/TTS provider integrations
- LiveKit SDK integration
- Pipecat SDK integration
- JD Intelligence (Amad)
- CV Intelligence (Amad)
- Eligibility Engine (Amad)
- Interview Intelligence (Faizan)
- Assessment & Scoring (Faizan)
- Database persistence
- Authentication
- Real-time WebSocket updates

## Repository Structure

```
├── backend/           → FastAPI backend application
│   ├── app/
│   │   ├── api/routes/       → API endpoint definitions
│   │   ├── core/             → Configuration, settings, utilities
│   │   ├── models/           → Database models
│   │   ├── schemas/          → Pydantic schemas (voice, STT, TTS)
│   │   ├── services/         → Business logic modules
│   │   │   ├── voice/        → Voice interview coordination (Jazib) ★
│   │   │   ├── jd_intelligence/       (Amad — not started)
│   │   │   ├── cv_intelligence/       (Amad — not started)
│   │   │   ├── eligibility/           (Amad — not started)
│   │   │   ├── interview_intelligence/ (Faizan — not started)
│   │   │   └── assessment/            (Faizan — not started)
│   │   ├── integrations/     → External service integrations
│   │   │   ├── llm/          → LLM provider (model agnostic)
│   │   │   ├── stt/          → Speech-to-Text (provider agnostic) ★
│   │   │   ├── tts/          → Text-to-Speech (provider agnostic) ★
│   │   │   ├── livekit/      → Real-time audio transport ★
│   │   │   └── pipecat/      → STT→LLM→TTS orchestration ★
│   │   ├── db/               → Database configuration
│   │   └── main.py           → Application entry point
│   └── tests/                → Backend tests ★
│
├── frontend/          → Frontend applications
│   ├── candidate/            → Candidate interview UI (Vite + React) ★
│   └── recruiter/            → Recruiter dashboard (Vite + React) ★
│
├── voice_lab/         → Experimental STT/TTS/transliteration sandbox
│
├── shared/            → Shared contracts and sample data
│   ├── contracts/            → JSON integration contracts
│   └── sample_data/          → Test data for development
│
├── docs/              → Documentation ★
│   ├── architecture/         → System + voice architecture
│   ├── api/                  → API documentation
│   └── project/              → Project overview
│
├── .gitignore
├── README.md
└── LICENSE
```

Items marked with ★ were created/updated in Day 1.

## Shared Contracts

> **Important**: The JSON files in `shared/contracts/` define the **integration boundaries** between team members. Any changes to contract schemas must be discussed and agreed upon by all affected team members before merging.

| Contract | Producer | Consumer |
|----------|----------|----------|
| `candidate_profile.json` | Amad (CV Intelligence) | Amad (Eligibility), Faizan (Interview) |
| `requirement_profile.json` | Amad (JD Intelligence) | Amad (Eligibility), Faizan (Interview) |
| `eligibility_result.json` | Amad (Eligibility) | Jazib (Interview Flow) |
| `interview_plan.json` | Faizan (Interview Intelligence) | Jazib (Voice Pipeline) |
| `interview_question.json` | Faizan (Interview Intelligence) | Jazib (Voice Pipeline) |
| `answer_evaluation.json` | Faizan (Interview Intelligence) | Faizan (Assessment) |
| `skill_scores.json` | Faizan (Assessment) | Jazib (Report UI) |
| `gap_analysis.json` | Faizan (Assessment) | Jazib (Report UI) |
| `assessment_report.json` | Faizan (Assessment) | Jazib (Recruiter Dashboard) |

## Architecture Principles

- **LiveKit** = Real-time audio transport / session layer
- **Pipecat** = Orchestration layer (STT → LLM → TTS pipeline)
- **Interview LLM** = Intelligence layer (question generation, evaluation)
- STT, TTS, and LLM integrations are **provider/model agnostic**
- **No facial analysis** or autonomous hiring decisions
- Final hiring decisions remain with the **human recruiter**

## Getting Started

### Backend
```bash
cd backend
# Create virtual environment
python -m venv venv
# Activate (Windows)
venv\Scripts\activate
# Install dependencies (when requirements are finalized)
# pip install -r requirements.txt
# Copy and configure environment
cp .env.example .env
# Run tests
# python -m pytest tests/
```

### Frontend — Candidate
```bash
cd frontend/candidate
npm install
npm run dev     # Development server
npm run build   # Production build
```

### Frontend — Recruiter
```bash
cd frontend/recruiter
npm install
npm run dev     # Development server
npm run build   # Production build
```

## Day 2 Planning

### Jazib
- Integrate real LiveKit SDK for room/token management
- Evaluate and select STT provider (test in voice_lab first)
- Evaluate and select TTS provider (test in voice_lab first)
- Begin Pipecat SDK integration for pipeline orchestration
- Connect candidate UI to real backend API

### Amad
- Begin JD Intelligence implementation
- Begin CV Intelligence implementation
- Define eligibility criteria schema

### Faizan
- Begin Interview Intelligence implementation
- Implement InterviewBridge interface
- Define question generation strategy
