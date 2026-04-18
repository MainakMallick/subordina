"""FastAPI application entrypoint."""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Subordinate", version="0.1.0")


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}
