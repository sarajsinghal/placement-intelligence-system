"""Deterministic eligibility, matching and placement analytics."""
from __future__ import annotations
import re
from collections import Counter
from typing import Any

def _number(value: Any) -> float | None:
    try:
        if value is None or str(value).strip() == "": return None
        return float(value)
    except (TypeError, ValueError): return None

def assess_eligibility(student: dict, job: dict) -> dict:
    """Apply explicit mandatory thresholds; missing evidence is never treated as pass."""
    checks = []
    requirements = [
        ("graduation_min", "graduation_pct", "Graduation percentage"),
        ("pgdm_min", "pgdm_pct", "PGDM percentage"),
        ("experience_min_years", "experience_years", "Experience years"),
    ]
    for rule, field, label in requirements:
        threshold = _number(job.get(rule))
        if threshold is None: continue
        actual = _number(student.get(field))
        checks.append({"criterion": label, "required": threshold, "actual": actual,
                       "status": "missing" if actual is None else ("pass" if actual >= threshold else "fail")})
    required_specialization = str(job.get("specialization", "")).strip().lower()
    if required_specialization:
        actual = str(student.get("specialization", "")).strip()
        checks.append({"criterion": "Specialization", "required": required_specialization,
                       "actual": actual or None, "status": "missing" if not actual else
                       ("pass" if actual.lower() == required_specialization else "fail")})
    statuses = {c["status"] for c in checks}
    result = "ineligible" if "fail" in statuses else ("needs-verification" if "missing" in statuses else "eligible")
    return {"classification": result, "checks": checks,
            "explanation": "One or more mandatory criteria failed." if result == "ineligible" else
            ("Required evidence is incomplete; review before deciding." if result == "needs-verification" else "All configured mandatory criteria passed.")}

def skill_match(student_skills: str, preferred_skills: str) -> dict:
    """Transparent token overlap for discovery only; not an eligibility decision."""
    norm = lambda s: {re.sub(r"\s+", " ", x.strip().lower()) for x in re.split(r"[,;|\n]", s or "") if x.strip()}
    have, want = norm(student_skills), norm(preferred_skills)
    matched = sorted(have & want); missing = sorted(want - have)
    return {"score_pct": round(100 * len(matched) / len(want)) if want else None,
            "matched": matched, "missing": missing, "label": "Discovery signal only; not used for eligibility."}

def funnel_summary(applications: list[dict], events: list[dict] | None = None) -> dict:
    events = events or []
    current = {}
    for e in events: current[str(e.get("application_id"))] = str(e.get("stage", ""))
    stage_counts = Counter(current.values())
    if not current:
        stage_counts = Counter(str(a.get("stage", "Applied")) for a in applications)
    return {"applications": len(applications), "stages": dict(stage_counts),
            "offers": sum(1 for s in current.values() if s.lower() == "offer") if current else sum(1 for a in applications if str(a.get("stage", "")).lower() == "offer"),
            "selected": sum(1 for s in current.values() if s.lower() in {"offer", "accepted", "rejected offer"}) if current else sum(1 for a in applications if str(a.get("stage", "")).lower() in {"offer", "accepted", "rejected offer"})}

def descriptive_root_causes(rows: list[dict], min_group: int = 3) -> dict:
    """Summarize observed outcomes by cohort; associations are not causal claims."""
    cohorts: dict[str, list[dict]] = {}
    for row in rows:
        for dim in ("specialization", "experience_band", "communication_band"):
            value = str(row.get(dim, "Unknown") or "Unknown")
            cohorts.setdefault(dim, []).append({"value": value, "outcome": str(row.get("outcome", "unknown")).lower()})
    results = {}
    for dim, items in cohorts.items():
        groups: dict[str, list[str]] = {}
        for item in items: groups.setdefault(item["value"], []).append(item["outcome"])
        results[dim] = [{"group": k, "n": len(v), "offer_rate_pct": round(100*sum(x in {"offer", "accepted"} for x in v)/len(v), 1) if len(v) >= min_group else None,
                         "warning": None if len(v) >= min_group else f"Small sample (n<{min_group}); rate suppressed."} for k,v in sorted(groups.items())]
    return {"method": "Descriptive cohort comparison; associations only, not causal findings.", "dimensions": results}
