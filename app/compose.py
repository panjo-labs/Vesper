"""
Gemma writes the show.

Two jobs, one call: turn the material into something written to be *spoken*,
and decide which of three moods the screen should wear.

The mood is chosen from a fixed list. Gemma never returns colour values. A
model improvising hex codes produces mud often enough that you'd ship it
without noticing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re

import httpx

log = logging.getLogger("nightjar.compose")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# Set GEMMA_LOCAL_URL to run Gemma on your own machine instead, e.g. Ollama at
# http://localhost:11434/v1/chat/completions. Then your reading never leaves
# the laptop and no key is needed. The weights are open; that's the point.
LOCAL_URL = os.environ.get("GEMMA_LOCAL_URL", "").strip()
URL = LOCAL_URL or OPENROUTER_URL
BACKEND = "local" if LOCAL_URL else "openrouter"
# Several open-weight models, tried in order. The free pool is shared with
# everyone on OpenRouter, so any single model can be congested at the moment a
# judge clicks your link. One name here is a single point of failure.
MODELS = [m.strip() for m in os.environ.get(
    "GEMMA_MODELS",
    "gemma4:e4b" if LOCAL_URL else
    "google/gemma-4-26b-a4b-it:free,google/gemma-4-31b-it:free"
).split(",") if m.strip()]
API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

MOODS = ("tideline", "deepfield", "ember")

SYSTEM = """You write a short night-time audio show for one tired listener.

Write for the ear, not the eye. That means:
- Short sentences. No lists, no headings, no bullet points, no markdown.
- No numbers written as digits. Write "about forty" not "~40".
- No URLs, no citations, no "according to the article".
- Speak to the listener as "you". Be warm but not chirpy. Never apologise.
- Open by saying how much there is. Close by stopping, not by summarising.
- If the material is thin or unreadable, say so plainly and keep it short.
- Never state a fact that is not in the material. If you are unsure, say the
  source was unclear. Inventing detail is the only unforgivable error here.

Target length: about {words} words.

Also choose exactly one mood for the screen:
- "deepfield" for research, science, engineering, anything technical
- "ember" for news, politics, conflict, anything heated
- "tideline" for everything else, or a mix

Return JSON only, no markdown fence:
{{"mood": "...", "title": "...", "script": "..."}}

The title is a short phrase under nine words, lowercase except names, no
punctuation at the end. It names the pile, like "four things you saved today"."""


class ComposeError(RuntimeError):
    pass


def _coerce(raw: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Models sometimes wrap JSON in a sentence. Take the outermost object.
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not m:
            raise ComposeError("Gemma did not return JSON.")
        data = json.loads(m.group(0))

    script = str(data.get("script", "")).strip()
    if len(script.split()) < 20:
        raise ComposeError("Gemma returned too little to read aloud.")

    mood = str(data.get("mood", "")).strip().lower()
    if mood not in MOODS:
        log.warning("Unknown mood %r from model; falling back to tideline.", mood)
        mood = "tideline"

    title = str(data.get("title", "")).strip() or "tonight's show"
    return {"mood": mood, "title": title[:70], "script": script}


async def compose(material: str, minutes: float = 3.0, timeout: float | None = None) -> dict:
    # A laptop CPU writing three minutes of script is slower than a hosted GPU.
    timeout = timeout or (600.0 if BACKEND == "local" else 90.0)
    if not API_KEY and BACKEND == "openrouter":
        raise ComposeError("OPENROUTER_API_KEY is not set.")

    words = int(minutes * 132)  # 132 wpm, unhurried, close to audiobook pace
    material = material.strip()
    if len(material) < 40:
        raise ComposeError("There isn't enough here to make a show from.")
    # Keep well inside the free tier's context and latency budget.
    material = material[:24000]

    messages = [
        {"role": "system", "content": SYSTEM.format(words=words)},
        {"role": "user", "content": material},
    ]
    headers = {"Authorization": f"Bearer {API_KEY}"} if BACKEND == "openrouter" else {}
    failures: list[str] = []

    live = list(MODELS)
    async with httpx.AsyncClient(timeout=timeout) as client:
        # Rounds over the whole list rather than retries on one model. The free
        # pool fails in bursts (429, 502, 504) that usually clear in seconds,
        # and the next model may be fine while this one is busy.
        for rnd in range(3):
            if rnd:
                await asyncio.sleep(2.0 * rnd)
            for model in list(live):
                payload = {
                    "model": model,
                    "temperature": 0.7,
                    "messages": messages,
                }
                if BACKEND == "openrouter":
                    # Let OpenRouter try a different host for the same
                    # open-weight model before we give up on it.
                    payload["provider"] = {"allow_fallbacks": True}
                try:
                    r = await client.post(URL, headers=headers, json=payload)
                except httpx.HTTPError as exc:
                    failures.append(f"{model}: {exc.__class__.__name__}")
                    continue

                if r.status_code == 200:
                    try:
                        return _coerce(r.json()["choices"][0]["message"]["content"])
                    except (ComposeError, KeyError, ValueError) as exc:
                        # Bad JSON is often a one-off. Worth another round.
                        failures.append(f"{model}: {exc}")
                        continue

                failures.append(f"{model}: {r.status_code} {_reason(r)}")
                if r.status_code != 429 and r.status_code < 500:
                    # Bad key, no credits, unknown model: retrying won't help.
                    live.remove(model)
            if not live:
                break

    log.warning("Gemma unavailable: %s", "; ".join(failures))
    raise ComposeError(
        "Gemma's servers are busy right now, so the show couldn't be written. "
        "Give it a minute and try again."
        + (f" ({failures[-1][:120]})" if failures else "")
    )


def _reason(r: httpx.Response) -> str:
    """Pull the provider's own message out, rather than hiding it."""
    try:
        err = r.json().get("error", {})
        meta = err.get("metadata") or {}
        text = str(meta.get("raw") or err.get("message") or "")
    except ValueError:
        text = r.text
    return " ".join(text.split())[:200]