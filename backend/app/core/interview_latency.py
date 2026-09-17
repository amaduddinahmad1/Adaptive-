"""Structured interview-turn latency logs. No secrets, tokens, or CV contents."""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

_PREFIX = "[INTERVIEW_LATENCY]"


def log_interview_latency(
    session: str,
    stage: str,
    elapsed_ms: Optional[float] = None,
    **fields: Any,
) -> None:
    parts = [f"{_PREFIX} session={session}", f"stage={stage}"]
    if elapsed_ms is not None:
        parts.append(f"elapsed_ms={elapsed_ms:.0f}")
    for key, value in fields.items():
        if value is None:
            continue
        parts.append(f"{key}={value}")
    logger.info(" ".join(parts))


class TurnLatency:
    """Monotonic timer from candidate-turn commit until next-question playout."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.t0 = time.perf_counter()

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self.t0) * 1000.0

    def mark(self, stage: str, **fields: Any) -> float:
        elapsed_ms = self.elapsed_ms()
        log_interview_latency(self.session_id, stage, elapsed_ms, **fields)
        return elapsed_ms

    def total(self) -> float:
        elapsed_ms = self.elapsed_ms()
        log_interview_latency(
            self.session_id,
            "turn_complete",
            elapsed_ms,
            total_turn_ms=f"{elapsed_ms:.0f}",
        )
        logger.info("%s session=%s total_turn_ms=%.0f", _PREFIX, self.session_id, elapsed_ms)
        return elapsed_ms
