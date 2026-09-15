"""
Adaptive Multimodal AI Interview & Candidate Assessment System

Standalone FastAPI service exposing the JD + CV Intelligence & Eligibility
Engine module (Days 1-5): JD parsing, CV parsing, experience matching, and
eligibility checking. Runs independently of any other module in this repo.

Exception handling: registered once here as global handlers rather than
per-endpoint try/except, since all four pipeline endpoints share the same
three error categories and must respond to each identically. A generic,
non-leaky message is always returned to the client for 500s — the real
error (including any chained root cause, e.g. a wrapped LLMProviderError)
is logged server-side instead, at a severity that distinguishes an external
service failure (ERROR) from a broken internal invariant (CRITICAL).

ValueError's message IS exposed to the client (400): the only ValueErrors
raised in this codebase are the deliberately-written, non-sensitive,
user-actionable "text cannot be empty" messages from the parsers.

Pydantic request validation failures (malformed/incomplete JSON bodies) are
handled entirely by FastAPI's default RequestValidationError behavior
(422) — no custom handler is needed or added for that case.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes.pipeline import router as pipeline_router
from app.services.cv_intelligence.cv_parser import CVParserError
from app.services.jd_intelligence.jd_parser import JDParserError

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Adaptive Multimodal AI Interview & Candidate Assessment System",
    version="0.1.0",
)

app.include_router(pipeline_router)


@app.get("/")
async def root():
    return {"message": "API is running"}


_GENERIC_SERVER_ERROR_MESSAGE = "An internal error occurred while processing the request."


@app.exception_handler(ValueError)
def handle_value_error(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(JDParserError)
def handle_jd_parser_error(request: Request, exc: JDParserError) -> JSONResponse:
    logger.error("JD parsing failed: %s", exc, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": _GENERIC_SERVER_ERROR_MESSAGE})


@app.exception_handler(CVParserError)
def handle_cv_parser_error(request: Request, exc: CVParserError) -> JSONResponse:
    logger.error("CV parsing failed: %s", exc, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": _GENERIC_SERVER_ERROR_MESSAGE})


@app.exception_handler(AssertionError)
def handle_assertion_error(request: Request, exc: AssertionError) -> JSONResponse:
    # An AssertionError here means one of our own invariants broke (e.g. the
    # experience-results length-mismatch guard in check_eligibility) — a
    # genuine internal bug, not an external service failure. Logged at
    # CRITICAL so it's immediately distinguishable from a JD/CV parser
    # failure when scanning logs later.
    logger.critical("Internal invariant violated: %s", exc, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": _GENERIC_SERVER_ERROR_MESSAGE})
