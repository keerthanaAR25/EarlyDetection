"""
FastAPI application entry point (Phase 19).

Usage:
    uvicorn backend.main:app --reload
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

from backend.api.routes import router  # noqa: E402

app = FastAPI(
    title="Early-AML-Warning-System API",
    description="Real-data-backed API for the formation-stage AML early-warning system. "
                "Every endpoint reads from the database populated by scripts/load_database.py "
                "— no fabricated responses.",
    version="0.1.0",
)

cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/")
def root():
    return {"message": "Early-AML-Warning-System API. See /docs for interactive API documentation."}
