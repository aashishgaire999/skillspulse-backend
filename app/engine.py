from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Dict, Iterable, List, Optional

from .data import SKILLS


def freshness_factor(days: int) -> float:
    """Evidence freshness multiplier.

    Recent evidence should matter more, but a previously demonstrated capability
    should not instantly disappear. The breakpoints are explicit and auditable.
    """
    if days <= 90:
        return 1.00
    if days <= 180:
        return 0.93
    if days <= 365:
        return 0.84
    return 0.70


def confidence_factor(confidence: float) -> float:
    """Convert 0..1 evidence confidence into a conservative multiplier 0.70..1.00."""
    c = min(1.0, max(0.0, confidence))
    return 0.70 + 0.30 * c


def effective_skill(employee: dict, skill_key: str) -> float:
    raw = float(employee.get("skills", {}).get(skill_key, 0.0))
    return raw * confidence_factor(float(employee.get("confidence", 0.0))) * freshness_factor(
        int(employee.get("freshness_days", 9999))
    )


def individual_readiness_ratio(employee: dict, skill_key: str, target: Optional[float] = None) -> float:
    target = float(target if target is not None else SKILLS[skill_key]["target"])
    if target <= 0:
        return 0.0
    return min(1.0, max(0.0, effective_skill(employee, skill_key) / target))


def qualified_count(employees: Iterable[dict], skill_key: str, target: Optional[float] = None) -> int:
    target = float(target if target is not None else SKILLS[skill_key]["target"])
    threshold = 0.90 * target
    return sum(1 for e in employees if effective_skill(e, skill_key) >= threshold)


def capability_coverage(employees: List[dict], skill_key: str, target: Optional[float] = None) -> float:
    """0..1 team coverage for one capability.

    Coverage combines two things leaders actually care about:

    1) **Qualified depth (70%)** — how many near-target people exist relative to
       the number of experts the business says it needs.
    2) **Top-team proficiency (30%)** — how close the strongest required number
       of people are to the target, even if they are not fully qualified yet.

    This deliberately prevents five half-ready employees from making a critical
    capability look 100% covered, while still giving credit for developable
    internal talent.
    """
    target = float(target if target is not None else SKILLS[skill_key]["target"])
    required_experts = max(1, int(SKILLS[skill_key]["required_experts"]))

    ratios = sorted(
        (individual_readiness_ratio(e, skill_key, target) for e in employees),
        reverse=True,
    )
    qualified = qualified_count(employees, skill_key, target)
    qualified_depth = min(1.0, qualified / required_experts)
    top_team = ratios[:required_experts]
    top_team_proficiency = sum(top_team) / required_experts if top_team else 0.0

    return min(1.0, 0.70 * qualified_depth + 0.30 * top_team_proficiency)


def readiness(employees: List[dict], requirements: Optional[Dict[str, float]] = None) -> float:
    weighted = 0.0
    total_weight = 0.0
    for key, meta in SKILLS.items():
        target = float(requirements[key]) if requirements and key in requirements else float(meta["target"])
        weight = float(meta["weight"])
        weighted += capability_coverage(employees, key, target) * weight
        total_weight += weight
    if total_weight == 0:
        return 0.0
    return round(100.0 * weighted / total_weight, 1)


def critical_gaps(employees: List[dict], requirements: Optional[Dict[str, float]] = None) -> List[dict]:
    gaps = []
    for key, meta in SKILLS.items():
        if meta["criticality"] not in ("Critical", "High"):
            continue
        target = float(requirements[key]) if requirements and key in requirements else float(meta["target"])
        coverage = capability_coverage(employees, key, target)
        qualified = qualified_count(employees, key, target)
        if coverage < 0.75 or qualified == 0:
            gaps.append(
                {
                    "skill": key,
                    "label": meta["label"],
                    "coverage_pct": round(coverage * 100, 1),
                    "qualified_people": qualified,
                    "required_experts": meta["required_experts"],
                    "target": target,
                    "criticality": meta["criticality"],
                }
            )
    return gaps


def single_point_risks(employees: List[dict], requirements: Optional[Dict[str, float]] = None) -> List[dict]:
    risks = []
    for key, meta in SKILLS.items():
        if meta["criticality"] not in ("Critical", "High"):
            continue
        target = float(requirements[key]) if requirements and key in requirements else float(meta["target"])
        qualified = qualified_count(employees, key, target)
        if qualified <= 1:
            risks.append(
                {
                    "skill": key,
                    "label": meta["label"],
                    "qualified_people": qualified,
                    "required_experts": meta["required_experts"],
                    "coverage_pct": round(capability_coverage(employees, key, target) * 100, 1),
                }
            )
    return risks


def succession_coverage(employees: List[dict], requirements: Optional[Dict[str, float]] = None) -> float:
    critical_keys = [k for k, v in SKILLS.items() if v["criticality"] in ("Critical", "High")]
    if not critical_keys:
        return 100.0
    protected = 0
    for key in critical_keys:
        target = float(requirements[key]) if requirements and key in requirements else float(SKILLS[key]["target"])
        # Succession protection means at least TWO people can perform the capability near target.
        if qualified_count(employees, key, target) >= 2:
            protected += 1
    return round(100.0 * protected / len(critical_keys), 1)


def employee_readiness(employee: dict, requirements: Optional[Dict[str, float]] = None) -> float:
    weighted = 0.0
    total_weight = 0.0
    for key, meta in SKILLS.items():
        target = float(requirements[key]) if requirements and key in requirements else float(meta["target"])
        weight = float(meta["weight"])
        weighted += individual_readiness_ratio(employee, key, target) * weight
        total_weight += weight
    return round(100.0 * weighted / total_weight, 1) if total_weight else 0.0


def skill_gap(employee: dict, skill_key: str, target: Optional[float] = None) -> float:
    target = float(target if target is not None else SKILLS[skill_key]["target"])
    return max(0.0, target - float(employee.get("skills", {}).get(skill_key, 0.0)))


def time_to_readiness_weeks(employee: dict, skill_key: str, target: Optional[float] = None) -> int:
    """Estimate weeks using the employee's observed skill-points-per-month growth rate.

    This is an estimate, not a promise. Minimum one month-equivalent denominator
    prevents divide-by-zero and over-optimistic instant readiness.
    """
    gap = skill_gap(employee, skill_key, target)
    if gap <= 0:
        return 0
    rate = max(0.05, float(employee.get("growth_rate", 0.05)))
    months = gap / rate
    return max(1, ceil(months * 4.345))


def backup_scores(employees: List[dict], skill_key: str, exclude_employee_id: Optional[str] = None) -> List[dict]:
    target = float(SKILLS[skill_key]["target"])
    results = []
    for e in employees:
        if exclude_employee_id and e["id"] == exclude_employee_id:
            continue
        exact = individual_readiness_ratio(e, skill_key, target)
        adjacent_keys = [k for k in SKILLS if k != skill_key]
        adjacent = sum(individual_readiness_ratio(e, k) for k in adjacent_keys) / max(1, len(adjacent_keys))
        confidence = min(1.0, max(0.0, float(e.get("confidence", 0))))
        growth = min(1.0, max(0.0, float(e.get("growth_rate", 0))) / 0.25)  # 0.25 points/month ~= very fast

        # Interest alignment is matched against an explicit per-skill keyword list
        # (SKILLS[skill_key]["related_keywords"]) rather than the skill's raw key/label,
        # since literal label text rarely appears verbatim in free-text interests.
        keywords = SKILLS[skill_key].get("related_keywords", [skill_key.lower()])
        interest_text = " ".join(e.get("interests", [])).lower()
        interest = 1.0 if any(kw in interest_text for kw in keywords) else 0.55

        score = 100 * (0.45 * exact + 0.20 * adjacent + 0.15 * confidence + 0.10 * growth + 0.10 * interest)
        weeks = time_to_readiness_weeks(e, skill_key, target)
        results.append(
            {
                "employee_id": e["id"],
                "name": e["name"],
                "role": e["role"],
                "department": e["department"],
                "match_pct": round(score, 1),
                "skill_score": e["skills"].get(skill_key, 0),
                "effective_skill": round(effective_skill(e, skill_key), 2),
                "confidence_pct": round(confidence * 100, 1),
                "gap_points": round(skill_gap(e, skill_key, target), 2),
                "time_to_readiness_weeks": weeks,
                "succession_depth": "Ready Now" if weeks == 0 else ("Ready <6 Months" if weeks <= 26 else "Ready 6–12 Months"),
                "career_interest_aligned": interest == 1.0,
            }
        )
    return sorted(results, key=lambda x: x["match_pct"], reverse=True)


def recovery_days_for_skill(employees: List[dict], skill_key: str, exclude_employee_id: Optional[str] = None) -> int:
    matches = backup_scores(employees, skill_key, exclude_employee_id)
    if not matches:
        return int(SKILLS[skill_key]["default_recovery_days"])
    best_weeks = matches[0]["time_to_readiness_weeks"]
    if best_weeks == 0:
        return 7  # even a ready-now backup needs handoff/verification time
    return min(365, max(7, best_weeks * 7))


def exposure_for_skill(
    employees: List[dict],
    skill_key: str,
    daily_downtime_cost: Optional[float] = None,
    recovery_days: Optional[int] = None,
    requirements: Optional[Dict[str, float]] = None,
) -> dict:
    meta = SKILLS[skill_key]
    target = float(requirements[skill_key]) if requirements and skill_key in requirements else float(meta["target"])
    required = int(meta["required_experts"])
    # Capacity gap measured in "expert-equivalent" units.
    coverage = capability_coverage(employees, skill_key, target)
    gap_units = max(0.0, required * (1.0 - coverage))
    cost = float(daily_downtime_cost if daily_downtime_cost is not None else meta["daily_downtime_cost"])
    days = int(recovery_days if recovery_days is not None else meta["default_recovery_days"])
    exposure = gap_units * cost * days
    return {
        "skill": skill_key,
        "label": meta["label"],
        "coverage_pct": round(coverage * 100, 1),
        "gap_expert_equivalents": round(gap_units, 3),
        "daily_downtime_cost": round(cost, 2),
        "recovery_days": days,
        "estimated_exposure": round(exposure, 2),
        "formula": "expert_equivalent_gap × downtime_cost_per_day × recovery_days",
    }


def total_exposure(employees: List[dict], business_impact: Optional[dict] = None, requirements: Optional[Dict[str, float]] = None) -> dict:
    details = []
    total = 0.0
    for key in SKILLS:
        override = (business_impact or {}).get(key, {})
        item = exposure_for_skill(
            employees,
            key,
            daily_downtime_cost=override.get("daily_downtime_cost"),
            recovery_days=override.get("default_recovery_days"),
            requirements=requirements,
        )
        details.append(item)
        total += item["estimated_exposure"]
    return {"estimated_exposure": round(total, 2), "details": details}


def scenario_employee_unavailable(employees: List[dict], employee_id: str, business_impact: Optional[dict] = None) -> dict:
    employee = next((e for e in employees if e["id"] == employee_id), None)
    if employee is None:
        raise KeyError(f"Employee {employee_id!r} not found")

    before = list(employees)
    after = [e for e in employees if e["id"] != employee_id]
    before_exposure = total_exposure(before, business_impact)
    after_exposure = total_exposure(after, business_impact)

    changed = []
    for key, meta in SKILLS.items():
        b = capability_coverage(before, key)
        a = capability_coverage(after, key)
        if b - a >= 0.03:
            changed.append(
                {
                    "skill": key,
                    "label": meta["label"],
                    "coverage_before_pct": round(b * 100, 1),
                    "coverage_after_pct": round(a * 100, 1),
                    "delta_pct_points": round((a - b) * 100, 1),
                }
            )

    primary_skill = max(SKILLS, key=lambda key: individual_readiness_ratio(employee, key) * SKILLS[key]["weight"])
    backups = backup_scores(before, primary_skill, exclude_employee_id=employee_id)

    return {
        "scenario": "employee_unavailable",
        "employee": {"id": employee["id"], "name": employee["name"], "role": employee["role"]},
        "primary_risk_skill": primary_skill,
        "before": {
            "readiness_pct": readiness(before),
            "critical_gap_count": len(critical_gaps(before)),
            "single_point_risk_count": len(single_point_risks(before)),
            "succession_coverage_pct": succession_coverage(before),
            "business_exposure": before_exposure["estimated_exposure"],
        },
        "after": {
            "readiness_pct": readiness(after),
            "critical_gap_count": len(critical_gaps(after)),
            "single_point_risk_count": len(single_point_risks(after)),
            "succession_coverage_pct": succession_coverage(after),
            "business_exposure": after_exposure["estimated_exposure"],
        },
        "incremental_business_impact": round(
            max(0.0, after_exposure["estimated_exposure"] - before_exposure["estimated_exposure"]), 2
        ),
        "what_changed": changed,
        "recommended_backups": backups[:5],
    }
