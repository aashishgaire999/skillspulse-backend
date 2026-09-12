from copy import deepcopy

from app.data import EMPLOYEES, SKILLS
from app.engine import (
    backup_scores,
    capability_coverage,
    readiness,
    scenario_employee_unavailable,
    succession_coverage,
    total_exposure,
)


def test_readiness_is_bounded():
    r = readiness(deepcopy(EMPLOYEES))
    assert 0 <= r <= 100


def test_removing_alex_hurts_or_preserves_readiness_never_improves_it():
    before = readiness(deepcopy(EMPLOYEES))
    after = readiness([e for e in deepcopy(EMPLOYEES) if e["id"] != "alex"])
    assert after <= before


def test_sap_coverage_drops_when_alex_is_removed():
    before = capability_coverage(deepcopy(EMPLOYEES), "SAP")
    after = capability_coverage([e for e in deepcopy(EMPLOYEES) if e["id"] != "alex"], "SAP")
    assert after < before


def test_financial_exposure_nonnegative():
    exposure = total_exposure(deepcopy(EMPLOYEES))
    assert exposure["estimated_exposure"] >= 0
    assert len(exposure["details"]) == len(SKILLS)


def test_scenario_has_incremental_business_impact():
    result = scenario_employee_unavailable(deepcopy(EMPLOYEES), "alex")
    assert result["incremental_business_impact"] >= 0
    assert result["after"]["readiness_pct"] <= result["before"]["readiness_pct"]


def test_backup_ranking_returns_candidates():
    matches = backup_scores(deepcopy(EMPLOYEES), "SAP", "alex")
    assert matches
    assert matches[0]["employee_id"] != "alex"
    assert 0 <= matches[0]["match_pct"] <= 100


def test_succession_coverage_is_bounded():
    s = succession_coverage(deepcopy(EMPLOYEES))
    assert 0 <= s <= 100


def test_aiops_interest_alignment_is_not_always_default():
    matches = backup_scores(deepcopy(EMPLOYEES), "AIOps")
    aligned = [m for m in matches if m["career_interest_aligned"]]
    assert aligned, "at least one employee should show real interest alignment for AIOps"
