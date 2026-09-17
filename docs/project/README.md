# Project Overview

## Adaptive Multimodal AI Interview & Candidate Assessment System

This project is an **AI-assisted interview and assessment platform**. It screens candidates against a job description, conducts an adaptive voice interview, and stores a real assessment report for a human recruiter.

Setup, environment variables, startup commands, and the demo walkthrough live in the root [README.md](../../README.md). This file is a short project map only.

### Core capabilities

- **JD Intelligence**: Parse job descriptions into structured requirement profiles.
- **CV Intelligence**: Parse candidate resumes into candidate profiles.
- **Eligibility Engine**: Screen candidates before interview.
- **Adaptive voice interview**: LiveKit transport, local Whisper STT, Interview Intelligence, ElevenLabs TTS (local fallback).
- **Assessment & scoring**: Persist `InterviewResult` from genuine evaluations only.
- **Recruiter dashboard**: Pipeline, jobs, assessment reports, in-memory sessions, derived analytics.

### Key principles

- AI assists, humans decide — final hiring decisions remain with the recruiter.
- No facial analysis or autonomous hiring decisions.
- `MockInterviewBridge` is not used on the real interview path.

### Team

| Member | Responsibilities |
|--------|------------------|
| **Amad** | JD Intelligence, CV Intelligence, Eligibility Engine |
| **Faizan** | Interview Intelligence, question generation, adaptive difficulty, assessment, gap analysis |
| **Jazib** | Voice interview (LiveKit + worker + STT/TTS), candidate UI, recruiter dashboard |

### Progress tracker

| Phase | Status |
|-------|--------|
| Shared contracts | Complete |
| JD / CV / eligibility | Complete |
| Application persistence + 48h invitations | Complete |
| Recruiter dashboard (live API) | Complete |
| Candidate apply + interview UI | Complete |
| Real Interview Intelligence on the voice path | Complete |
| Assessment persistence (`InterviewResult`) | Complete |
| LiveKit Agents worker + Whisper STT + ElevenLabs TTS | Complete |
| Authentication | Out of scope for the current demo |
| Phase 6 demo documentation / polish | Complete |

### Architecture documentation

See [docs/architecture/](../architecture/) for the original system diagram. Runtime commands and current providers are documented in the root README.

### API documentation

Interactive OpenAPI: `http://localhost:8000/docs` when the backend is running. See also [docs/api/](../api/).
