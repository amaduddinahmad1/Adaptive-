# Voice Lab

## Purpose

**voice_lab** is an **experimental sandbox** for benchmarking and evaluating Speech-to-Text (STT), Text-to-Speech (TTS), and Roman Urdu/Urdu transliteration solutions **before** they are integrated into the production system.

## Important Rules

- This directory is **NOT** part of the production codebase.
- Experiments here are **isolated** from `backend/app/integrations/`.
- Once a provider/model is selected and validated, the production integration goes into `backend/app/integrations/stt/`, `backend/app/integrations/tts/`, etc.
- Do **NOT** import from `voice_lab/` in any production code.

## Structure

```
voice_lab/
├── stt/              # STT provider experiments
│   ├── samples/      # Audio samples for testing
│   └── test_stt.py   # STT benchmarking scripts
├── tts/              # TTS provider experiments
│   ├── outputs/      # Generated audio outputs
│   └── test_tts.py   # TTS benchmarking scripts
├── transliteration/  # Roman Urdu ↔ Urdu experiments
│   └── test_transliteration.py
├── test_sentences.txt
├── requirements.txt  # Experimental deps only
└── README.md
```

## Owner

**Jazib** — Voice Interview, LiveKit, Pipecat, STT, TTS
