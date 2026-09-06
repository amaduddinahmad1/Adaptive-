# System Architecture

## High-Level Pipeline

```
Recruiter
    ↓
Job Description
    ↓
JD Analysis Engine          ← Amad
    ↓
Requirement Profile
    ↓
Candidate Application
    ↓
AI Screening
    ↓
Eligibility Engine           ← Amad
    ↓
Interview Link
    ↓
LiveKit                      ← Jazib (real-time audio transport)
    ↓
Pipecat                      ← Jazib (orchestration: STT → LLM → TTS)
    ↓
Interview LLM                ← Faizan (intelligence layer)
    ↓
Adaptive Interview           ← Faizan
    ↓
Skill Scores + Gap Analysis  ← Faizan
    ↓
Assessment Report            ← Faizan
    ↓
Recruiter Dashboard          ← Jazib
```

## Layer Responsibilities

| Layer | Role | Owner |
|-------|------|-------|
| **LiveKit** | Real-time audio transport / session layer | Jazib |
| **Pipecat** | Orchestration layer (STT → LLM → TTS pipeline, conversation flow) | Jazib |
| **Interview LLM** | Intelligence layer (question generation, evaluation, adaptive difficulty) | Faizan |
| **JD Intelligence** | Job description analysis and requirement extraction | Amad |
| **CV Intelligence** | Resume parsing and candidate profile extraction | Amad |
| **Eligibility Engine** | Candidate screening against job requirements | Amad |
| **Assessment** | Scoring, gap analysis, and final report generation | Faizan |

## Design Principles

- **Provider/model agnostic**: STT, TTS, and LLM integrations must not be locked to a single provider.
- **Human-in-the-loop**: Final hiring decisions remain with the human recruiter.
- **No facial analysis**: Computer vision / facial emotion analysis is NOT part of the current implementation.
- **Separation of concerns**: voice_lab is experimental and separate from production integrations.
- **Observable indicators only**: Use behavioral indicators (speech clarity, response articulation) not psychological labels.

## Detailed Architecture

For voice-specific architecture, see [voice_architecture.md](./voice_architecture.md).
