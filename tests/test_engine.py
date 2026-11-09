import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.engine import assess_eligibility, funnel_summary, descriptive_root_causes

def test_eligibility_pass_fail_missing():
    job={"graduation_min":60,"pgdm_min":65}
    assert assess_eligibility({"graduation_pct":70,"pgdm_pct":70},job)["classification"]=="eligible"
    assert assess_eligibility({"graduation_pct":50,"pgdm_pct":70},job)["classification"]=="ineligible"
    assert assess_eligibility({"graduation_pct":70},job)["classification"]=="needs-verification"

def test_stage_history_uses_latest_event():
    summary=funnel_summary([{"application_id":"A","stage":"Applied"}],[{"application_id":"A","stage":"Screening"},{"application_id":"A","stage":"GD"}])
    assert summary["stages"]=={"GD":1}

def test_small_cohort_rates_suppressed():
    report=descriptive_root_causes([{"specialization":"X","outcome":"offer"}])
    group=report["dimensions"]["specialization"][0]
    assert group["offer_rate_pct"] is None and group["warning"]
