"""
FINN — FastAPI Main Application
"""

import math
import json
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import ALLOWED_ORIGINS
from backend.routers import push, pull, chat


def sanitize_floats(obj: Any) -> Any:
    """Recursively replace NaN/Inf with None so JSON serialization doesn't fail."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: sanitize_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_floats(v) for v in obj]
    return obj


class SafeJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        return json.dumps(sanitize_floats(content), ensure_ascii=False).encode("utf-8")

app = FastAPI(
    title="FINN API",
    description="Financial Investment Agent — ENAM Holdings Build Challenge",
    version="1.0.0",
    default_response_class=SafeJSONResponse,
)

# CORS — allow frontend dev server and deployed frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(push.router)
app.include_router(pull.router)
app.include_router(chat.router)


@app.get("/health")
async def health():
    import os
    gemini_key_detected = bool(
        os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or os.getenv("GOOGLE_GENAI_API_KEY")
    )
    detected_var = None
    if os.getenv("GEMINI_API_KEY"):
        detected_var = "GEMINI_API_KEY"
    elif os.getenv("GOOGLE_API_KEY"):
        detected_var = "GOOGLE_API_KEY"
    elif os.getenv("GOOGLE_GENAI_API_KEY"):
        detected_var = "GOOGLE_GENAI_API_KEY"

    return {
        "status": "ok",
        "service": "FINN API",
        "version": "1.2.0",
        "has_gemini_key": gemini_key_detected,
        "gemini_env_var": detected_var,
        "cors_origins": ALLOWED_ORIGINS,
    }


@app.get("/")
async def root():
    return {
        "service": "FINN",
        "description": "Financial Investment Agent",
        "docs": "/docs",
        "endpoints": {
            "push_digest": "/push/digest",
            "push_alerts": "/push/alerts",
            "push_prices": "/push/prices",
            "pull_research": "/pull/research/{ticker}",
            "chat": "/chat",
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
