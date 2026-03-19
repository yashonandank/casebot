import sqlite3
import json
from datetime import datetime
from typing import Dict, Optional
from llm_client import get_llm_client
from prompts import report_generator_prompt
from case_manager import get_case, get_latest_blueprint
from simulation import get_session_transcript
from retrieval import retrieve_chunks


def generate_report(
    session_id: int,
    case_id: int,
    student_id: int,
) -> Dict:
    """Generate final feedback report. Returns report dict."""
    db_path = "data/db/casesim.db"

    # Get checkpoint submissions
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT checkpoint_key, submission_text, is_passed, score, feedback
        FROM checkpoint_submissions WHERE session_id = ?
        ORDER BY created_at
    """, (session_id,))
    checkpoint_submissions = [
        {
            "checkpoint_key": r[0], "submission_text": r[1],
            "is_passed": bool(r[2]), "score": r[3], "feedback": r[4],
        }
        for r in cursor.fetchall()
    ]
    conn.close()

    case = get_case(case_id)
    blueprint = get_latest_blueprint(case_id)
    if not case or not blueprint:
        raise ValueError("Invalid case or blueprint")

    transcript = get_session_transcript(session_id, limit=20)

    # Gather evidence from recent student messages
    student_msgs = [m["content"] for m in transcript if m["role"] == "student"]
    all_evidence = []
    seen_ids = set()
    for query in student_msgs[-3:]:
        for chunk in retrieve_chunks(case_id, query, top_k=3):
            if chunk["chunk_id"] not in seen_ids:
                all_evidence.append(chunk)
                seen_ids.add(chunk["chunk_id"])

    prompt = report_generator_prompt(
        blueprint, transcript, checkpoint_submissions,
        case.get("rubric", {}), all_evidence[:5]
    )

    llm = get_llm_client()
    try:
        report_data = llm.generate_json(prompt)
    except Exception as e:
        report_data = {
            "title": "Case Performance Report",
            "summary": f"Report generation encountered an error: {str(e)}",
            "scores": {},
            "total_score": 0,
            "decision_quality": "Unable to assess",
            "improvement_areas": ["Complete the case without errors"],
            "citations": [],
            "next_steps": "Contact your instructor.",
        }

    # Save report — fixed: keep connection open until commit
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO reports (session_id, report_json)
        VALUES (?, ?)
    """, (session_id, json.dumps(report_data)))
    conn.commit()
    conn.close()

    return report_data


def get_report(session_id: int) -> Optional[Dict]:
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT report_json, created_at FROM reports WHERE session_id = ?",
        (session_id,)
    )
    result = cursor.fetchone()
    conn.close()
    if result:
        return {"data": json.loads(result[0]), "created_at": result[1]}
    return None


def render_report_html(report: Dict, student_name: str = "Student") -> str:
    data = report.get("data", report)
    total = data.get("total_score", 0)

    scores_html = ""
    if data.get("scores"):
        scores_html = "<div class='scores'>"
        for cat, details in data["scores"].items():
            score_val = details.get("score", 0) if isinstance(details, dict) else details
            fb = details.get("feedback", "") if isinstance(details, dict) else ""
            scores_html += f"""
            <div class='score-card'>
                <div class='score-val'>{score_val}</div>
                <div class='score-label'>{cat}</div>
                <p class='score-fb'>{fb}</p>
            </div>"""
        scores_html += "</div>"

    improvements_html = ""
    for item in data.get("improvement_areas", []):
        improvements_html += f"<li>{item}</li>"

    citations_html = ""
    for cite in data.get("citations", [])[:3]:
        citations_html += f"""
        <div class='evidence'>
            <strong>{cite.get('relevance','')}</strong><br>
            <span class='snippet'>{cite.get('snippet','')[:200]}</span>
        </div>"""

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset='UTF-8'>
<title>Case Performance Report</title>
<style>
  body{{font-family:'Segoe UI',sans-serif;margin:40px;color:#333;background:#fdfcf7}}
  .header{{border-bottom:3px solid #2c2c2c;padding-bottom:20px;margin-bottom:30px}}
  .header h1{{margin:0;color:#2c2c2c;font-size:1.8rem}}
  .header p{{margin:4px 0;color:#666;font-size:.9rem}}
  .section{{margin-bottom:30px}}
  .section h2{{color:#2c2c2c;border-left:4px solid #2c2c2c;padding-left:10px;font-size:1.2rem}}
  .total-score{{font-size:56px;font-weight:700;color:#2c2c2c;text-align:center;padding:20px}}
  .scores{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;margin:16px 0}}
  .score-card{{background:#f5f0e8;padding:16px;border-radius:4px;border-left:4px solid #8b8680}}
  .score-val{{font-size:2rem;font-weight:700;color:#2c2c2c}}
  .score-label{{font-size:.8rem;color:#6a6460;text-transform:uppercase;letter-spacing:.5px;margin:4px 0}}
  .score-fb{{margin:8px 0 0;font-size:.85rem;color:#5a5a5a}}
  .feedback{{background:#f9f4ed;border-left:2px solid #8b8680;padding:12px 16px;margin:10px 0;border-radius:2px}}
  .evidence{{background:#f5f0e8;padding:12px;margin:8px 0;border-radius:4px;font-size:.88rem}}
  .snippet{{color:#666;font-style:italic}}
  ul{{padding-left:1.2rem}}
  li{{margin:6px 0}}
  .footer{{margin-top:40px;padding-top:16px;border-top:1px solid #e0d7ca;text-align:center;font-size:.8rem;color:#999}}
</style>
</head>
<body>
<div class='header'>
  <h1>{data.get('title','Case Performance Report')}</h1>
  <p><strong>Student:</strong> {student_name}</p>
  <p><strong>Date:</strong> {datetime.now().strftime('%B %d, %Y')}</p>
</div>

<div class='section'>
  <h2>Summary</h2>
  <p>{data.get('summary','')}</p>
</div>

<div class='section'>
  <h2>Overall Score</h2>
  <div class='total-score'>{total}<span style='font-size:1.2rem;color:#8b8680'>/100</span></div>
</div>

{'<div class="section"><h2>Category Breakdown</h2>' + scores_html + '</div>' if scores_html else ''}

{'<div class="section"><h2>Decision Quality</h2><div class="feedback">' + data.get("decision_quality","") + '</div></div>' if data.get("decision_quality") else ''}

{'<div class="section"><h2>Areas for Improvement</h2><ul>' + improvements_html + '</ul></div>' if improvements_html else ''}

{'<div class="section"><h2>Supporting Evidence</h2>' + citations_html + '</div>' if citations_html else ''}

{'<div class="section"><h2>Next Steps</h2><p>' + data.get("next_steps","") + '</p></div>' if data.get("next_steps") else ''}

<div class='footer'>Generated by CaseSim · Goizueta Business School</div>
</body>
</html>"""


def export_report_html(report: Dict, student_name: str = "Student") -> bytes:
    return render_report_html(report, student_name).encode("utf-8")
