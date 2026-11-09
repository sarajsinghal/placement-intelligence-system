import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.jd_reader import extract_from_rows, extract_from_text, normalize_candidate

def test_extract_labeled_pdf_text_and_normalize():
    fields=extract_from_text("Company: Acme\nJob Title: Analyst\nGraduation minimum: 60%\nPGDM cutoff: 65%\nMinimum experience: 2 years\nPreferred skills: SQL, Excel")
    result=normalize_candidate(fields)["fields"]
    assert result["company"]=="Acme" and result["title"]=="Analyst"
    assert result["graduation_min"]==60 and result["pgdm_min"]==65 and result["experience_min_years"]==2
    assert result["preferred_skills"]=="SQL, Excel"

def test_extract_spreadsheet_key_value_and_header_rows():
    rows=[["Company","Acme"],["Role Title","Analyst"],["PGDM Minimum","70%"],["Job ID","J-1"]]
    result=extract_from_rows(rows)
    assert result["company"]=="Acme" and result["title"]=="Analyst" and result["pgdm_min"]=="70%"

def test_bad_threshold_is_left_for_human_review():
    result=normalize_candidate({"graduation_min":"150%"})
    assert result["fields"]["graduation_min"] is None
    assert result["notes"]
