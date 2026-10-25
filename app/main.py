"""Nightjar — one Space serves both the API and the player."""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

# compose and voice read their keys at import, so load .env before them.
# On a Space there is no .env and the secrets are already in the environment.
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from compose import ComposeError, compose
import compose as composer
from voice import VoiceError, ambient, speak

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("nightjar")

APP_NAME = "Vesper"
HERE = os.path.dirname(__file__)
STATIC = os.path.join(HERE, "static")

app = FastAPI(title=APP_NAME)


class ShowRequest(BaseModel):
    material: str = Field(min_length=40, max_length=24000)
    minutes: float = Field(default=3.0, ge=1.0, le=6.0)


class ShowResponse(BaseModel):
    title: str
    mood: str
    script: str
    words: list[dict]
    audio_b64: str
    timing: str


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "gemma": composer.BACKEND == "local" or bool(os.environ.get("OPENROUTER_API_KEY")),
        "gemma_backend": composer.BACKEND,
        "voice": bool(os.environ.get("ELEVENLABS_API_KEY")),
    }


@app.post("/api/show", response_model=ShowResponse)
async def show(req: ShowRequest):
    try:
        written = await compose(req.material, req.minutes)
    except ComposeError as exc:
        raise HTTPException(400, str(exc)) from exc

    try:
        spoken = await speak(written["script"])
    except VoiceError as exc:
        # The script survives even when the voice doesn't. Say which failed.
        raise HTTPException(502, f"The script was written, but {exc}") from exc

    return {**written, **spoken}


@app.get("/api/ambient/{mood}")
async def ambient_bed(mood: str):
    try:
        path = await ambient(mood)
    except VoiceError as exc:
        log.info("No ambient bed: %s", exc)
        raise HTTPException(404, str(exc)) from exc
    return FileResponse(path, media_type="audio/mpeg")


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    return FileResponse(os.path.join(STATIC, "index.html"))