"""Small SQLite persistence layer for the MVP."""
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (student_id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT, specialization TEXT, graduation_pct REAL, pgdm_pct REAL, experience_years REAL, skills TEXT, profile_json TEXT DEFAULT '{}');
CREATE TABLE IF NOT EXISTS jobs (job_id TEXT PRIMARY KEY, company TEXT, title TEXT, jd_text TEXT, rules_json TEXT DEFAULT '{}', version INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS applications (application_id TEXT PRIMARY KEY, student_id TEXT, job_id TEXT, applied_at TEXT, stage TEXT DEFAULT 'Applied', non_application_reason TEXT, UNIQUE(student_id,job_id));
CREATE TABLE IF NOT EXISTS stage_events (event_id INTEGER PRIMARY KEY AUTOINCREMENT, application_id TEXT NOT NULL, stage TEXT NOT NULL, result TEXT, occurred_at TEXT DEFAULT CURRENT_TIMESTAMP, actor TEXT);
CREATE TABLE IF NOT EXISTS feedback (feedback_id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT, faculty_id TEXT, date TEXT, rubric_json TEXT, comments TEXT);
CREATE TABLE IF NOT EXISTS audit_log (audit_id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT, action TEXT, entity TEXT, entity_id TEXT, occurred_at TEXT DEFAULT CURRENT_TIMESTAMP);
"""
def connect(path="placement.db"):
    con = sqlite3.connect(path, check_same_thread=False); con.row_factory = sqlite3.Row
    con.executescript(SCHEMA); return con
