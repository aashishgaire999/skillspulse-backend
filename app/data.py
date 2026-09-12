from copy import deepcopy

SKILLS = {
    "SAP": {
        "label": "SAP Configuration",
        "target": 4.6,
        "future_target": 4.8,
        "weight": 0.23,
        "criticality": "Critical",
        "required_experts": 3,
        "daily_downtime_cost": 2500.0,
        "default_recovery_days": 30,
        "related_keywords": ["sap"],
    },
    "FoodSafety": {
        "label": "Food Safety Certification",
        "target": 4.5,
        "future_target": 4.7,
        "weight": 0.22,
        "criticality": "Critical",
        "required_experts": 2,
        "daily_downtime_cost": 3000.0,
        "default_recovery_days": 14,
        "related_keywords": ["food safety", "food"],
    },
    "Robotics": {
        "label": "Industrial Robotics",
        "target": 4.6,
        "future_target": 4.9,
        "weight": 0.20,
        "criticality": "High",
        "required_experts": 2,
        "daily_downtime_cost": 2800.0,
        "default_recovery_days": 21,
        "related_keywords": ["robotics", "industrial"],
    },
    "ColdChain": {
        "label": "Cold Chain Operations",
        "target": 4.3,
        "future_target": 4.6,
        "weight": 0.18,
        "criticality": "High",
        "required_experts": 3,
        "daily_downtime_cost": 2200.0,
        "default_recovery_days": 14,
        "related_keywords": ["cold chain", "cold"],
    },
    "AIOps": {
        "label": "AI-Assisted Operations",
        "target": 4.3,
        "future_target": 4.8,
        "weight": 0.17,
        "criticality": "High",
        "required_experts": 2,
        "daily_downtime_cost": 2000.0,
        "default_recovery_days": 30,
        "related_keywords": ["aiops", "ai-assisted", "automation", "analytics", "predictive", "machine learning"],
    },
}

EMPLOYEES = [
    {
        "id": "alex",
        "name": "Alex Morgan",
        "role": "Operations Systems Lead",
        "department": "Operations",
        "team": "Enterprise Systems",
        "confidence": 0.96,
        "freshness_days": 18,
        "growth_rate": 0.04,  # skill points / month
        "interests": ["automation", "systems resilience", "SAP"],
        "skills": {"SAP": 5.0, "FoodSafety": 3.1, "Robotics": 4.6, "ColdChain": 4.0, "AIOps": 4.2},
        "projects": ["ERP Modernization", "Line Automation"],
        "certifications": ["SAP Advanced"],
    },
    {
        "id": "maria",
        "name": "Maria Santos",
        "role": "Process Engineer",
        "department": "Engineering",
        "team": "Plant Engineering",
        "confidence": 0.91,
        "freshness_days": 21,
        "growth_rate": 0.18,
        "interests": ["automation leadership", "SAP", "robotics"],
        "skills": {"SAP": 4.1, "FoodSafety": 4.4, "Robotics": 3.2, "ColdChain": 4.0, "AIOps": 3.3},
        "projects": ["SAP Rollout", "Packaging Upgrade"],
        "certifications": ["Lean Manufacturing"],
    },
    {
        "id": "john",
        "name": "John Lee",
        "role": "Quality Specialist",
        "department": "Quality",
        "team": "Food Safety",
        "confidence": 0.94,
        "freshness_days": 10,
        "growth_rate": 0.08,
        "interests": ["food safety leadership", "quality systems"],
        "skills": {"SAP": 2.5, "FoodSafety": 4.8, "Robotics": 2.1, "ColdChain": 3.2, "AIOps": 2.0},
        "projects": ["Audit Readiness", "Supplier Quality"],
        "certifications": ["Food Safety Level 2"],
    },
    {
        "id": "priya",
        "name": "Priya Shah",
        "role": "Supply Chain Analyst",
        "department": "Supply Chain",
        "team": "Cold Chain",
        "confidence": 0.87,
        "freshness_days": 34,
        "growth_rate": 0.21,
        "interests": ["automation analytics", "machine vision", "cold chain"],
        "skills": {"SAP": 3.4, "FoodSafety": 3.3, "Robotics": 4.0, "ColdChain": 4.7, "AIOps": 3.8},
        "projects": ["Cold Chain Optimization", "Vision Pilot"],
        "certifications": ["Data Analytics"],
    },
    {
        "id": "sam",
        "name": "Sam Rivera",
        "role": "Maintenance Engineer",
        "department": "Operations",
        "team": "Plant Reliability",
        "confidence": 0.88,
        "freshness_days": 55,
        "growth_rate": 0.12,
        "interests": ["predictive maintenance", "robotics"],
        "skills": {"SAP": 3.2, "FoodSafety": 3.6, "Robotics": 4.3, "ColdChain": 3.5, "AIOps": 3.4},
        "projects": ["Predictive Maintenance Pilot"],
        "certifications": ["Industrial Maintenance"],
    },
    {
        "id": "lena",
        "name": "Lena Park",
        "role": "R&D Specialist",
        "department": "R&D",
        "team": "Product Innovation",
        "confidence": 0.90,
        "freshness_days": 92,
        "growth_rate": 0.05,
        "interests": ["product innovation", "Korean market R&D"],
        "skills": {"SAP": 2.2, "FoodSafety": 4.2, "Robotics": 2.8, "ColdChain": 3.0, "AIOps": 3.1},
        "projects": ["Korean Product Launch"],
        "certifications": ["Food Science"],
    },
]

# Simple in-memory store for hackathon speed. Replace with Supabase/Postgres later.
STATE = {
    "employees": deepcopy(EMPLOYEES),
    "future_requirements": {k: v["future_target"] for k, v in SKILLS.items()},
    "business_impact": {
        k: {
            "daily_downtime_cost": v["daily_downtime_cost"],
            "default_recovery_days": v["default_recovery_days"],
        }
        for k, v in SKILLS.items()
    },
}


def reset_state():
    STATE["employees"] = deepcopy(EMPLOYEES)
    STATE["future_requirements"] = {k: v["future_target"] for k, v in SKILLS.items()}
    STATE["business_impact"] = {
        k: {
            "daily_downtime_cost": v["daily_downtime_cost"],
            "default_recovery_days": v["default_recovery_days"],
        }
        for k, v in SKILLS.items()
    }
