# Foresight Backend

The live product (`app/static/index.html`) is a self-contained frontend with its
own tested JavaScript calculation engine — it does not call this backend for
readiness, coverage, risk, succession, or match numbers. This FastAPI backend
serves that page and hosts the three real AI calls (`/api/strategy/analyze`,
`/api/skills/suggest`, `/api/data/validate`, all calling Gemini).

`app/engine.py` is a separate, real, unit-tested (`pytest -q`, 8 tests)
implementation of similar workforce-readiness math, described below. It is
**not currently wired to any live number in the UI** — only `readiness()` and
`critical_gaps()` from it are used, and only inside `/api/strategy/analyze`'s
response payload. Its formulas differ in places from the frontend's (e.g.
capability coverage is a 70/30 blend here vs. a top-N-ratio average in the
frontend) — this is a known, intentional gap, not a bug: unifying the two
was evaluated and deliberately deferred as disproportionate risk for a
hackathon timeline, since no live number actually depends on the mismatch.

## What `app/engine.py` calculates

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

## Endpoints

- `GET /` — serves the frontend
- `GET /health`
- `POST /api/strategy/analyze` — Gemini call, translates a strategy into future skill targets
- `POST /api/skills/suggest` — Gemini call, proposes a skill-score update from evidence text
- `POST /api/data/validate` — Gemini call, classifies uploaded file content as workforce-related or not before Connect Your Data imports anything

`app/engine.py`'s other functions (`capability_coverage`, `backup_scores`,
`succession_coverage`, `total_exposure`, `scenario_employee_unavailable`,
`qualified_count`, `single_point_risks`) have no corresponding REST route —
they exist only as tested library code. Their previous routes
(`/api/overview`, `/api/employees`, `/api/talent-match`,
`/api/simulations/employee-unavailable`, `/api/skills/verify`,
`/api/future-requirements`, `/api/business-impact`, `/api/reset-demo`) were
removed since the frontend never called them and an unused, differently-
calculated API surface is more confusing than no API surface.

## Test

```bash
pytest -q
```
