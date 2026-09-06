# Project Overview

## Adaptive Multimodal AI Interview & Candidate Assessment System

This project builds an **AI-powered interview and assessment platform** that automates candidate screening, conducts adaptive voice interviews, and generates comprehensive assessment reports for recruiters.

### Core Capabilities

- **JD Intelligence**: Analyze job descriptions to extract structured requirement profiles.
- **CV Intelligence**: Parse candidate resumes to build candidate profiles.
- **Eligibility Engine**: Screen candidates against job requirements before interview.
- **Adaptive Voice Interview**: Conduct real-time voice interviews with adaptive question difficulty.
- **Assessment & Scoring**: Generate skill scores, gap analysis, and comprehensive reports.
- **Recruiter Dashboard**: Present assessment results for human decision-making.

### Key Principles

- AI assists, humans decide — final hiring decisions remain with the recruiter.
- Provider/model agnostic integrations for STT, TTS, and LLM.
- Shared contracts define integration boundaries between team members.
- Observable behavioral indicators only — no psychological labels.
- No facial analysis or autonomous hiring decisions.

### Team

| Member | Responsibilities |
|--------|------------------|
| **Amad** | JD Intelligence, CV Intelligence, Eligibility Engine |
| **Faizan** | Interview Intelligence, Question Generation, Adaptive Difficulty, Assessment, Gap Analysis |
| **Jazib** | Voice Interview (LiveKit + Pipecat), STT, TTS, Candidate UI, Recruiter Dashboard |

### Progress Tracker

| Phase | Status |
|-------|--------|
| Project Structure | ✅ Complete |
| Shared Contracts | ✅ Complete |
| Voice Foundation (Jazib Day 1) | ✅ Complete |
| Candidate Interview UI | ✅ Complete |
| Recruiter Dashboard Shell | ✅ Complete |
| JD Intelligence (Amad) | ⬜ Not Started |
| CV Intelligence (Amad) | ⬜ Not Started |
| Eligibility Engine (Amad) | ⬜ Not Started |
| Interview Intelligence (Faizan) | ⬜ Not Started |
| Assessment & Scoring (Faizan) | ⬜ Not Started |
| Real STT/TTS Integration | ⬜ Not Started |
| Real LiveKit Integration | ⬜ Not Started |
| Real Pipecat Integration | ⬜ Not Started |
| Database Persistence | ⬜ Not Started |
| Authentication | ⬜ Not Started |

### Architecture Documentation

See [docs/architecture/](../architecture/) for detailed system and voice architecture documentation.

### API Documentation

See [docs/api/](../api/) for endpoint documentation.
