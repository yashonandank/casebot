import sqlite3
import json
from datetime import datetime
from typing import Dict, List, Optional
from llm_client import get_llm_client
from prompts import simulation_system_prompt, checkpoint_evaluator_prompt
from retrieval import retrieve_chunks
from case_manager import get_case, get_latest_blueprint


def create_session(case_id: int, student_id: int, is_test: bool = False) -> int:
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    initial_state = {
        "current_phase": 1,
        "checkpoint_pointer": 0,
        "completed_checkpoints": [],
        "scores": {},
        "phase_introduced": False,
    }
    cursor.execute("""
        INSERT INTO sessions (case_id, student_id, is_test, state_json)
        VALUES (?, ?, ?, ?)
    """, (case_id, student_id, int(is_test), json.dumps(initial_state)))
    session_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return session_id


def get_session(session_id: int) -> Optional[Dict]:
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, case_id, student_id, is_test, state_json, started_at, ended_at
        FROM sessions WHERE id = ?
    """, (session_id,))
    r = cursor.fetchone()
    conn.close()
    if r:
        return {
            "id": r[0], "case_id": r[1], "student_id": r[2],
            "is_test": bool(r[3]),
            "state": json.loads(r[4] or "{}"),
            "started_at": r[5], "ended_at": r[6],
        }
    return None


def save_session_state(session_id: int, state: Dict):
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE sessions SET state_json = ? WHERE id = ?",
        (json.dumps(state), session_id)
    )
    conn.commit()
    conn.close()


def add_message(
    session_id: int,
    role: str,
    content: str,
    citations: Optional[List[int]] = None,
) -> int:
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO session_messages (session_id, role, content, citations_json)
        VALUES (?, ?, ?, ?)
    """, (session_id, role, content, json.dumps(citations or [])))
    msg_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return msg_id


def get_session_transcript(session_id: int, limit: int = 50) -> List[Dict]:
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT role, content, citations_json, created_at
        FROM session_messages WHERE session_id = ?
        ORDER BY created_at ASC LIMIT ?
    """, (session_id, limit))
    messages = [
        {
            "role": r[0], "content": r[1],
            "citations": json.loads(r[2] or "[]"),
            "created_at": r[3],
        }
        for r in cursor.fetchall()
    ]
    conn.close()
    return messages


def get_phase_intro(blueprint: Dict, phase_num: int) -> Optional[str]:
    """Get the narrator intro for a given phase."""
    for phase in blueprint.get("phases", []):
        if phase.get("phase_id") == phase_num:
            return phase.get("narrator_intro")
    return None


def get_current_checkpoint(blueprint: Dict, state: Dict) -> Optional[Dict]:
    """Get the current checkpoint definition from state."""
    phase_num = state.get("current_phase", 1)
    cp_pointer = state.get("checkpoint_pointer", 0)

    completed = state.get("completed_checkpoints", [])

    for phase in blueprint.get("phases", []):
        if phase.get("phase_id") == phase_num:
            checkpoints = phase.get("checkpoints", [])
            for cp in checkpoints:
                if cp.get("checkpoint_key") not in completed:
                    return cp
    return None


def process_chat_turn(
    session_id: int,
    case_id: int,
    student_message: str,
    student_id: int,
) -> Dict:
    session = get_session(session_id)
    case = get_case(case_id)
    blueprint = get_latest_blueprint(case_id)

    if not session or not case or not blueprint:
        raise ValueError("Invalid session, case, or blueprint")

    state = session["state"]

    # Retrieve context
    retrieved = retrieve_chunks(case_id, student_message, top_k=6)
    chunk_context = "\n---\n".join([
        f"[CHUNK {c['chunk_id']}] ({c['location_hint']})\n{c['content'][:400]}"
        for c in retrieved
    ])

    # Build message history for the LLM (last 10 exchanges)
    transcript = get_session_transcript(session_id, limit=20)
    history = [
        {
            "role": "user" if m["role"] == "student" else "assistant",
            "content": m["content"],
        }
        for m in transcript
    ]

    # Add current context + message
    current_cp = get_current_checkpoint(blueprint, state)
    cp_context = f"\nCURRENT CHECKPOINT DUE: {json.dumps(current_cp)}" if current_cp else ""

    history.append({
        "role": "user",
        "content": (
            f"RETRIEVED CASE CONTENT:\n{chunk_context}\n\n"
            f"CURRENT SESSION STATE: {json.dumps(state)}{cp_context}\n\n"
            f"STUDENT MESSAGE: {student_message}"
        )
    })

    hint_policy = case.get("hint_policy", "coaching")
    system = simulation_system_prompt(blueprint, hint_policy)

    llm = get_llm_client()
    try:
        result = llm.chat_json(system, history)
    except Exception as e:
        result = {
            "assistant_message": f"I had trouble processing that. Please try again. (Error: {str(e)})",
            "state_update": state,
            "checkpoint_due": None,
            "citations": [],
            "integrity_flag": None,
        }

    # Update state
    if result.get("state_update"):
        new_state = result["state_update"]
        # Preserve fields not in LLM response
        new_state.setdefault("completed_checkpoints", state.get("completed_checkpoints", []))
        new_state.setdefault("scores", state.get("scores", {}))
        new_state.setdefault("phase_introduced", state.get("phase_introduced", False))
        save_session_state(session_id, new_state)

    # Save messages
    add_message(session_id, "student", student_message)
    add_message(session_id, "assistant", result["assistant_message"],
                result.get("citations", []))

    return result


def submit_checkpoint(
    session_id: int,
    case_id: int,
    checkpoint_key: str,
    submission_text: str,
    student_id: int,
) -> Dict:
    case = get_case(case_id)
    blueprint = get_latest_blueprint(case_id)

    if not case or not blueprint:
        raise ValueError("Invalid case or blueprint")

    # Find checkpoint definition
    checkpoint_def = None
    for phase in blueprint.get("phases", []):
        for cp in phase.get("checkpoints", []):
            if cp.get("checkpoint_key") == checkpoint_key:
                checkpoint_def = cp
                break

    if not checkpoint_def:
        raise ValueError(f"Checkpoint '{checkpoint_key}' not found in blueprint")

    rubric = case.get("rubric", {})
    from prompts import checkpoint_evaluator_prompt
    prompt = checkpoint_evaluator_prompt(checkpoint_def, submission_text, rubric)

    llm = get_llm_client()
    try:
        evaluation = llm.generate_json(prompt)
    except Exception as e:
        evaluation = {
            "is_passed": False,
            "score": 0,
            "feedback": f"Evaluation error: {str(e)}",
            "suggestions": [],
        }

    # Save submission with feedback
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO checkpoint_submissions
        (session_id, checkpoint_key, submission_text, is_passed, score, feedback)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        session_id, checkpoint_key, submission_text,
        int(evaluation.get("is_passed", False)),
        evaluation.get("score", 0),
        evaluation.get("feedback", ""),
    ))
    conn.commit()
    conn.close()

    # Update session state
    session = get_session(session_id)
    state = session["state"]
    if evaluation.get("is_passed"):
        state["completed_checkpoints"].append(checkpoint_key)
        state["scores"][checkpoint_key] = evaluation.get("score", 0)
        state["checkpoint_pointer"] = state.get("checkpoint_pointer", 0) + 1

        # Check if we should advance phase
        _maybe_advance_phase(state, blueprint)

    save_session_state(session_id, state)
    return evaluation


def _maybe_advance_phase(state: Dict, blueprint: Dict):
    """Advance to next phase if all checkpoints in current phase are done."""
    current_phase_num = state.get("current_phase", 1)
    completed = set(state.get("completed_checkpoints", []))

    for phase in blueprint.get("phases", []):
        if phase.get("phase_id") == current_phase_num:
            phase_cp_keys = {cp["checkpoint_key"] for cp in phase.get("checkpoints", [])}
            if phase_cp_keys.issubset(completed):
                # Advance
                state["current_phase"] = current_phase_num + 1
                state["phase_introduced"] = False
            break


def finalize_session(session_id: int):
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE sessions SET ended_at = CURRENT_TIMESTAMP WHERE id = ?",
        (session_id,)
    )
    conn.commit()
    conn.close()


def get_student_sessions(student_id: int, case_id: Optional[int] = None) -> List[Dict]:
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    if case_id:
        cursor.execute("""
            SELECT id, case_id, started_at, ended_at, state_json, is_test
            FROM sessions WHERE student_id = ? AND case_id = ?
            ORDER BY started_at DESC
        """, (student_id, case_id))
    else:
        cursor.execute("""
            SELECT id, case_id, started_at, ended_at, state_json, is_test
            FROM sessions WHERE student_id = ?
            ORDER BY started_at DESC
        """, (student_id,))
    sessions = [
        {
            "id": r[0], "case_id": r[1], "started_at": r[2], "ended_at": r[3],
            "state": json.loads(r[4] or "{}"),
            "is_complete": r[3] is not None,
            "is_test": bool(r[5]),
        }
        for r in cursor.fetchall()
    ]
    conn.close()
    return sessions


def get_resumable_session(student_id: int, case_id: int) -> Optional[int]:
    """Return session_id of an incomplete session for this student+case, if any."""
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM sessions
        WHERE student_id = ? AND case_id = ? AND ended_at IS NULL AND is_test = 0
        ORDER BY started_at DESC LIMIT 1
    """, (student_id, case_id))
    r = cursor.fetchone()
    conn.close()
    return r[0] if r else None
