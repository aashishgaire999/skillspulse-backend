from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Dict, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .data import SKILLS, STATE, reset_state
from .engine import (
    backup_scores,
    capability_coverage,
    critical_gaps,
    effective_skill,
    employee_readiness,
    qualified_count,
    readiness,
    scenario_employee_unavailable,
    single_point_risks,
    succession_coverage,
    total_exposure,
)

app = FastAPI(title="SkillsPulse API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class EmployeeUnavailableRequest(BaseModel):
    employee_id: str


class TalentMatchRequest(BaseModel):
    skill: str
    exclude_employee_id: Optional[str] = None


class SkillVerificationRequest(BaseModel):
    employee_id: str
    skill: str
    verified_score: float = Field(ge=0, le=5)
    confidence: float = Field(ge=0, le=1)
    freshness_days: int = Field(default=0, ge=0)


class FutureRequirementsRequest(BaseModel):
    requirements: Dict[str, float]


class ImpactUpdateRequest(BaseModel):
    skill: str
    daily_downtime_cost: float = Field(ge=0)
    default_recovery_days: int = Field(ge=0, le=3650)


class StrategyAnalysisRequest(BaseModel):
    strategy: str
    horizon_months: int = Field(default=12, ge=1, le=60)


STATIC_DIR = Path(__file__).parent / "static"


@app.get("/", include_in_schema=False)
def root():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    return {"ok": True, "service": "skillspulse-api", "version": app.version}


@app.post("/api/reset-demo")
def reset_demo():
    reset_state()
    return {"ok": True, "employees": len(STATE["employees"])}


@app.get("/api/skills")
def get_skills():
    return SKILLS


@app.get("/api/employees")
def get_employees(q: Optional[str] = Query(default=None)):
    employees = STATE["employees"]
    if not q:
        return employees
    needle = q.lower().strip()
    return [
        e
        for e in employees
        if needle in " ".join(
            [e["name"], e["role"], e["department"], e["team"], " ".join(e["interests"]), " ".join(e["projects"])]
        ).lower()
    ]


@app.get("/api/employees/{employee_id}")
def get_employee(employee_id: str):
    e = next((x for x in STATE["employees"] if x["id"] == employee_id), None)
    if not e:
        raise HTTPException(404, "Employee not found")
    enriched = deepcopy(e)
    enriched["readiness_pct"] = employee_readiness(e)
    enriched["skill_evidence"] = {
        k: {
            "raw_score": e["skills"].get(k, 0),
            "effective_score": round(effective_skill(e, k), 2),
            "confidence_pct": round(e["confidence"] * 100, 1),
            "last_verified_days_ago": e["freshness_days"],
        }
        for k in SKILLS
    }
    return enriched


@app.get("/api/overview")
def overview():
    employees = STATE["employees"]
    future = STATE["future_requirements"]
    current_exposure = total_exposure(employees, STATE["business_impact"])
    future_exposure = total_exposure(employees, STATE["business_impact"], future)
    capabilities = []
    for key, meta in SKILLS.items():
        capabilities.append(
            {
                "skill": key,
                "label": meta["label"],
                "criticality": meta["criticality"],
                "current_coverage_pct": round(capability_coverage(employees, key) * 100, 1),
                "future_coverage_pct": round(capability_coverage(employees, key, future[key]) * 100, 1),
                "qualified_people": qualified_count(employees, key),
                "required_experts": meta["required_experts"],
            }
        )
    return {
        "workforce_readiness_pct": readiness(employees),
        "future_readiness_pct": readiness(employees, future),
        "critical_skill_gaps": critical_gaps(employees),
        "single_point_knowledge_risks": single_point_risks(employees),
        "succession_coverage_pct": succession_coverage(employees),
        "business_exposure": current_exposure,
        "future_business_exposure": future_exposure,
        "capabilities": capabilities,
    }


@app.post("/api/simulations/employee-unavailable")
def simulate_employee_unavailable(req: EmployeeUnavailableRequest):
    try:
        return scenario_employee_unavailable(STATE["employees"], req.employee_id, STATE["business_impact"])
    except KeyError as exc:
        raise HTTPException(404, str(exc))


@app.post("/api/talent-match")
def talent_match(req: TalentMatchRequest):
    if req.skill not in SKILLS:
        raise HTTPException(400, f"Unknown skill: {req.skill}")
    return {
        "skill": req.skill,
        "label": SKILLS[req.skill]["label"],
        "matches": backup_scores(STATE["employees"], req.skill, req.exclude_employee_id),
    }


@app.post("/api/skills/verify")
def verify_skill(req: SkillVerificationRequest):
    if req.skill not in SKILLS:
        raise HTTPException(400, "Unknown skill")
    employee = next((e for e in STATE["employees"] if e["id"] == req.employee_id), None)
    if not employee:
        raise HTTPException(404, "Employee not found")
    employee["skills"][req.skill] = req.verified_score
    employee["confidence"] = req.confidence
    employee["freshness_days"] = req.freshness_days
    return {
        "ok": True,
        "employee_id": employee["id"],
        "skill": req.skill,
        "verified_score": req.verified_score,
        "new_workforce_readiness_pct": readiness(STATE["employees"]),
        "new_succession_coverage_pct": succession_coverage(STATE["employees"]),
    }


@app.post("/api/future-requirements")
def update_future_requirements(req: FutureRequirementsRequest):
    unknown = [k for k in req.requirements if k not in SKILLS]
    if unknown:
        raise HTTPException(400, f"Unknown skills: {unknown}")
    for k, v in req.requirements.items():
        if not (0 <= v <= 5):
            raise HTTPException(400, f"Target for {k} must be 0..5")
        STATE["future_requirements"][k] = float(v)
    return {
        "ok": True,
        "future_requirements": STATE["future_requirements"],
        "future_readiness_pct": readiness(STATE["employees"], STATE["future_requirements"]),
        "future_gaps": critical_gaps(STATE["employees"], STATE["future_requirements"]),
    }


@app.post("/api/strategy/analyze")
async def analyze_strategy(req: StrategyAnalysisRequest):
    """Translate a free-text business/technology strategy into future skill targets.

    Real model call, not keyword matching: the model only ever returns adjustments
    to the existing skill catalog (validated against SKILLS + clamped to 0..5),
    so a bad or unexpected response can't corrupt state.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(500, "OPENAI_API_KEY is not configured on the server")

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

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.2,
                },
            )
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Could not reach AI provider: {exc}")

    if resp.status_code != 200:
        raise HTTPException(502, f"AI provider error ({resp.status_code}): {resp.text[:300]}")

    content = resp.json()["choices"][0]["message"]["content"]
    try:
        adjustments = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(502, "AI response was not valid JSON")

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


@app.post("/api/business-impact")
def update_business_impact(req: ImpactUpdateRequest):
    if req.skill not in SKILLS:
        raise HTTPException(400, "Unknown skill")
    STATE["business_impact"][req.skill] = {
        "daily_downtime_cost": req.daily_downtime_cost,
        "default_recovery_days": req.default_recovery_days,
    }
    return {
        "ok": True,
        "business_impact": STATE["business_impact"],
        "recalculated_exposure": total_exposure(STATE["employees"], STATE["business_impact"]),
    }
