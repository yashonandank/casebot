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
    hint_policy: str
) -> int:
    """Create a new case. Returns case_id."""
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO cases (
            professor_id, title, course, instructions_text,
            objectives_json, checkpoints_json, rubric_json, hint_policy, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft')
    """, (
        professor_id, title, course, instructions_text,
        json.dumps(objectives), json.dumps(checkpoints),
        json.dumps(rubric), hint_policy
    ))
    
    case_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    # Log
    log_audit("create case", "cases", case_id, professor_id, {"title": title})
    
    return case_id


def upload_case_file(case_id: int, uploaded_file) -> str:
    """Save uploaded file and extract content. Returns file path."""
    os.makedirs("data/uploads", exist_ok=True)
    
    # Save file
    file_ext = os.path.splitext(uploaded_file.name)[1]
    file_path = f"data/uploads/case_{case_id}_{datetime.now().timestamp()}{file_ext}"
    
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    # Update DB
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE cases SET upload_path = ? WHERE id = ?", (file_path, case_id))
    conn.commit()
    conn.close()
    
    return file_path


def generate_blueprint(
    case_id: int,
    professor_id: int,
    provider: str = "openai"
) -> Dict:
    """
    Generate initial blueprint using LLM.
    Extracts case text, retrieves chunks, and generates blueprint.
    """
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get case details
    cursor.execute("""
        SELECT upload_path, instructions_text, checkpoints_json, rubric_json
        FROM cases WHERE id = ?
    """, (case_id,))
    case_data = cursor.fetchone()
    
    if not case_data:
        raise ValueError(f"Case {case_id} not found")
    
    upload_path, instructions, checkpoints_json, rubric_json = case_data
    
    if not upload_path or not os.path.exists(upload_path):
        raise ValueError("Case file not found. Upload a file first.")
    
    # Extract and chunk
    num_chunks, chunks = ingest_case_file(case_id, upload_path)
    
    # Prepare extracted text sample (first 5 chunks)
    extracted_text = "\n---\n".join([c["content"][:500] for c in chunks[:5]])
    
    checkpoints = json.loads(checkpoints_json or "[]")
    rubric = json.loads(rubric_json or "{}")
    
    # Generate blueprint
    llm = get_llm_client(provider)
    prompt = blueprint_generator_prompt(instructions, checkpoints, rubric, extracted_text)
    
    try:
        blueprint = llm.generate_json(prompt)
    except Exception as e:
        raise ValueError(f"Blueprint generation failed: {str(e)}")
    
    # Save blueprint
    cursor.execute("""
        INSERT INTO case_blueprints (case_id, version, blueprint_json, created_by)
        VALUES (?, 1, ?, 'ai')
    """, (case_id, json.dumps(blueprint)))
    
    conn.commit()
    conn.close()
    
    log_audit("generate blueprint", "case_blueprints", case_id, professor_id, {})
    
    return blueprint


def get_latest_blueprint(case_id: int) -> Optional[Dict]:
    """Get latest blueprint for case."""
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT blueprint_json FROM case_blueprints
        WHERE case_id = ?
        ORDER BY version DESC
        LIMIT 1
    """, (case_id,))
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return json.loads(result[0])
    return None


def save_blueprint_version(
    case_id: int,
    blueprint: Dict,
    professor_id: int
) -> int:
    """Save edited blueprint as new version."""
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get current max version
    cursor.execute("""
        SELECT COALESCE(MAX(version), 0) FROM case_blueprints WHERE case_id = ?
    """, (case_id,))
    current_version = cursor.fetchone()[0]
    new_version = current_version + 1
    
    cursor.execute("""
        INSERT INTO case_blueprints (case_id, version, blueprint_json, created_by)
        VALUES (?, ?, ?, 'professor')
    """, (case_id, new_version, json.dumps(blueprint)))
    
    conn.commit()
    conn.close()
    
    log_audit("update blueprint", "case_blueprints", case_id, professor_id, {})
    
    return new_version


def get_professor_cases(professor_id: int) -> List[Dict]:
    """Get all cases created by professor."""
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, title, course, status, created_at, updated_at
        FROM cases
        WHERE professor_id = ?
        ORDER BY updated_at DESC
    """, (professor_id,))
    
    cases = []
    for case_id, title, course, status, created_at, updated_at in cursor.fetchall():
        cases.append({
            "id": case_id,
            "title": title,
            "course": course,
            "status": status,
            "created_at": created_at,
            "updated_at": updated_at
        })
    
    conn.close()
    return cases


def get_case(case_id: int) -> Optional[Dict]:
    """Get case details."""
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, professor_id, title, course, instructions_text,
               objectives_json, checkpoints_json, rubric_json, hint_policy, status, created_at
        FROM cases WHERE id = ?
    """, (case_id,))
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            "id": result[0],
            "professor_id": result[1],
            "title": result[2],
            "course": result[3],
            "instructions_text": result[4],
            "objectives": json.loads(result[5] or "[]"),
            "checkpoints": json.loads(result[6] or "[]"),
            "rubric": json.loads(result[7] or "{}"),
            "hint_policy": result[8],
            "status": result[9],
            "created_at": result[10]
        }
    return None


def publish_case(case_id: int, professor_id: int) -> bool:
    """Publish a case (make it available to students)."""
    # Validate blueprint exists
    blueprint = get_latest_blueprint(case_id)
    if not blueprint:
        raise ValueError("Cannot publish: no blueprint found. Generate one first.")
    
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE cases SET status = 'published', updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (case_id,))
    
    conn.commit()
    conn.close()
    
    log_audit("publish case", "cases", case_id, professor_id, {})
    return True


def assign_case_to_students(case_id: int, student_ids: List[int], professor_id: int):
    """Assign a published case to students."""
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    for student_id in student_ids:
        try:
            cursor.execute("""
                INSERT INTO assignments (case_id, student_id)
                VALUES (?, ?)
            """, (case_id, student_id))
        except sqlite3.IntegrityError:
            # Already assigned
            pass
    
    conn.commit()
    conn.close()
    
    log_audit("assign case", "assignments", case_id, professor_id, 
              {"num_students": len(student_ids)})


def get_student_assigned_cases(student_id: int) -> List[Dict]:
    """Get cases assigned to a student."""
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT c.id, c.title, c.course, c.created_at
        FROM cases c
        JOIN assignments a ON c.id = a.case_id
        WHERE a.student_id = ? AND c.status = 'published'
        ORDER BY c.created_at DESC
    """, (student_id,))
    
    cases = []
    for case_id, title, course, created_at in cursor.fetchall():
        cases.append({
            "id": case_id,
            "title": title,
            "course": course,
            "created_at": created_at
        })
    
    conn.close()
    return cases


def log_audit(action: str, entity_type: str, entity_id: int, 
              user_id: Optional[int] = None, payload: Optional[Dict] = None):
    """Log an audit event."""
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO audit_logs (actor_user_id, action, entity_type, entity_id, payload_json)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, action, entity_type, entity_id, json.dumps(payload or {})))
    
    conn.commit()
    conn.close()
