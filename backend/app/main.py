"""
Main FastAPI application entrypoint.
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.routes.voice import router as voice_router
from app.integrations.livekit.config import LiveKitConfig
from app.integrations.livekit.service import LiveKitService
from app.services.voice.service import VoiceInterviewService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

app = FastAPI(
    title=settings.app_name,
    description="Backend API for the Adaptive Multimodal AI Interview System.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Application-scoped voice service so sessions persist across requests.
app.state.voice_service = VoiceInterviewService(
    livekit_service=LiveKitService(
        LiveKitConfig(
            url=settings.livekit_url,
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
        )
    )
)

app.include_router(voice_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.app_name}
