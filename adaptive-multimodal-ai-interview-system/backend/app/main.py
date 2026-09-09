"""
Adaptive Multimodal AI Interview & Candidate Assessment System

Standalone FastAPI service exposing the JD + CV Intelligence & Eligibility
Engine module (Days 1-5): JD parsing, CV parsing, experience matching, and
eligibility checking. Runs independently of any other module in this repo.
"""

from fastapi import FastAPI

from app.api.routes.pipeline import router as pipeline_router

app = FastAPI(
    title="Adaptive Multimodal AI Interview & Candidate Assessment System",
    version="0.1.0",
)

app.include_router(pipeline_router)


@app.get("/")
async def root():
    return {"message": "API is running"}
