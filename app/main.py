from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Dict

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .data import SKILLS, STATE
from .engine import critical_gaps, readiness

app = FastAPI(title="Foresight API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class StrategyAnalysisRequest(BaseModel):
    strategy: str
    horizon_months: int = Field(default=12, ge=1, le=60)


class FileValidationRequest(BaseModel):
    filename: str
    content: str = Field(max_length=6000)


class SkillSuggestionRequest(BaseModel):
    employee_id: str
    employee_name: str
    role: str
    skill: str
    current_score: float = Field(ge=0, le=5)
    current_confidence: float = Field(ge=0, le=1)
    evidence_text: str


GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent"


async def _post_to_gemini(api_key: str, prompt: str) -> httpx.Response:
    async with httpx.AsyncClient(timeout=30) as client:
        return await client.post(
            GEMINI_URL,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
            },
        )


async def call_gemini_json(prompt: str) -> dict:
    """Call Gemini with a prompt that requests JSON back; return it parsed.

    Tries GEMINI_API_KEY, then GEMINI_API_KEY_2 if it's set, so a second
    free-tier key can absorb quota overflow from the first. A 429 (quota
    exhausted) moves straight to the next key since retrying won't help;
    a network error or 5xx gets one retry on the same key first.

    Raises HTTPException on total failure (no key configured, network error,
    non-200, or a response that isn't valid JSON), so callers can just
    `await` this and let FastAPI turn it into a clean error response.
    """
    keys = [k for k in (os.environ.get("GEMINI_API_KEY"), os.environ.get("GEMINI_API_KEY_2")) if k]
    if not keys:
        raise HTTPException(500, "GEMINI_API_KEY is not configured on the server")

    last_error = HTTPException(502, "AI call failed")
    for key in keys:
        for attempt in range(2):
            try:
                resp = await _post_to_gemini(key, prompt)
            except httpx.HTTPError as exc:
                last_error = HTTPException(502, f"Could not reach AI provider: {exc}")
                await asyncio.sleep(1.5)
                continue

            if resp.status_code == 200:
                try:
                    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                    return json.loads(text)
                except (KeyError, IndexError, json.JSONDecodeError) as exc:
                    raise HTTPException(502, f"AI response was not in the expected format: {exc}")

            last_error = HTTPException(502, f"AI provider error ({resp.status_code}): {resp.text[:300]}")
            if resp.status_code == 429:
                break  # this key is out of quota - retrying it won't help, move to the next key
            await asyncio.sleep(1.5)  # transient server-side error - retry same key once

    raise last_error


STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def root():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/logo.jpeg", include_in_schema=False)
def logo():
    return FileResponse(STATIC_DIR / "logo.jpeg")


@app.get("/health")
def health():
    return {"ok": True, "service": "skillspulse-api", "version": app.version}


@app.post("/api/strategy/analyze")
async def analyze_strategy(req: StrategyAnalysisRequest):
    """Translate a free-text business/technology strategy into future skill targets.

    Real model call, not keyword matching: the model only ever returns adjustments
    to the existing skill catalog (validated against SKILLS + clamped to 0..5),
    so a bad or unexpected response can't corrupt state.
    """
    catalog = {
        key: {
            "label": meta["label"],
            "current_future_target": STATE["future_requirements"][key],
            "criticality": meta["criticality"],
        }
        for key, meta in SKILLS.items()
    }
    prompt = (
        "You translate a business/technology strategy into required workforce skill targets "
        "for an internal workforce-readiness tool.\n\n"
        f"Skill catalog (key, label, current future target on a 0-5 scale, criticality):\n"
        f"{json.dumps(catalog, indent=2)}\n\n"
        f'Business strategy: "{req.strategy}"\n'
        f"Planning horizon: {req.horizon_months} months\n\n"
        "Return ONLY a JSON object mapping affected skill keys to a new future target "
        "(a number from 0 to 5, one decimal place). Only include skills materially "
        "affected by this specific strategy. Never invent a skill key outside the catalog above."
    )

    adjustments = await call_gemini_json(prompt)

    applied: Dict[str, float] = {}
    for key, value in adjustments.items():
        if key in SKILLS and isinstance(value, (int, float)) and 0 <= value <= 5:
            STATE["future_requirements"][key] = float(value)
            applied[key] = float(value)

    return {
        "ok": True,
        "applied_adjustments": applied,
        "future_requirements": STATE["future_requirements"],
        "future_readiness_pct": readiness(STATE["employees"], STATE["future_requirements"]),
        "future_gaps": critical_gaps(STATE["employees"], STATE["future_requirements"]),
    }


@app.post("/api/data/validate")
async def validate_uploaded_file(req: FileValidationRequest):
    """Classify uploaded file content before Connect Your Data imports anything.

    A real model call, not a keyword match: Gemini reads the extracted text
    and decides whether it plausibly describes employees/workforce/HR/SAP
    data. Nothing is imported unless this returns ok=True - a wrong file
    (a recipe, an invoice, a random PDF) gets rejected with a reason instead
    of being parsed as if it were a roster.
    """
    if not req.content.strip():
        return {"ok": True, "is_relevant": False, "reason": "The file appears to be empty."}

    prompt = (
        "You are a gatekeeper for a workforce-readiness tool's file import feature. "
        "Decide whether the text below plausibly comes from an employee roster, HR "
        "export, skills/competency spreadsheet, SAP or workforce-management data file. "
        "It does NOT need to match any specific column format - any real employee, "
        "role, department, skill, or certification data counts.\n\n"
        f"Filename: {req.filename}\n\n"
        f"Extracted content (may be partial/truncated):\n\"\"\"\n{req.content}\n\"\"\"\n\n"
        "Return ONLY a JSON object with:\n"
        '- "is_relevant": true or false\n'
        '- "detected_type": a short label for what the file actually looks like '
        '(e.g. "employee roster", "recipe", "invoice", "unrelated text")\n'
        '- "reason": one short sentence explaining the decision'
    )

    parsed = await call_gemini_json(prompt)
    try:
        is_relevant = bool(parsed["is_relevant"])
        detected_type = str(parsed.get("detected_type", "")).strip() or "unknown"
        reason = str(parsed.get("reason", "")).strip() or "No reason returned."
    except (KeyError, TypeError):
        raise HTTPException(502, "AI response was not in the expected format")

    return {"ok": True, "is_relevant": is_relevant, "detected_type": detected_type, "reason": reason}


@app.post("/api/skills/suggest")
async def suggest_skill_update(req: SkillSuggestionRequest):
    """Suggest a skill-score update from new evidence text - a real model call.

    Returns a proposed score only; it never writes to any employee record.
    The caller (frontend) is responsible for applying it after human approval,
    same human-in-the-loop pattern as the rest of the app.
    """
    if req.skill not in SKILLS:
        raise HTTPException(400, f"Unknown skill: {req.skill}")
    if not req.evidence_text.strip():
        raise HTTPException(400, "evidence_text is required")

    meta = SKILLS[req.skill]
    prompt = (
        "You assess whether new work evidence justifies updating an employee's skill score "
        "in an internal workforce-readiness tool.\n\n"
        f"Employee: {req.employee_name}, {req.role}\n"
        f"Skill: {meta['label']} (0-5 scale). Current score {req.current_score}, "
        f"current evidence confidence {req.current_confidence}.\n\n"
        f'New evidence: "{req.evidence_text}"\n\n'
        "Return ONLY a JSON object with:\n"
        '- "suggested_score": number 0-5, one decimal\n'
        '- "confidence": number 0-1, how much you trust this evidence\n'
        '- "reasoning": one short sentence\n\n'
        "Be conservative: do not move the score by more than 1.0 point from the current "
        "score based on a single piece of evidence, and do not invent specifics the "
        "evidence doesn't support."
    )

    parsed = await call_gemini_json(prompt)
    try:
        suggested_score = float(parsed["suggested_score"])
        confidence = float(parsed["confidence"])
        reasoning = str(parsed.get("reasoning", "")).strip()
    except (KeyError, TypeError, ValueError):
        raise HTTPException(502, "AI response was not in the expected format")

    if not (0 <= suggested_score <= 5) or not (0 <= confidence <= 1):
        raise HTTPException(502, "AI returned an out-of-range score or confidence")

    return {
        "ok": True,
        "employee_id": req.employee_id,
        "employee_name": req.employee_name,
        "skill": req.skill,
        "skill_label": meta["label"],
        "current_score": req.current_score,
        "suggested_score": round(suggested_score, 1),
        "confidence": round(confidence, 2),
        "reasoning": reasoning or "No reasoning returned.",
    }
