"""
LiveKit Agents worker entrypoint for real-time voice interviews.

This file is meant to be run as its own process, separate from uvicorn
(e.g. `python -m app.agents.worker dev`).
"""
from dotenv import load_dotenv
load_dotenv()
import logging

from livekit import agents
from livekit.agents import AgentServer, AgentSession, JobProcess, JobRequest
from livekit.plugins import silero

from app.agents.interview_agent import InterviewAgent
from app.agents.room_ownership import (
    owner_job_id,
    release_room,
    room_already_has_interview_agent,
    try_claim_room,
)
from app.integrations.stt.factory import warmup_whisper_model
from app.integrations.tts.factory import warmup_blocking_providers

logger = logging.getLogger(__name__)

# livekit-agents 1.8.1 AgentSession defaults turn_detection to
# inference.TurnDetector() when the key is omitted. That ML end-of-turn
# detector can commit a user turn before local faster-whisper has produced
# FINAL_TRANSCRIPT. "vad" is a supported TurnDetectionMode in this version
# (livekit.agents.voice.turn.TurnDetectionMode). FINAL_TRANSCRIPT is only
# yielded after Whisper finishes, so endpointing min_delay is 0 — extra delay
# after the transcript would add idle time to every turn.
INTERVIEW_TURN_HANDLING = {
    "turn_detection": "vad",
    "endpointing": {
        "mode": "fixed",
        # FINAL_TRANSCRIPT is only emitted after Whisper finishes, so a
        # post-transcript min_delay would add idle time to every turn.
        "min_delay": 0.0,
        "max_delay": 8.0,
    },
    "interruption": {
        "enabled": False,
        "mode": "vad",
        "discard_audio_if_uninterruptible": True,
    },
    "preemptive_generation": {"enabled": False},
}


def prewarm_interview_process(proc: JobProcess) -> None:
    """Load Silero VAD, TTS providers, and Whisper before the job connects.

    This runs in the job process/thread during initialization, not on the in-room
    event loop, so ONNX/SSL/ElevenLabs/Whisper construction cannot stall LiveKit
    pings during a candidate turn. HTTP clients are created later on the job's
    own event loop so they cannot be reused across loops.
    """
    proc.userdata["vad"] = silero.VAD.load()
    warmup_blocking_providers()
    warmup_whisper_model()


server = AgentServer(
    setup_fnc=prewarm_interview_process,
    initialize_process_timeout=60.0,
)


def create_interview_agent_session(vad=None) -> AgentSession:
    if vad is None:
        vad = silero.VAD.load()
    return AgentSession(
        vad=vad,
        turn_handling=INTERVIEW_TURN_HANDLING,
        user_away_timeout=60.0,
    )


async def handle_interview_job_request(req: JobRequest) -> None:
    """Accept at most one active interview agent job per LiveKit room."""
    room_name = (req.room.name or "").strip()
    job_id = req.id
    if not try_claim_room(room_name, job_id):
        logger.warning(
            "Rejecting duplicate interview job room=%s job=%s existing_owner=%s",
            room_name,
            job_id,
            owner_job_id(room_name),
        )
        await req.reject()
        return
    await req.accept()


@server.rtc_session(on_request=handle_interview_job_request)
async def entrypoint(ctx: agents.JobContext) -> None:
    vad = ctx.proc.userdata.get("vad")
    if vad is None:
        logger.warning("VAD missing from job userdata; loading before connect")
        vad = silero.VAD.load()
        ctx.proc.userdata["vad"] = vad

    room_name = (ctx.room.name or "").strip()
    job_id = ctx.job.id
    agent = InterviewAgent()

    async def _on_job_shutdown(_reason: str = "") -> None:
        await agent.aclose()
        release_room(room_name, job_id)

    ctx.add_shutdown_callback(_on_job_shutdown)
    await ctx.connect()

    local_identity = ""
    try:
        local_identity = ctx.room.local_participant.identity or ""
    except Exception:
        local_identity = ""
    if room_already_has_interview_agent(ctx.room, local_identity):
        logger.warning(
            "Standing down duplicate interview agent already present in room %s job=%s",
            room_name,
            job_id,
        )
        return

    # InterviewAgent node overrides call whisper_local / Interview Intelligence /
    # TTSProviderFactory. VAD here is what stt_node uses as the end-of-turn signal.
    session = create_interview_agent_session(vad=vad)
    await session.start(
        room=ctx.room,
        agent=agent,
    )


if __name__ == "__main__":
    agents.cli.run_app(server)
