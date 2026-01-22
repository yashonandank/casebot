import sqlite3
import json
import base64
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
    provider: str = "anthropic"
) -> Dict:
    """
    Generate final feedback report for student.
    Returns report dict with scores, feedback, and evidence.
    """
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get checkpoint submissions
    cursor.execute("""
        SELECT checkpoint_key, submission_text, is_passed, score
        FROM checkpoint_submissions
        WHERE session_id = ?
        ORDER BY created_at
    """, (session_id,))
    
    checkpoint_submissions = [
        {
            "checkpoint_key": row[0],
            "submission_text": row[1],
            "is_passed": bool(row[2]),
            "score": row[3]
        }
        for row in cursor.fetchall()
    ]
    
    conn.close()
    
    # Get case and blueprint
    case = get_case(case_id)
    blueprint = get_latest_blueprint(case_id)
    
    if not case or not blueprint:
        raise ValueError("Invalid case or blueprint")
    
    # Get transcript (last 20 messages)
    transcript = get_session_transcript(session_id, limit=20)
    
    # Retrieve supporting evidence
    evidence_queries = [msg["content"] for msg in transcript[-5:] if msg["role"] == "student"]
    all_evidence = []
    for query in evidence_queries[:3]:  # Top 3 student messages
        retrieved = retrieve_chunks(case_id, query, top_k=3)
        all_evidence.extend(retrieved)
    
    # Remove duplicates
    seen = set()
    evidence = []
    for e in all_evidence:
        if e["chunk_id"] not in seen:
            evidence.append(e)
            seen.add(e["chunk_id"])
    
    # Generate report using LLM
    prompt = report_generator_prompt(
        blueprint,
        transcript,
        checkpoint_submissions,
        case.get("rubric", {}),
        evidence[:5]  # Top 5 pieces of evidence
    )
    
    llm = get_llm_client(provider)
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
            "next_steps": "Try again or contact instructor"
        }
    
    # Save report to DB
    cursor = sqlite3.connect(db_path).cursor()
    cursor.execute("""
        INSERT INTO reports (session_id, report_json)
        VALUES (?, ?)
    """, (session_id, json.dumps(report_data)))
    sqlite3.connect(db_path).commit()
    
    return report_data


def get_report(session_id: int) -> Optional[Dict]:
    """Retrieve saved report for a session."""
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT report_json, created_at FROM reports WHERE session_id = ?
    """, (session_id,))
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            "data": json.loads(result[0]),
            "created_at": result[1]
        }
    return None


def render_report_html(report: Dict, student_name: str = "Student") -> str:
    """Render report as HTML for display/export."""
    data = report.get("data", report)
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Case Performance Report</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 40px; color: #333; }}
            .header {{ border-bottom: 3px solid #0066cc; padding-bottom: 20px; margin-bottom: 30px; }}
            .header h1 {{ margin: 0; color: #0066cc; }}
            .header p {{ margin: 5px 0; color: #666; }}
            .section {{ margin-bottom: 30px; }}
            .section h2 {{ color: #0066cc; border-left: 4px solid #0066cc; padding-left: 10px; }}
            .scores {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin: 20px 0; }}
            .score-card {{ background: #f5f5f5; padding: 15px; border-radius: 5px; border-left: 4px solid #0066cc; }}
            .score-card .score-value {{ font-size: 28px; font-weight: bold; color: #0066cc; }}
            .score-card .score-label {{ font-size: 14px; color: #666; margin-top: 5px; }}
            .feedback {{ background: #f9f9f9; padding: 15px; margin: 10px 0; border-radius: 5px; border-left: 3px solid #ddd; }}
            .evidence {{ background: #f0f7ff; padding: 15px; margin: 10px 0; border-radius: 5px; font-size: 14px; }}
            .improvement {{ list-style: none; padding-left: 0; }}
            .improvement li {{ padding: 8px 0; padding-left: 25px; position: relative; }}
            .improvement li:before {{ content: "✓"; position: absolute; left: 0; color: #0066cc; font-weight: bold; }}
            .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; text-align: center; font-size: 12px; color: #999; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>📋 {data.get('title', 'Case Performance Report')}</h1>
            <p><strong>Student:</strong> {student_name}</p>
            <p><strong>Date:</strong> {datetime.now().strftime('%B %d, %Y')}</p>
        </div>
        
        <div class="section">
            <h2>Summary</h2>
            <p>{data.get('summary', 'No summary available.')}</p>
        </div>
        
        <div class="section">
            <h2>Overall Score</h2>
            <div style="font-size: 48px; font-weight: bold; color: #0066cc; text-align: center; padding: 20px;">
                {data.get('total_score', 0)}/100
            </div>
        </div>
    """
    
    # Category scores
    if data.get('scores'):
        html += """
        <div class="section">
            <h2>Category Breakdown</h2>
            <div class="scores">
        """
        for category, details in data.get('scores', {}).items():
            score_val = details.get('score', 0) if isinstance(details, dict) else details
            html += f"""
                <div class="score-card">
                    <div class="score-value">{score_val}</div>
                    <div class="score-label">{category}</div>
                    <p style="margin: 10px 0; font-size: 13px; color: #666;">{details.get('feedback', '') if isinstance(details, dict) else ''}</p>
                </div>
            """
        html += "</div></div>"
    
    # Decision quality
    if data.get('decision_quality'):
        html += f"""
        <div class="section">
            <h2>Decision Quality Analysis</h2>
            <div class="feedback">
                {data.get('decision_quality')}
            </div>
        </div>
        """
    
    # Improvements
    if data.get('improvement_areas'):
        html += """
        <div class="section">
            <h2>Areas for Improvement</h2>
            <ul class="improvement">
        """
        for item in data.get('improvement_areas', []):
            html += f"<li>{item}</li>"
        html += "</ul></div>"
    
    # Evidence
    if data.get('citations'):
        html += """
        <div class="section">
            <h2>Supporting Evidence</h2>
        """
        for cite in data.get('citations', [])[:3]:
            html += f"""
            <div class="evidence">
                <strong>Relevance:</strong> {cite.get('relevance', '')}<br>
                <strong>Reference:</strong> {cite.get('snippet', '')[:150]}...
            </div>
            """
        html += "</div>"
    
    # Next steps
    if data.get('next_steps'):
        html += f"""
        <div class="section">
            <h2>Next Steps</h2>
            <p>{data.get('next_steps')}</p>
        </div>
        """
    
    html += """
        <div class="footer">
            <p>This report was automatically generated by CaseSim.</p>
        </div>
    </body>
    </html>
    """
    
    return html


def export_report_html(report: Dict, student_name: str = "Student") -> bytes:
    """Export report as HTML bytes for download."""
    html = render_report_html(report, student_name)
    return html.encode('utf-8')
