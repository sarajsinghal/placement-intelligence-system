"""Offline JD extraction agent: proposes fields from PDF text or Excel tables.

This agent extracts candidate facts only. It does not decide eligibility and it
never saves a role without a human confirming the reviewed form.
"""
from __future__ import annotations
import re
from typing import Any

FIELDS = {
    "job_id": ["job id", "job_id", "requisition id", "role id"],
    "company": ["company", "company name", "organization", "organisation", "employer"],
    "title": ["job title", "role title", "position", "designation", "title"],
    "graduation_min": ["graduation minimum", "minimum graduation", "graduation cutoff", "graduation_min", "ug cutoff"],
    "pgdm_min": ["pgdm minimum", "minimum pgdm", "pgdm cutoff", "pgdm_min", "mba cutoff"],
    "experience_min_years": ["minimum experience", "experience minimum", "experience_min_years", "min experience"],
    "specialization": ["specialization", "specialisation", "eligible specialization"],
    "preferred_skills": ["preferred skills", "required skills", "skills", "key skills", "competencies"],
}

def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()

def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _clean(value).lower()).strip()

def extract_from_rows(rows: list[list[Any]]) -> dict:
    """Extract from label/value rows or tabular header columns."""
    values: dict[str, Any] = {}
    for row in rows:
        if not row: continue
        cells = [_clean(c) for c in row]
        if len(cells) >= 2:
            label = _key(cells[0])
            for field, aliases in FIELDS.items():
                if any(label == _key(alias) for alias in aliases) and cells[1]:
                    values.setdefault(field, cells[1])
    # Header + data table mapping; all columns in the first row are considered.
    if len(rows) >= 2:
        headers = [_key(c) for c in rows[0]]
        for field, aliases in FIELDS.items():
            for alias in aliases:
                if _key(alias) in headers:
                    idx = headers.index(_key(alias))
                    if idx < len(rows[1]) and _clean(rows[1][idx]): values.setdefault(field, _clean(rows[1][idx]))
    return values

def extract_from_text(text: str) -> dict:
    """Extract conservative label/value candidates from common JD wording."""
    values: dict[str, Any] = {}
    lines = [_clean(line) for line in text.splitlines() if _clean(line)]
    label_regex = {
        "job_id": r"(?:job|requisition|role)\s*id",
        "company": r"(?:company|organization|organisation|employer)(?:\s*name)?",
        "title": r"(?:job\s*title|role\s*title|position|designation)",
        "graduation_min": r"(?:graduation|graduate|ug)\s*(?:minimum|min\.?|cut.?off|percentage|aggregate)?",
        "pgdm_min": r"(?:pgdm|mba)\s*(?:minimum|min\.?|cut.?off|percentage|aggregate)?",
        "experience_min_years": r"(?:minimum|min\.?)\s*(?:work\s*)?experience",
        "specialization": r"(?:eligible\s*)?speciali[sz]ation",
        "preferred_skills": r"(?:preferred|required|key)?\s*skills|competencies",
    }
    for line in lines:
        for field, label in label_regex.items():
            m = re.match(rf"^\s*{label}\s*[:\-]\s*(.+)$", line, flags=re.I)
            if m and m.lastindex: values.setdefault(field, m.group(1).strip())
    # Natural phrasing for experience; keep extraction narrow and mark provenance.
    for line in lines:
        m = re.search(r"(?:minimum|min\.? of)\s+(\d+(?:\.\d+)?)\s*(?:years?|yrs?)\s+(?:of\s+)?(?:work\s+)?experience", line, re.I)
        if m: values.setdefault("experience_min_years", m.group(1))
    return values

def normalize_candidate(raw: dict) -> dict:
    """Normalize known values and return explicit confidence/provenance notes."""
    out = {"job_id": "", "company": "", "title": "", "jd_text": "", "graduation_min": None,
           "pgdm_min": None, "experience_min_years": None, "specialization": "", "preferred_skills": ""}
    out.update(raw)
    notes=[]
    for field, label, maximum in [("graduation_min","Graduation threshold",100),("pgdm_min","PGDM threshold",100),("experience_min_years","Experience minimum",50)]:
        val=out.get(field)
        if val is None or _clean(val)=="": out[field]=None; continue
        match=re.search(r"-?\d+(?:\.\d+)?",_clean(val))
        if not match: notes.append(f"{label}: could not parse '{val}'; review manually."); out[field]=None; continue
        n=float(match.group())
        if n<0 or n>maximum: notes.append(f"{label}: value {n:g} is outside the expected range; review manually."); out[field]=None
        else: out[field]=n
    if out.get("job_id"): out["job_id"]=_clean(out["job_id"])
    if out.get("company"): out["company"]=_clean(out["company"])
    if out.get("title"): out["title"]=_clean(out["title"])
    if out.get("specialization"): out["specialization"]=_clean(out["specialization"])
    if out.get("preferred_skills"): out["preferred_skills"]=_clean(out["preferred_skills"])
    return {"fields":out,"notes":notes}
