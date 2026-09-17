"""
Main FastAPI application entrypoint.
"""
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.api.routes.apply import router as apply_router
from app.api.routes.auth import router as auth_router
from app.api.routes.voice import router as voice_router
from app.api.routes.pipeline import router as pipeline_router
from app.api.routes.dashboard import router as dashboard_router
from app.integrations.livekit.config import LiveKitConfig
from app.integrations.livekit.service import LiveKitService
from app.services.voice.service import VoiceInterviewService
from app.services.cv_intelligence.cv_parser import CVParserError
from app.services.cv_intelligence.extraction import CVExtractionError
from app.services.jd_intelligence.jd_parser import JDParserError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

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

app.include_router(auth_router, prefix="/api/v1")
app.include_router(voice_router, prefix="/api/v1")
app.include_router(apply_router, prefix="/api/v1")
app.include_router(pipeline_router)
app.include_router(dashboard_router, prefix="/api/v1/dashboard")


@app.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.app_name}


_GENERIC_SERVER_ERROR_MESSAGE = "An internal error occurred while processing the request."
_CV_ANALYSIS_UNAVAILABLE = (
    "We could not analyze your CV right now. Please try again in a moment."
)
_JD_ANALYSIS_UNAVAILABLE = (
    "We could not parse this job description right now. Please try again in a moment."
)


@app.exception_handler(ValueError)
def handle_value_error(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(JDParserError)
def handle_jd_parser_error(request: Request, exc: JDParserError) -> JSONResponse:
    logger.error("JD parsing failed: %s", exc, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": _JD_ANALYSIS_UNAVAILABLE})


@app.exception_handler(CVParserError)
def handle_cv_parser_error(request: Request, exc: CVParserError) -> JSONResponse:
    logger.error("CV parsing failed: %s", exc, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": _CV_ANALYSIS_UNAVAILABLE})


@app.exception_handler(CVExtractionError)
def handle_cv_extraction_error(request: Request, exc: CVExtractionError) -> JSONResponse:
    logger.error("CV extraction failed: %s", exc, exc_info=exc)
    return JSONResponse(
        status_code=400,
        content={
            "detail": "We could not read text from the uploaded CV. Please upload a text-based PDF or DOCX file."
        },
    )


@app.exception_handler(AssertionError)
def handle_assertion_error(request: Request, exc: AssertionError) -> JSONResponse:
    logger.critical("Internal invariant violated: %s", exc, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": _GENERIC_SERVER_ERROR_MESSAGE})


@app.exception_handler(Exception)
def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled server error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": _GENERIC_SERVER_ERROR_MESSAGE})