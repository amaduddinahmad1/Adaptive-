"""Standalone TTS/STT smoke checks (English).

Run from the backend directory (or anywhere; this file adds backend to sys.path):

    python scripts/test_stt_tts.py
    python scripts/test_stt_tts.py path/to/sample.wav

Loads backend/.env if present. Does not change any project files outside this folder.
WAV outputs are written to scripts/test_output/.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPTS_DIR / "test_output"

# Set this to a short local audio file (WAV/MP3/etc.), or pass the path as argv[1].
SAMPLE_AUDIO_PATH = ""

TTS_SENTENCES = [
    "How many years of experience do you have with FastAPI?",
    "Tell me about a past project you are proud of.",
    "Why did you choose that database for the backend?",
]

_INVALID_ELEVENLABS_KEY = "sk_invalid_test_key_do_not_use"
_FALLBACK_TTS_INDEX = 0  # first sentence: force ElevenLabs failure → local_tts


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _ensure_import_path() -> None:
    backend = str(BACKEND_ROOT)
    if backend not in sys.path:
        sys.path.insert(0, backend)


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str

    def summary_line(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {self.name}: {self.detail}"


def _write_wav(path: Path, audio_data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(audio_data)


def _looks_like_wav(audio_data: bytes) -> bool:
    return len(audio_data) > 44 and audio_data[:4] == b"RIFF"


def _clear_tts_cache(provider_canonical_name: str) -> None:
    from app.integrations.tts.factory import TTSProviderFactory

    TTSProviderFactory._instances.pop(provider_canonical_name, None)


def _restore_env(key: str, previous: str | None) -> None:
    if previous is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = previous


async def _run_tts_check(
    index: int,
    text: str,
    *,
    force_invalid_elevenlabs: bool,
) -> CheckResult:
    from app.integrations.tts.factory import TTSProviderFactory
    from app.schemas.tts import TTSConfig

    label = f"TTS {index + 1}"
    out_path = OUTPUT_DIR / f"tts_{index + 1}.wav"
    config = TTSConfig(provider="elevenlabs_tts", language="en", output_format="wav")

    previous_key = os.environ.get("ELEVENLABS_API_KEY")
    previous_voice = os.environ.get("ELEVENLABS_VOICE_ID")
    try:
        if force_invalid_elevenlabs:
            os.environ["ELEVENLABS_API_KEY"] = _INVALID_ELEVENLABS_KEY
            if not (os.environ.get("ELEVENLABS_VOICE_ID") or "").strip():
                os.environ["ELEVENLABS_VOICE_ID"] = "invalid_voice_id_for_fallback_test"
            _clear_tts_cache("elevenlabs")
            expected_provider = "local_fallback"
            label = f"{label} (ElevenLabs invalid key → local_tts fallback)"
        else:
            _clear_tts_cache("elevenlabs")
            expected_provider = "elevenlabs"
            label = f"{label} (elevenlabs_tts)"

        result = await TTSProviderFactory.synthesize_with_fallback(text, config)
        _write_wav(out_path, result.audio_data)

        wav_ok = _looks_like_wav(result.audio_data) and out_path.is_file()
        provider_ok = result.provider == expected_provider
        passed = wav_ok and provider_ok and bool(result.audio_data)

        parts = [
            f"provider={result.provider}",
            f"bytes={len(result.audio_data)}",
            f"file={out_path}",
            f"{result.processing_time_ms:.0f}ms",
        ]
        if not provider_ok:
            parts.append(f"expected provider={expected_provider}")
        if not wav_ok:
            parts.append("output is not a non-empty WAV")
        return CheckResult(name=label, passed=passed, detail="; ".join(parts))
    except Exception as exc:
        return CheckResult(name=label, passed=False, detail=f"{type(exc).__name__}: {exc}")
    finally:
        if force_invalid_elevenlabs:
            _restore_env("ELEVENLABS_API_KEY", previous_key)
            _restore_env("ELEVENLABS_VOICE_ID", previous_voice)
            _clear_tts_cache("elevenlabs")


async def _run_stt_check(audio_path: Path) -> CheckResult:
    from app.integrations.stt.factory import STTProviderFactory
    from app.schemas.stt import STTConfig

    name = "STT 1 (whisper_local)"
    if not audio_path.is_file():
        return CheckResult(
            name=name,
            passed=False,
            detail=(
                f"audio file not found: {audio_path}. "
                "Set SAMPLE_AUDIO_PATH in this script or pass the path as argv[1]."
            ),
        )

    try:
        audio_data = audio_path.read_bytes()
        provider = STTProviderFactory.get_provider("whisper_local")
        config = STTConfig(provider="whisper_local", language="en")
        result = await provider.transcribe(audio_data, config)
        transcript = (result.text or "").strip()
        passed = bool(transcript)
        print()
        print("STT transcript:")
        print(transcript or "(empty)")
        print()
        detail = (
            f"provider={result.provider}; "
            f"chars={len(transcript)}; "
            f"confidence={result.confidence:.2f}; "
            f"{result.processing_time_ms:.0f}ms; "
            f"source={audio_path}"
        )
        if not passed:
            detail += "; empty transcript"
        return CheckResult(name=name, passed=passed, detail=detail)
    except Exception as exc:
        return CheckResult(name=name, passed=False, detail=f"{type(exc).__name__}: {exc}")


def _parse_args() -> Path:
    parser = argparse.ArgumentParser(description="Smoke-test TTS factory and local Whisper STT.")
    parser.add_argument(
        "audio",
        nargs="?",
        default=SAMPLE_AUDIO_PATH,
        help="Path to a short local audio file for STT (overrides SAMPLE_AUDIO_PATH).",
    )
    args = parser.parse_args()
    raw = (args.audio or "").strip()
    path = Path(raw) if raw else Path("")
    if raw and not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path


async def _main() -> int:
    _configure_stdio()
    _ensure_import_path()
    _load_env_file(BACKEND_ROOT / ".env")

    audio_path = _parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    checks: list[CheckResult] = []
    for index, sentence in enumerate(TTS_SENTENCES):
        checks.append(
            await _run_tts_check(
                index,
                sentence,
                force_invalid_elevenlabs=(index == _FALLBACK_TTS_INDEX),
            )
        )
    checks.append(await _run_stt_check(audio_path))

    print("=" * 60)
    print("STT / TTS smoke check summary")
    print("=" * 60)
    for check in checks:
        print(check.summary_line())
    print("=" * 60)

    failed = sum(1 for check in checks if not check.passed)
    print(f"Result: {len(checks) - failed}/{len(checks)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
