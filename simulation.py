import sqlite3
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import streamlit as st
from llm_client import get_llm_client
from prompts import (
    simulation_chat_prompt, checkpoint_evaluator_prompt
)
from retrieval import retrieve_chunks
from case_manager import get_case, get_latest_blueprint


def create_session(
    case_id: int,
    student_id: int,
    is_test: bool = False
) -> int:
    """Create a new case session. Returns session_id."""
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    initial_state = {
        "phase": 1,
        "checkpoint_pointer": 0,
        "completed_checkpoints": [],
        "scores": {}
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
    """Get session details."""
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, case_id, student_id, is_test, state_json, started_at, ended_at
        FROM sessions WHERE id = ?
    """, (session_id,))
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            "id": result[0],
            "case_id": result[1],
            "student_id": result[2],
            "is_test": bool(result[3]),
            "state": json.loads(result[4] or "{}"),
            "started_at": result[5],
            "ended_at": result[6]
        }
    return None


def save_session_state(session_id: int, state: Dict):
    """Update session state."""
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE sessions SET state_json = ? WHERE id = ?
    """, (json.dumps(state), session_id))
    
    conn.commit()
    conn.close()


def add_message(
    session_id: int,
    role: str,
    content: str,
    citations: Optional[List[int]] = None
) -> int:
    """Add message to session transcript. Returns message_id."""
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
    """Get conversation transcript."""
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT role, content, citations_json, created_at
        FROM session_messages
        WHERE session_id = ?
        ORDER BY created_at ASC
        LIMIT ?
    """, (session_id, limit))
    
    messages = []
    for role, content, citations_json, created_at in cursor.fetchall():
        messages.append({
            "role": role,
            "content": content,
            "citations": json.loads(citations_json or "[]"),
            "created_at": created_at
        })
    
    conn.close()
    return messages


def process_chat_turn(
    session_id: int,
    case_id: int,
    student_message: str,
    student_id: int,
    provider: str = "anthropic"
) -> Dict:
    """
    Process one chat turn: retrieve context, call LLM, update state.
    Returns result with assistant message, citations, state changes.
    """
    # Get session and case
    session = get_session(session_id)
    case = get_case(case_id)
    blueprint = get_latest_blueprint(case_id)
    
    if not session or not case or not blueprint:
        raise ValueError("Invalid session, case, or blueprint")
    
    # Retrieve relevant chunks
    retrieved = retrieve_chunks(case_id, student_message, top_k=5)
    chunk_summaries = [
        f"[CHUNK {c['chunk_id']}] {c['content'][:300]}"
        for c in retrieved
    ]
    
    # Prepare simulation prompt
    hint_policy = case.get("hint_policy", "coaching")
    prompt = simulation_chat_prompt(
        blueprint,
        session["state"],
        retrieved,
        student_message,
        hint_policy
    )
    
    # Call LLM
    llm = get_llm_client(provider)
    try:
        result = llm.generate_json(prompt)
    except Exception as e:
        # Fallback response if LLM fails
        result = {
            "assistant_message": f"I encountered an error processing your request: {str(e)}. Please try again.",
            "state_update": session["state"],
            "checkpoint_due": None,
            "citations": [],
            "integrity_flag": None,
            "grounding_issues": [str(e)]
        }
    
    # Validate response has citations if it makes claims
    if result.get("assistant_message") and not result.get("citations"):
        # Try to infer citations from content matching
        for chunk in retrieved:
            if any(phrase in result["assistant_message"] 
                   for phrase in chunk["content"].split()[:5]):
                result["citations"].append(chunk["chunk_id"])
    
    # Update session state if needed
    if result.get("state_update"):
        save_session_state(session_id, result["state_update"])
    
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
    provider: str = "anthropic"
) -> Dict:
    """
    Evaluate a checkpoint submission.
    Returns evaluation result with pass/fail and score.
    """
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
        raise ValueError(f"Checkpoint {checkpoint_key} not found")
    
    # Evaluate using LLM
    rubric = case.get("rubric", {})
    prompt = checkpoint_evaluator_prompt(checkpoint_def, submission_text, rubric)
    
    llm = get_llm_client(provider)
    try:
        evaluation = llm.generate_json(prompt)
    except Exception as e:
        evaluation = {
            "is_passed": False,
            "score": 0,
            "feedback": f"Evaluation error: {str(e)}",
            "reasoning": "System error",
            "suggestions": []
        }
    
    # Save submission
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO checkpoint_submissions
        (session_id, checkpoint_key, submission_text, is_passed, score)
        VALUES (?, ?, ?, ?, ?)
    """, (session_id, checkpoint_key, submission_text,
          int(evaluation.get("is_passed", False)),
          evaluation.get("score", 0)))
    
    conn.commit()
    conn.close()
    
    # Update session state
    session = get_session(session_id)
    state = session["state"]
    state["completed_checkpoints"].append(checkpoint_key)
    state["scores"][checkpoint_key] = evaluation.get("score", 0)
    save_session_state(session_id, state)
    
    return evaluation


def finalize_session(session_id: int) -> int:
    """Mark session as complete. Returns report_id."""
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE sessions SET ended_at = CURRENT_TIMESTAMP WHERE id = ?
    """, (session_id,))
    
    conn.commit()
    conn.close()
    
    return session_id


def get_student_sessions(student_id: int, case_id: Optional[int] = None) -> List[Dict]:
    """Get all sessions for a student."""
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    if case_id:
        cursor.execute("""
            SELECT id, case_id, started_at, ended_at, state_json
            FROM sessions
            WHERE student_id = ? AND case_id = ?
            ORDER BY started_at DESC
        """, (student_id, case_id))
    else:
        cursor.execute("""
            SELECT id, case_id, started_at, ended_at, state_json
            FROM sessions
            WHERE student_id = ?
            ORDER BY started_at DESC
        """, (student_id,))
    
    sessions = []
    for session_id, case_id, started_at, ended_at, state_json in cursor.fetchall():
        sessions.append({
            "id": session_id,
            "case_id": case_id,
            "started_at": started_at,
            "ended_at": ended_at,
            "state": json.loads(state_json or "{}"),
            "is_complete": ended_at is not None
        })
    
    conn.close()
    return sessions
