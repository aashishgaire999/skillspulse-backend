# Foresight Backend — Deterministic Workforce Readiness Engine

This backend turns the Foresight frontend from a visual prototype into a real calculation engine.

## What is calculated

### 1. Effective skill

`effective_skill = raw_skill × confidence_factor × freshness_factor`

- raw skill: 0–5
- confidence factor: maps evidence confidence 0–1 into 0.70–1.00
- freshness factor:
  - <=90 days: 1.00
  - <=180 days: 0.93
  - <=365 days: 0.84
  - older: 0.70

### 2. Capability coverage

Coverage deliberately combines two signals:

`coverage = 70% × qualified_depth + 30% × top_team_proficiency`

Where:

- `qualified_depth = qualified_people / required_experts`, capped at 100%
- a qualified person has effective proficiency >=90% of the target
- `top_team_proficiency` is the average readiness ratio of the strongest `required_experts` people

This prevents a crowd of partially skilled employees from making a critical capability look fully covered, while still recognizing developable internal talent.

### 3. Workforce readiness

`readiness = weighted average of capability coverage`

Weights are explicit in `app/data.py` and sum to 1.

### 4. Single-point knowledge risk

A critical/high skill is a single-point risk when <=1 employee has effective proficiency >=90% of the required target.

### 5. Succession coverage

Percent of critical/high skills with at least 2 employees at >=90% of the target.

### 6. Backup / Talent Match

- 45% exact target skill fit
- 20% adjacent skill fit
- 15% evidence confidence
- 10% observed growth rate
- 10% career-interest alignment (matched against an explicit per-skill `related_keywords` list — see `app/data.py`)

### 7. Time to readiness

`months = skill_gap / observed_skill_growth_points_per_month`

Then converted to weeks. This is an estimate, not a promise.

### 8. Financial exposure

`estimated exposure = expert-equivalent coverage gap × downtime cost/day × recovery days`

This is dimensionally correct and uses editable business assumptions. It is a scenario estimate, not an accounting loss.

## Run locally

```bash
cd skillspulse-backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Open API docs:

`http://127.0.0.1:8000/docs`

Health check:

`http://127.0.0.1:8000/health`

## Main endpoints

- `GET /api/overview`
- `GET /api/employees`
- `GET /api/employees/{id}`
- `POST /api/simulations/employee-unavailable`
- `POST /api/talent-match`
- `POST /api/skills/verify`
- `POST /api/future-requirements`
- `POST /api/business-impact`
- `POST /api/reset-demo`

## Test

```bash
pytest -q
```

## Next step

Wire the current `skillspulse-sap-final.html` to these endpoints so the UI reads all KPI, scenario, match, and exposure values from this backend instead of browser-side calculations.
