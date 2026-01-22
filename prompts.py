import json


def blueprint_generator_prompt(
    professor_instructions: str,
    checkpoints: list,
    rubric: dict,
    extracted_text: str
) -> str:
    """Generate prompt for creating case blueprint."""
    return f"""You are an expert instructional designer creating an interactive case simulation blueprint.

PROFESSOR INSTRUCTIONS:
{professor_instructions}

DEFINED CHECKPOINTS (that student must complete):
{json.dumps(checkpoints, indent=2)}

RUBRIC CATEGORIES & WEIGHTS:
{json.dumps(rubric, indent=2)}

EXTRACTED CASE TEXT (use ONLY this content):
{extracted_text}

Create a comprehensive case blueprint JSON with this structure:
{{
  "metadata": {{
    "title": "case title",
    "estimated_minutes": 60,
    "difficulty": "intermediate"
  }},
  "narrator_style": "consulting-like",
  "phases": [
    {{
      "phase_id": 1,
      "phase_goal": "understand the situation",
      "context_reveal_rules": "what info becomes available",
      "checkpoints": [
        {{
          "checkpoint_key": "id",
          "prompt_to_student": "what to do",
          "required_submission_type": "short_answer|choose_one|upload_text",
          "evaluation_notes": "INSTRUCTOR_ONLY: how to evaluate",
          "progression_rule": "when checkpoint passes"
        }}
      ],
      "decision_points": []
    }}
  ],
  "roles": ["narrator"],
  "rubric": {json.dumps(rubric)},
  "integrity_rules": "strict|coaching|open",
  "grounding_rules": "must cite chunks; ask clarifying questions if unsupported"
}}

CRITICAL:
- Do NOT invent information outside the case text
- Make checkpoints match the professor-defined ones (enhance wording if needed)
- Define phases that guide student from problem understanding to solution
- Mark all instructor-only content clearly
- Ensure checkpoint keys are unique
- Return ONLY valid JSON, no markdown or explanation
"""


def simulation_chat_prompt(
    blueprint: dict,
    session_state: dict,
    retrieved_chunks: list,
    student_message: str,
    hint_policy: str
) -> str:
    """Generate prompt for case simulation chat turn."""
    chunk_text = "\n---\n".join([f"[CHUNK {c['chunk_id']}] {c['content']}" for c in retrieved_chunks])
    
    hint_policy_guidance = {
        "strict": "Only ask guiding questions. Never provide answers. Explain tradeoffs.",
        "coaching": "Provide structured guidance and frameworks but not the solution.",
        "open": "Can offer more direct suggestions but still ground in case and cite sources."
    }
    
    return f"""You are a consulting case simulation facilitator. Your role is to guide the student through a realistic business case.

CASE BLUEPRINT:
{json.dumps(blueprint, indent=2)}

CURRENT SESSION STATE:
{json.dumps(session_state, indent=2)}

AVAILABLE CASE CONTENT (cite these chunks when making claims):
{chunk_text}

STUDENT MESSAGE:
{student_message}

INTEGRITY POLICY: {hint_policy}
{hint_policy_guidance.get(hint_policy, hint_policy_guidance['coaching'])}

GROUNDING RULES:
- Every factual claim MUST be supported by a chunk ID
- If student asks "what's the answer", respond by coaching instead
- If a chunk is missing, ask student to point you to relevant section
- Do NOT invent facts beyond the case

Respond with ONLY this JSON structure:
{{
  "assistant_message": "your response (must be grounded in chunks)",
  "state_update": {{
    "current_phase": 1,
    "checkpoint_pointer": 0
  }},
  "checkpoint_due": null,
  "citations": [1, 3, 5],
  "integrity_flag": null,
  "grounding_issues": []
}}

If student_message requests an answer directly, set integrity_flag with coaching strategy.
If response lacks citations, explain you need to find supporting evidence first.
"""


def checkpoint_evaluator_prompt(
    checkpoint_definition: dict,
    student_submission: str,
    rubric: dict
) -> str:
    """Generate prompt for evaluating checkpoint submission."""
    return f"""You are grading a student's checkpoint submission in a case simulation.

CHECKPOINT DEFINITION:
{json.dumps(checkpoint_definition, indent=2)}

STUDENT SUBMISSION:
{student_submission}

RUBRIC:
{json.dumps(rubric, indent=2)}

Evaluate and respond with ONLY this JSON:
{{
  "is_passed": true|false,
  "score": 0-100,
  "feedback": "specific guidance for next steps",
  "reasoning": "why passed/failed",
  "suggestions": ["actionable improvement"]
}}

Be fair and constructive. Checkpoint passes if student demonstrates understanding of core concept.
"""


def report_generator_prompt(
    case_blueprint: dict,
    transcript: list,
    checkpoint_submissions: list,
    rubric: dict,
    retrieved_evidence: list
) -> str:
    """Generate prompt for final report generation."""
    evidence_text = "\n".join([
        f"- [{c['chunk_id']}] {c['content'][:200]}..."
        for c in retrieved_evidence
    ])
    
    return f"""You are creating a final feedback report for a student who completed a case simulation.

CASE BLUEPRINT:
{json.dumps(case_blueprint, indent=2)}

STUDENT TRANSCRIPT (conversation history):
{json.dumps(transcript[-10:], indent=2)}  # Last 10 messages

CHECKPOINT SUBMISSIONS:
{json.dumps(checkpoint_submissions, indent=2)}

RUBRIC:
{json.dumps(rubric, indent=2)}

SUPPORTING EVIDENCE FROM CASE:
{evidence_text}

Generate ONLY this JSON structure:
{{
  "title": "Case Performance Report",
  "summary": "overall assessment (2-3 sentences)",
  "scores": {{
    "category_name": {{
      "score": 0-100,
      "feedback": "specific strengths and areas for improvement"
    }}
  }},
  "total_score": 0-100,
  "decision_quality": "analysis of student's key decisions",
  "improvement_areas": ["specific actionable feedback"],
  "citations": [
    {{
      "chunk_id": 1,
      "snippet": "relevant quote",
      "relevance": "why it matters"
    }}
  ],
  "next_steps": "recommendations for continued learning"
}}

Be constructive and evidence-based. Reference specific chunks for credibility.
"""
