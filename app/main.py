from __future__ import annotations
import io, json, sys
from pathlib import Path
import pandas as pd
import streamlit as st
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.engine import assess_eligibility, skill_match, funnel_summary, descriptive_root_causes
from core.jd_reader import extract_from_rows, extract_from_text, normalize_candidate
from core.pdf_ocr import extract_pdf_text
from core.storage import connect

st.set_page_config(page_title="Placement Intelligence", page_icon=":material/school:", layout="wide")
st.title("Placement intelligence", icon=":material/school:")
st.caption("A clearer view of student readiness, role fit, and placement progress")
st.badge("PGDM placement office", icon=":material/domain:", color="blue")
DB_PATH = str(ROOT / "placement.db")
con = connect(DB_PATH)

def current_students(): return pd.read_sql_query("SELECT * FROM students ORDER BY student_id", con)
def current_jobs(): return pd.read_sql_query("SELECT * FROM jobs ORDER BY job_id", con)
def current_apps(): return pd.read_sql_query("SELECT * FROM applications ORDER BY applied_at DESC", con)
def audit(action, entity, entity_id=""):
    con.execute("INSERT INTO audit_log(actor,action,entity,entity_id) VALUES(?,?,?,?)", (st.session_state.get("user","demo-user"),action,entity,str(entity_id))); con.commit()

with st.sidebar:
    st.subheader("Access")
    role=st.selectbox("Role",["Admin","Placement Team","Faculty","Student"])
    st.session_state.user=role
    st.caption("Demo role selector only. Production authentication and row-level permissions are not configured.")
    st.divider()
    st.markdown("**Data notice**\n\nUse synthetic or de-identified data in this MVP. Avoid sensitive/protected attributes.")

tabs=st.tabs([":material/dashboard: Overview",":material/group: Students & uploads",":material/work: Jobs & eligibility",":material/track_changes: Applications",":material/insights: Insights",":material/menu_book: Guide"],
             key="main_navigation")
with tabs[0]:
    students=current_students(); jobs=current_jobs(); apps=current_apps()
    st.subheader("Placement at a glance",icon=":material/insights:")
    filter_options=["All roles"]+(jobs.job_id.tolist() if len(jobs) else [])
    selected_job=st.selectbox("Filter by job",filter_options,format_func=lambda value: "All roles" if value=="All roles" else f"{value} · {jobs.loc[jobs.job_id==value,'title'].iloc[0]}",key="overview_job_filter")
    filtered_apps=apps if selected_job=="All roles" else apps[apps.job_id==selected_job] if len(apps) else apps
    offers=int(filtered_apps.stage.str.lower().isin(["offer","accepted"]).sum()) if len(filtered_apps) else 0
    a,b,c,d=st.columns(4)
    a.metric("Students",len(students),border=True); b.metric("Roles",len(jobs),border=True)
    c.metric("Applications",len(filtered_apps),border=True); d.metric("Offers",offers,border=True)
    if selected_job!="All roles" and len(students):
        selected=jobs[jobs.job_id==selected_job].iloc[0]
        rules=json.loads(selected.rules_json)
        eligible_ids={s["student_id"] for s in students.to_dict("records") if assess_eligibility(s,rules)["classification"]=="eligible"}
        applied_ids=set(filtered_apps.student_id.astype(str)) if len(filtered_apps) else set()
        eligible_applied=len(eligible_ids & applied_ids); eligible_not_applied=len(eligible_ids-applied_ids)
        e,f,g=st.columns(3)
        e.metric("Eligible students",len(eligible_ids),border=True)
        f.metric("Eligible applicants",eligible_applied,border=True)
        g.metric("Eligible non-applicants",eligible_not_applied,border=True)
        st.caption("Counts use saved mandatory rules. Students with missing evidence are excluded from the eligible count and need review.")
    view=st.segmented_control("Dashboard view",["Placement funnel","Application details"],default="Placement funnel",key="overview_view")
    if view=="Placement funnel":
        if len(filtered_apps):
            st.subheader("Current stage counts",icon=":material/bar_chart:")
            stage_counts=filtered_apps.groupby("stage").size().sort_values(ascending=False)
            st.bar_chart(stage_counts,color="#137C78")
            st.caption("Each application appears at its current recorded stage.")
        else: st.info("Record an application to see the placement funnel.")
    elif len(filtered_apps):
        st.subheader("Applications",icon=":material/table_view:")
        if len(jobs)>1 and selected_job=="All roles":
            chosen_stages=st.multiselect("Filter stages",sorted(filtered_apps.stage.dropna().unique()),default=sorted(filtered_apps.stage.dropna().unique()),key="overview_stage_filter")
            filtered_apps=filtered_apps[filtered_apps.stage.isin(chosen_stages)]
        st.dataframe(filtered_apps,width="stretch",hide_index=True)
    else: st.info("No applications match this role filter yet.")
    st.caption("Dashboard refreshes when you change a filter or update a record.")

with tabs[1]:
    st.subheader("Upload & validate")
    kind=st.selectbox("Dataset",["Student profiles","Student profiles (PDF/resume)","Resumes (PDF)","Faculty feedback","Job descriptions","Applications","Selection results"])
    files=st.file_uploader("Choose CSV, XLSX or PDF files",type=["csv","xlsx","pdf"],accept_multiple_files=True,key="upload")
    if files:
        for f in files:
            try:
                if f.name.lower().endswith(".pdf"):
                    pdf_result=extract_pdf_text(f.getvalue())
                    extracted=pdf_result.text
                    st.write(f"**{f.name}** · {pdf_result.page_count} page(s) · {len(extracted)} text characters")
                    st.caption(pdf_result.message)
                    if kind=="Student profiles (PDF/resume)":
                        st.text_area("Resume/profile text preview",extracted[:5000],key=f"profile-pdf-{f.name}")
                        st.caption("OCR makes scanned profile text readable for review. It does not automatically create or change a student record.")
                    else:
                        st.text_area("Extracted PDF text preview",extracted[:5000],key=f"dataset-pdf-{f.name}")
                else:
                    df=pd.read_csv(f) if f.name.lower().endswith(".csv") else pd.read_excel(f)
                    st.write(f"**{f.name}** · {len(df)} rows · {len(df.columns)} columns")
                    st.dataframe(df.head(100),width="stretch",hide_index=True)
                    if kind=="Student profiles":
                        required={"student_id","name"}; missing=required-set(df.columns)
                        if missing: st.error("Required columns missing: "+", ".join(sorted(missing)))
                        else:
                            duplicates=df[df.duplicated("student_id",keep=False)]
                            if len(duplicates): st.warning(f"Duplicate student IDs found: {duplicates.student_id.astype(str).unique().tolist()}")
                            if st.button(f"Import {f.name}",key="import"+f.name):
                                imported=0
                                for row in df.to_dict("records"):
                                    sid=str(row.get("student_id","")).strip()
                                    if not sid: continue
                                    con.execute("INSERT INTO students(student_id,name,email,specialization,graduation_pct,pgdm_pct,experience_years,skills,profile_json) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(student_id) DO UPDATE SET name=excluded.name,email=excluded.email,specialization=excluded.specialization,graduation_pct=excluded.graduation_pct,pgdm_pct=excluded.pgdm_pct,experience_years=excluded.experience_years,skills=excluded.skills,profile_json=excluded.profile_json",(sid,str(row.get("name","")),row.get("email"),row.get("specialization"),row.get("graduation_pct"),row.get("pgdm_pct"),row.get("experience_years"),str(row.get("skills","")),json.dumps({k:v for k,v in row.items() if k not in {"student_id","name","email","specialization","graduation_pct","pgdm_pct","experience_years","skills"}},default=str)))
                                    imported+=1
                                con.commit(); audit("import","students",f.name); st.success(f"Imported/updated {imported} student records.")
            except Exception as e: st.error(f"Could not read {f.name}: {e}")
    sample_profiles=ROOT/"data"/"demo_student_profiles.csv"
    if sample_profiles.exists():
        if st.button("Load local sample records"):
            profile_df=pd.read_csv(sample_profiles)
            for row in profile_df.to_dict("records"):
                con.execute("INSERT OR REPLACE INTO students(student_id,name,email,specialization,graduation_pct,pgdm_pct,experience_years,skills) VALUES(?,?,?,?,?,?,?,?)",(str(row.get("student_id","")),str(row.get("name","")),row.get("email"),row.get("specialization"),row.get("graduation_pct"),row.get("pgdm_pct"),row.get("experience_years"),str(row.get("skills", ""))))
            job_file=ROOT/"data"/"demo_job_descriptions.csv"
            if job_file.exists():
                for row in pd.read_csv(job_file).to_dict("records"):
                    rules={key:row.get(key) for key in ("graduation_min","pgdm_min","experience_min_years","specialization","preferred_skills")}
                    rules={key:(None if pd.isna(value) else value) for key,value in rules.items()}
                    con.execute("INSERT OR REPLACE INTO jobs(job_id,company,title,jd_text,rules_json,version) VALUES(?,?,?,?,?,1)",(str(row.get("job_id","")),row.get("company"),row.get("title"),row.get("jd_text",""),json.dumps(rules)))
            applications_file=ROOT/"data"/"demo_applications.csv"
            if applications_file.exists():
                for row in pd.read_csv(applications_file).to_dict("records"):
                    con.execute("INSERT OR IGNORE INTO applications(application_id,student_id,job_id,applied_at,stage) VALUES(?,?,?,?,?)",(str(row.get("application_id","")),str(row.get("student_id","")),str(row.get("job_id","")),str(row.get("applied_at","")),str(row.get("stage","Applied"))))
            results_file=ROOT/"data"/"demo_selection_results.csv"
            if results_file.exists():
                for row in pd.read_csv(results_file).to_dict("records"):
                    con.execute("INSERT INTO stage_events(application_id,stage,result,occurred_at,actor) VALUES(?,?,?,?,?)",(str(row.get("application_id","")),str(row.get("stage","")),str(row.get("result","")),str(row.get("occurred_at","")),"local-sample"))
            con.commit(); audit("load-local-samples","workspace"); st.success("Loaded local sample records."); st.rerun()
    else:
        st.caption("No local sample records are installed. Upload approved files to populate this workspace.")
    st.subheader("Student master")
    st.dataframe(current_students(),width="stretch",hide_index=True)
    with st.expander("Supported dataset templates"):
        st.code("Student profiles: student_id,name,email,specialization,graduation_pct,pgdm_pct,experience_years,skills\nApplications: application_id,student_id,job_id,applied_at,stage\nFaculty feedback: student_id,faculty_id,date,communication,teamwork,comments\nSelection results: application_id,stage,result,occurred_at\nJD: job_id,company,title,jd_text,graduation_min,pgdm_min,experience_min_years,specialization,preferred_skills")

with tabs[2]:
    st.subheader("Job description & versioned rules")
    job_tabs=st.tabs(["Upload JD & extract","Manual entry & eligibility"])
    with job_tabs[0]:
        st.markdown("Upload a JD and the **JD Reader Agent** will propose fields for review. It runs locally with pattern and table extraction; it does not call an external LLM and does not determine student eligibility.")
        jd_file=st.file_uploader("Upload job description",type=["pdf","xlsx","csv"],key="jd_reader_upload")
        if jd_file:
            try:
                extracted_text=""
                raw_fields={}
                if jd_file.name.lower().endswith(".pdf"):
                    pdf_result=extract_pdf_text(jd_file.getvalue())
                    extracted_text=pdf_result.text
                    st.caption(f"Read {pdf_result.page_count} PDF page(s). {pdf_result.message}")
                    if not extracted_text.strip():
                        st.error("No readable text was extracted. Check the PDF quality or enter the details manually.")
                    else:
                        raw_fields=extract_from_text(extracted_text)
                        with st.expander("Show extracted JD text"):
                            st.text(extracted_text[:12000])
                else:
                    frame=pd.read_csv(jd_file) if jd_file.name.lower().endswith(".csv") else pd.read_excel(jd_file)
                    st.write("JD spreadsheet preview")
                    st.dataframe(frame.head(100),width="stretch",hide_index=True)
                    raw_fields=extract_from_rows([frame.columns.tolist()]+frame.fillna("").values.tolist())
                    extracted_text=frame.to_csv(index=False)
                candidate=normalize_candidate(raw_fields)
                suggested=candidate["fields"]
                if candidate["notes"]:
                    for note in candidate["notes"]: st.warning(note)
                if not raw_fields and extracted_text.strip():
                    st.warning("The reader did not confidently recognize any supported JD fields. Review and enter the fields below.")
                st.subheader("Review extracted details")
                st.caption("Every field is editable. Confirm the JD and mandatory criteria before saving.")
                with st.form("jd_extraction_review"):
                    r1,r2=st.columns(2)
                    review_id=r1.text_input("Job ID",value=str(suggested.get("job_id") or ""))
                    review_company=r2.text_input("Company",value=str(suggested.get("company") or ""))
                    review_title=r1.text_input("Role title",value=str(suggested.get("title") or ""))
                    review_spec=r2.text_input("Mandatory specialization (optional)",value=str(suggested.get("specialization") or ""))
                    r3,r4,r5=st.columns(3)
                    review_grad=r3.number_input("Graduation minimum (%)",0.0,100.0,float(suggested.get("graduation_min") or 0.0),key="extract_grad")
                    review_pgdm=r4.number_input("PGDM minimum (%)",0.0,100.0,float(suggested.get("pgdm_min") or 0.0),key="extract_pgdm")
                    review_exp=r5.number_input("Minimum experience (years)",0.0,50.0,float(suggested.get("experience_min_years") or 0.0),key="extract_exp")
                    review_skills=st.text_input("Preferred skills",value=str(suggested.get("preferred_skills") or ""))
                    review_jd=st.text_area("Full JD text",value=extracted_text[:20000],height=180)
                    confirmed=st.checkbox("I reviewed these extracted fields against the original JD",key="jd_review_confirmed")
                    save_extracted=st.form_submit_button("Save reviewed job")
                if save_extracted:
                    if not confirmed: st.error("Review and confirm the extracted fields before saving.")
                    elif not review_id.strip() or not review_title.strip(): st.error("Job ID and role title are required.")
                    else:
                        old=con.execute("SELECT version FROM jobs WHERE job_id=?",(review_id.strip(),)).fetchone(); ver=(old[0]+1) if old else 1
                        rules={"graduation_min":review_grad or None,"pgdm_min":review_pgdm or None,"experience_min_years":review_exp or None,"specialization":review_spec.strip(),"preferred_skills":review_skills}
                        con.execute("INSERT OR REPLACE INTO jobs(job_id,company,title,jd_text,rules_json,version) VALUES(?,?,?,?,?,?)",(review_id.strip(),review_company.strip(),review_title.strip(),review_jd,json.dumps(rules),ver)); con.commit(); audit("save-extracted-role","job",review_id.strip()); st.success(f"Reviewed job saved as rule version {ver}.")
            except Exception as e: st.error(f"Could not read this JD file: {e}")
        else: st.info("Supported formats: PDF, XLSX, and CSV. PDF OCR runs locally when the optional Python packages, Poppler, and Tesseract are installed.")
    with job_tabs[1]:
        st.subheader("Enter or edit job manually")
        with st.form("jobform"):
            jid=st.text_input("Job ID"); company=st.text_input("Company"); title=st.text_input("Role title"); jd=st.text_area("JD text"); x,y,z=st.columns(3)
            grad=x.number_input("Mandatory graduation minimum (%)",0.0,100.0,0.0); pgdm=y.number_input("Mandatory PGDM minimum (%)",0.0,100.0,0.0); exp=z.number_input("Minimum experience (years)",0.0,50.0,0.0)
            spec=st.text_input("Mandatory specialization (optional)"); pref=st.text_input("Preferred skills (comma separated)")
            if st.form_submit_button("Save role"):
                if not jid or not title: st.error("Job ID and role title are required.")
                else:
                    old=con.execute("SELECT version FROM jobs WHERE job_id=?",(jid,)).fetchone(); ver=(old[0]+1) if old else 1
                    rules={"graduation_min":grad or None,"pgdm_min":pgdm or None,"experience_min_years":exp or None,"specialization":spec,"preferred_skills":pref}
                    con.execute("INSERT OR REPLACE INTO jobs(job_id,company,title,jd_text,rules_json,version) VALUES(?,?,?,?,?,?)",(jid,company,title,jd,json.dumps(rules),ver)); con.commit(); audit("save-role","job",jid); st.success(f"Saved rule version {ver}.")
    jobs=current_jobs(); students=current_students()
    if len(jobs): st.dataframe(jobs[["job_id","company","title","version"]],width="stretch",hide_index=True)
    if len(jobs) and len(students):
        st.subheader("Check student eligibility",icon=":material/fact_check:")
        job_id=st.selectbox("Choose a role to assess",jobs.job_id.tolist(),format_func=lambda value: f"{value} · {jobs.loc[jobs.job_id==value,'title'].iloc[0]}"); job=jobs[jobs.job_id==job_id].iloc[0]; rules=json.loads(job.rules_json)
        results=[]
        for s in students.to_dict("records"):
            result=assess_eligibility(s,rules); match=skill_match(str(s.get("skills") or ""),str(rules.get("preferred_skills") or ""))
            results.append({"student_id":s["student_id"],"name":s["name"],"classification":result["classification"],"explanation":result["explanation"],"skill_match_pct":match["score_pct"],"matched_skills":", ".join(match["matched"]),"missing_skills":", ".join(match["missing"])})
        result_df=pd.DataFrame(results)
        eligible_count=int((result_df.classification=="eligible").sum())
        needs_review_count=int((result_df.classification=="needs-verification").sum())
        ineligible_count=int((result_df.classification=="ineligible").sum())
        e,f,g=st.columns(3)
        e.metric("Eligible",eligible_count,border=True); f.metric("Needs review",needs_review_count,border=True); g.metric("Not eligible",ineligible_count,border=True)
        left,right=st.columns([2,1])
        with left: search=st.text_input("Find a student",placeholder="Search by name or student ID",key="eligibility_search",type="search")
        with right: classes=st.multiselect("Show classifications",["eligible","needs-verification","ineligible"],default=["eligible","needs-verification","ineligible"],key="eligibility_class_filter")
        visible=result_df[result_df.classification.isin(classes)]
        if search.strip(): visible=visible[visible.name.str.contains(search.strip(),case=False,na=False)|visible.student_id.astype(str).str.contains(search.strip(),case=False,na=False)]
        st.dataframe(visible,width="stretch",hide_index=True)
        st.caption("Eligibility uses mandatory thresholds only. Skill overlap is separate and is not an eligibility or ranking decision.")
        st.download_button("Download eligibility CSV",result_df.to_csv(index=False),"eligibility.csv","text/csv",icon=":material/download:")

with tabs[3]:
    st.subheader("Applications & stage events")
    apps=current_apps(); students=current_students(); jobs=current_jobs()
    if len(students) and len(jobs):
        with st.form("appform"):
            student_id=st.selectbox("Student",students.student_id.tolist()); job_id=st.selectbox("Job",jobs.job_id.tolist()); app_id=st.text_input("Application ID"); stage=st.selectbox("Stage",["Applied","Screening","GD","PI1","PI2","Offer","Accepted","Rejected","Withdrawn"])
            if st.form_submit_button("Record nomination"):
                try:
                    con.execute("INSERT INTO applications(application_id,student_id,job_id,applied_at,stage) VALUES(?,?,?,?,?)",(app_id,student_id,job_id,pd.Timestamp.now().isoformat(),stage)); con.execute("INSERT INTO stage_events(application_id,stage,actor) VALUES(?,?,?)",(app_id,stage,role)); con.commit(); audit("nomination","application",app_id); st.success("Nomination recorded."); st.rerun()
                except Exception as e: st.error(f"Not saved. Check duplicate nomination or identifiers: {e}")
    if len(apps):
        st.dataframe(apps,width="stretch",hide_index=True)
        selected=st.selectbox("Update stage",apps.application_id.tolist()); new_stage=st.selectbox("New stage",["Applied","Screening","GD","PI1","PI2","Offer","Accepted","Rejected","Withdrawn"],key="newstage"); result=st.text_input("Outcome / note (optional)")
        if st.button("Add stage event"):
            con.execute("INSERT INTO stage_events(application_id,stage,result,actor) VALUES(?,?,?,?)",(selected,new_stage,result,role)); con.execute("UPDATE applications SET stage=? WHERE application_id=?",(new_stage,selected)); con.commit(); audit("stage-update","application",selected); st.success("Stage history updated."); st.rerun()
        events=[dict(r) for r in con.execute("SELECT application_id,stage FROM stage_events ORDER BY occurred_at,event_id")]
        st.json(funnel_summary(apps.to_dict("records"),events))
    else: st.info("Add a student, job, and nomination to track a selection funnel.")

with tabs[4]:
    st.subheader("Evidence-based cohort review")
    rows=[]
    if len(apps):
        for app in apps.to_dict("records"):
            s=con.execute("SELECT * FROM students WHERE student_id=?",(app["student_id"],)).fetchone()
            if s:
                d=dict(s); d.update(outcome=app.get("stage","unknown"),experience_band="Prior experience" if (d.get("experience_years") or 0)>0 else "No prior experience")
                rows.append(d)
    if rows:
        report=descriptive_root_causes(rows)
        st.write(report["method"])
        for dim,items in report["dimensions"].items(): st.markdown(f"**{dim.replace('_',' ').title()}**"); st.dataframe(pd.DataFrame(items),width="stretch",hide_index=True)
        st.info("These comparisons describe observed cohorts. Small samples are flagged; they do not establish why a selection outcome occurred.")
        st.download_button("Download cohort summary JSON",json.dumps(report,indent=2),"cohort_summary.json","application/json")
    else: st.info("Application outcome data is needed for cohort comparisons.")
    st.subheader("Suggested development actions")
    st.markdown("- Use faculty feedback and mock interview rubrics to identify skills for coaching.\n- Compare stage-specific outcomes before planning training.\n- Validate every recommendation with faculty and the student; avoid ranking on protected traits.")

with tabs[5]:
    st.subheader("Integration status")
    st.markdown("**Available now:** local CSV/XLSX import preview, basic PDF text extraction, SQLite persistence, deterministic eligibility, skill overlap, application stage history, and CSV/JSON exports.\n\n**Scaffolded, requires configuration:** Google Forms/Sheets OAuth/API connector and external model adapter. No API key is assumed. OCR is not configured. No LLM decides eligibility.")
    st.markdown("**Suggested Google workflow:** create or select a Forms response destination in Sheets, configure OAuth consent and Forms/Sheets API access, store credentials outside source control, then map response columns to student_id, job_id, and nomination fields. Validate student IDs before importing.")
    st.subheader("Privacy & governance")
    st.markdown("- Use role-based accounts in production; the selector here is a demo scaffold only.\n- Minimize collected fields and define retention/deletion rules.\n- Restrict resume and feedback access; log data imports and stage changes.\n- Exclude protected or sensitive attributes from eligibility and matching.\n- Route missing/conflicting records to human review.\n- Never treat this tool as an automatic hiring decision system.")
    st.subheader("Audit log")
    st.dataframe(pd.read_sql_query("SELECT * FROM audit_log ORDER BY occurred_at DESC LIMIT 100",con),width="stretch",hide_index=True)
