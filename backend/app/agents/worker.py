"""
LiveKit Agents worker entrypoint for real-time voice interviews.

This file is meant to be run as its own process, separate from uvicorn
(e.g. `python -m app.agents.worker dev`).
"""
from dotenv import load_dotenv
load_dotenv()
from livekit import agents
from livekit.agents import AgentServer, AgentSession
from livekit.plugins import silero

from app.agents.interview_agent import InterviewAgent

server = AgentServer()


@server.rtc_session()
async def entrypoint(ctx: agents.JobContext) -> None:
    await ctx.connect()

    # InterviewAgent node overrides call whisper_local / MockInterviewBridge /
    # TTSProviderFactory. VAD here is what stt_node uses as the end-of-turn signal.
    session = AgentSession(
        vad=silero.VAD.load(),
    )
    await session.start(
        room=ctx.room,
        agent=InterviewAgent(),
    )


if __name__ == "__main__":
    agents.cli.run_app(server)
