from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Dict, Optional

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
