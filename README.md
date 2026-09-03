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

## Repository Structure

```
├── backend/           → FastAPI backend application
│   ├── app/
│   │   ├── api/routes/       → API endpoint definitions
│   │   ├── core/             → Configuration, settings, utilities
│   │   ├── models/           → Database models
│   │   ├── schemas/          → Pydantic schemas
│   │   ├── services/         → Business logic modules
│   │   │   ├── jd_intelligence/       (Amad)
│   │   │   ├── cv_intelligence/       (Amad)
│   │   │   ├── eligibility/           (Amad)
│   │   │   ├── interview_intelligence/ (Faizan)
│   │   │   └── assessment/            (Faizan)
│   │   ├── integrations/     → External service integrations
│   │   │   ├── llm/          → LLM provider (model agnostic)
│   │   │   ├── stt/          → Speech-to-Text (provider agnostic)
│   │   │   ├── tts/          → Text-to-Speech (provider agnostic)
│   │   │   ├── livekit/      → Real-time audio transport
│   │   │   └── pipecat/      → STT→LLM→TTS orchestration
│   │   ├── db/               → Database configuration
│   │   └── main.py           → Application entry point
│   └── tests/
│
├── frontend/          → Frontend applications
│   ├── candidate/            → Candidate interview UI (Jazib)
│   └── recruiter/            → Recruiter dashboard (Jazib)
│
├── voice_lab/         → Experimental STT/TTS/transliteration sandbox
│
├── shared/            → Shared contracts and sample data
│   ├── contracts/            → JSON integration contracts
│   └── sample_data/          → Test data for development
│
├── docs/              → Documentation
│   ├── architecture/         → System architecture
│   ├── api/                  → API documentation
│   └── project/              → Project overview
│
├── .gitignore
├── README.md
└── LICENSE
```

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

## Current Status

🏗️ **Initial project structure only** — no business logic has been implemented yet.

## Getting Started

1. Clone the repository
2. Copy `backend/.env.example` to `backend/.env` and fill in your values
3. Check each module's README for specific setup instructions
