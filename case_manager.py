import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Optional
from ingest import ingest_case_file, get_case_chunks
from llm_client import get_llm_client
from prompts import blueprint_generator_prompt


def create_case(
    professor_id: int,
    title: str,
    course: str,
    instructions_text: str,
    objectives: List[str],
    checkpoints: List[Dict],
    rubric: Dict,
    hint_policy: str,
) -> int:
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO cases (
            professor_id, title, course, instructions_text,
            objectives_json, checkpoints_json, rubric_json, hint_policy, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft')
    """, (
        professor_id, title, course, instructions_text,
        json.dumps(objectives), json.dumps(checkpoints),
        json.dumps(rubric), hint_policy,
    ))
    case_id = cursor.lastrowid
    conn.commit()
    conn.close()
    log_audit("create_case", "cases", case_id, professor_id, {"title": title})
    return case_id


def upload_case_file(case_id: int, uploaded_file) -> str:
    os.makedirs("data/uploads", exist_ok=True)
    file_ext = os.path.splitext(uploaded_file.name)[1]
    file_path = f"data/uploads/case_{case_id}_{int(datetime.now().timestamp())}{file_ext}"
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE cases SET upload_path = ? WHERE id = ?", (file_path, case_id))
    conn.commit()
    conn.close()
    return file_path


def generate_blueprint(case_id: int, professor_id: int) -> Dict:
    """
    Generate blueprint using ALL case chunks (not just first 5).
    """
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT upload_path, instructions_text, checkpoints_json, rubric_json
        FROM cases WHERE id = ?
    """, (case_id,))
    case_data = cursor.fetchone()
    conn.close()

    if not case_data:
        raise ValueError(f"Case {case_id} not found")

    upload_path, instructions, checkpoints_json, rubric_json = case_data

    if not upload_path or not os.path.exists(upload_path):
        raise ValueError("Case file not found. Upload a file first.")

    # Ingest (embed) all chunks
    num_chunks, chunks = ingest_case_file(case_id, upload_path)

    # Use ALL chunks for blueprint (concatenated, capped at ~12k chars for prompt)
    all_text_parts = [c["content"] for c in chunks]
    extracted_text = "\n---\n".join(all_text_parts)
    if len(extracted_text) > 12000:
        extracted_text = extracted_text[:12000] + "\n\n[...text continues...]"

    checkpoints = json.loads(checkpoints_json or "[]")
    rubric = json.loads(rubric_json or "{}")

    llm = get_llm_client()
    prompt = blueprint_generator_prompt(instructions, checkpoints, rubric, extracted_text)

    try:
        blueprint = llm.generate_json(prompt)
    except Exception as e:
        raise ValueError(f"Blueprint generation failed: {str(e)}")

    # Save
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO case_blueprints (case_id, version, blueprint_json, created_by)
        VALUES (?, 1, ?, 'ai')
    """, (case_id, json.dumps(blueprint)))
    conn.commit()
    conn.close()

    log_audit("generate_blueprint", "case_blueprints", case_id, professor_id, {})
    return blueprint


def get_latest_blueprint(case_id: int) -> Optional[Dict]:
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT blueprint_json FROM case_blueprints
        WHERE case_id = ? ORDER BY version DESC LIMIT 1
    """, (case_id,))
    result = cursor.fetchone()
    conn.close()
    return json.loads(result[0]) if result else None


def save_blueprint_version(case_id: int, blueprint: Dict, professor_id: int) -> int:
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COALESCE(MAX(version), 0) FROM case_blueprints WHERE case_id = ?",
        (case_id,)
    )
    new_version = cursor.fetchone()[0] + 1
    cursor.execute("""
        INSERT INTO case_blueprints (case_id, version, blueprint_json, created_by)
        VALUES (?, ?, ?, 'professor')
    """, (case_id, new_version, json.dumps(blueprint)))
    conn.commit()
    conn.close()
    log_audit("update_blueprint", "case_blueprints", case_id, professor_id, {})
    return new_version


def get_professor_cases(professor_id: int) -> List[Dict]:
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, course, status, created_at, updated_at
        FROM cases WHERE professor_id = ? ORDER BY updated_at DESC
    """, (professor_id,))
    cases = [
        {"id": r[0], "title": r[1], "course": r[2],
         "status": r[3], "created_at": r[4], "updated_at": r[5]}
        for r in cursor.fetchall()
    ]
    conn.close()
    return cases


def get_case(case_id: int) -> Optional[Dict]:
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, professor_id, title, course, instructions_text,
               objectives_json, checkpoints_json, rubric_json, hint_policy, status, created_at
        FROM cases WHERE id = ?
    """, (case_id,))
    r = cursor.fetchone()
    conn.close()
    if r:
        return {
            "id": r[0], "professor_id": r[1], "title": r[2], "course": r[3],
            "instructions_text": r[4],
            "objectives": json.loads(r[5] or "[]"),
            "checkpoints": json.loads(r[6] or "[]"),
            "rubric": json.loads(r[7] or "{}"),
            "hint_policy": r[8], "status": r[9], "created_at": r[10],
        }
    return None


def publish_case(case_id: int, professor_id: int) -> bool:
    blueprint = get_latest_blueprint(case_id)
    if not blueprint:
        raise ValueError("Cannot publish: generate a blueprint first.")

    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE cases SET status = 'published', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (case_id,)
    )
    conn.commit()
    conn.close()
    log_audit("publish_case", "cases", case_id, professor_id, {})
    return True


def assign_case_to_students(case_id: int, student_ids: List[int], professor_id: int):
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    for student_id in student_ids:
        try:
            cursor.execute(
                "INSERT INTO assignments (case_id, student_id) VALUES (?, ?)",
                (case_id, student_id)
            )
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    conn.close()
    log_audit("assign_case", "assignments", case_id, professor_id,
              {"num_students": len(student_ids)})


def get_student_assigned_cases(student_id: int) -> List[Dict]:
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.id, c.title, c.course, c.created_at
        FROM cases c JOIN assignments a ON c.id = a.case_id
        WHERE a.student_id = ? AND c.status = 'published'
        ORDER BY c.created_at DESC
    """, (student_id,))
    cases = [
        {"id": r[0], "title": r[1], "course": r[2], "created_at": r[3]}
        for r in cursor.fetchall()
    ]
    conn.close()
    return cases


def get_all_students() -> List[Dict]:
    """Get all users with Student role."""
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, username FROM users WHERE role = 'Student' ORDER BY username"
    )
    students = [{"id": r[0], "username": r[1]} for r in cursor.fetchall()]
    conn.close()
    return students


def get_case_student_results(case_id: int) -> List[Dict]:
    """Get all sessions and scores for a case (for professor reporting)."""
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.id, u.username, s.started_at, s.ended_at, s.state_json
        FROM sessions s
        JOIN users u ON s.student_id = u.id
        WHERE s.case_id = ? AND s.is_test = 0
        ORDER BY s.started_at DESC
    """, (case_id,))
    results = []
    for row in cursor.fetchall():
        state = json.loads(row[4] or "{}")
        results.append({
            "session_id": row[0],
            "username": row[1],
            "started_at": row[2],
            "ended_at": row[3],
            "is_complete": row[3] is not None,
            "scores": state.get("scores", {}),
            "completed_checkpoints": state.get("completed_checkpoints", []),
        })
    conn.close()
    return results


def log_audit(action: str, entity_type: str, entity_id: int,
              user_id: Optional[int] = None, payload: Optional[Dict] = None):
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO audit_logs (actor_user_id, action, entity_type, entity_id, payload_json)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, action, entity_type, entity_id, json.dumps(payload or {})))
    conn.commit()
    conn.close()
