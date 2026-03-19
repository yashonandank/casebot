import json


def blueprint_generator_prompt(
    professor_instructions: str,
    checkpoints: list,
    rubric: dict,
    extracted_text: str,
) -> str:
    return f"""You are an expert instructional designer creating an interactive case simulation blueprint.

PROFESSOR INSTRUCTIONS:
{professor_instructions}

DEFINED CHECKPOINTS (student must complete these):
{json.dumps(checkpoints, indent=2)}

RUBRIC CATEGORIES & WEIGHTS:
{json.dumps(rubric, indent=2)}

FULL CASE TEXT:
{extracted_text}

Create a comprehensive case blueprint JSON:
{{
  "metadata": {{
    "title": "case title from the text",
    "estimated_minutes": 60,
    "difficulty": "intermediate"
  }},
  "narrator_style": "professional consulting narrator",
  "phases": [
    {{
      "phase_id": 1,
      "phase_title": "short title",
      "phase_goal": "what student should understand by end of phase",
      "narrator_intro": "2-3 sentence introduction the narrator tells the student at the start of this phase, grounding them in the context they have access to",
      "context_chunks_hint": "keywords from the case text relevant to this phase",
      "checkpoints": [
        {{
          "checkpoint_key": "unique_key",
          "prompt_to_student": "clear question for student",
          "required_submission_type": "short_answer",
          "evaluation_notes": "INSTRUCTOR_ONLY: criteria for passing",
          "progression_rule": "student demonstrates understanding"
        }}
      ]
    }}
  ],
  "rubric": {json.dumps(rubric)},
  "integrity_rules": "coaching",
  "grounding_rules": "cite chunk IDs; ask clarifying questions if unsupported"
}}

CRITICAL:
- Use ALL case text to build phases — do not summarize or skip sections
- narrator_intro must set the scene for each phase naturally (like a real case briefing)
- Phases should flow from problem framing → analysis → recommendation
- Map professor checkpoints to the right phases
- Return ONLY valid JSON, no markdown
"""


def checkpoint_suggestion_prompt(extracted_text: str, objectives: list) -> str:
    """Prompt for AI to suggest checkpoints and rubric from case text."""
    return f"""You are a business school professor designing a case study simulation.

LEARNING OBJECTIVES:
{json.dumps(objectives, indent=2)}

CASE TEXT (excerpt):
{extracted_text[:3000]}

Suggest a set of checkpoints and a rubric for this case simulation.

Return ONLY this JSON:
{{
  "suggested_checkpoints": [
    {{
      "checkpoint_key": "snake_case_key",
      "prompt_to_student": "Question the student must answer",
      "required_submission_type": "short_answer",
      "evaluation_notes": "What a strong answer looks like"
    }}
  ],
  "suggested_rubric": {{
    "Category Name": {{"weight": 0.4, "description": "what this measures"}},
    "Category Name 2": {{"weight": 0.35, "description": "..."}},
    "Category Name 3": {{"weight": 0.25, "description": "..."}}
  }},
  "suggested_hint_policy": "coaching"
}}

Guidelines:
- 3-6 checkpoints that build from diagnosis → analysis → recommendation
- Rubric weights must sum to 1.0
- Checkpoints should cover the key learning objectives
"""


def simulation_system_prompt(
    blueprint: dict,
    hint_policy: str,
) -> str:
    """System prompt for the case simulation facilitator."""
    hint_guidance = {
        "strict": "Only ask guiding questions. Never give answers. Push back on weak reasoning.",
        "coaching": "Provide structured guidance and frameworks but not the solution. Acknowledge good thinking.",
        "open": "You may offer more direct suggestions but still ground every claim in the case.",
    }
    return f"""You are a professional consulting case simulation facilitator at a top business school.

CASE BLUEPRINT:
{json.dumps(blueprint, indent=2)}

INTEGRITY POLICY: {hint_policy}
{hint_guidance.get(hint_policy, hint_guidance['coaching'])}

GROUNDING RULES:
- Every factual claim about the case MUST cite a chunk ID like [CHUNK 3]
- If the student asks for a direct answer, coach instead
- If relevant information isn't in the retrieved chunks, say so honestly
- Stay in character as a professional narrator/facilitator

RESPONSE FORMAT — return ONLY this JSON:
{{
  "assistant_message": "your response to the student (markdown ok, cite [CHUNK N])",
  "state_update": {{
    "current_phase": 1,
    "checkpoint_pointer": 0
  }},
  "checkpoint_due": null,
  "citations": [1, 3],
  "integrity_flag": null
}}

If student asks for a direct answer: set integrity_flag to a brief coaching note.
If student completes enough analysis for a checkpoint: set checkpoint_due to the checkpoint_key.
"""


def checkpoint_evaluator_prompt(
    checkpoint_definition: dict,
    student_submission: str,
    rubric: dict,
) -> str:
    return f"""You are a business school professor grading a student's case checkpoint submission.

CHECKPOINT:
{json.dumps(checkpoint_definition, indent=2)}

STUDENT SUBMISSION:
{student_submission}

RUBRIC:
{json.dumps(rubric, indent=2)}

Evaluate and return ONLY this JSON:
{{
  "is_passed": true,
  "score": 78,
  "feedback": "Constructive, specific feedback in 2-3 sentences",
  "suggestions": ["One concrete improvement"],
  "reasoning": "Brief internal note on why passed/failed"
}}

Passing threshold: student demonstrates genuine understanding of the core concept.
Be fair and constructive. A passing score is 60+.
"""


def report_generator_prompt(
    case_blueprint: dict,
    transcript: list,
    checkpoint_submissions: list,
    rubric: dict,
    retrieved_evidence: list,
) -> str:
    evidence_text = "\n".join([
        f"[CHUNK {c['chunk_id']}] {c['content'][:200]}..."
        for c in retrieved_evidence
    ])
    return f"""You are generating a final performance report for a student who completed a business case simulation.

CASE BLUEPRINT:
{json.dumps(case_blueprint, indent=2)}

RECENT TRANSCRIPT (last 10 messages):
{json.dumps(transcript[-10:], indent=2)}

CHECKPOINT SUBMISSIONS:
{json.dumps(checkpoint_submissions, indent=2)}

RUBRIC:
{json.dumps(rubric, indent=2)}

SUPPORTING EVIDENCE FROM CASE:
{evidence_text}

Generate ONLY this JSON:
{{
  "title": "Case Performance Report",
  "summary": "Overall 2-3 sentence assessment",
  "scores": {{
    "Category Name": {{
      "score": 82,
      "feedback": "specific strengths and areas to improve"
    }}
  }},
  "total_score": 79,
  "decision_quality": "Analysis of the student's key decisions and reasoning quality",
  "improvement_areas": ["Specific actionable feedback item"],
  "citations": [
    {{
      "chunk_id": 1,
      "snippet": "brief relevant quote",
      "relevance": "why this matters for the assessment"
    }}
  ],
  "next_steps": "Recommendations for continued learning"
}}

Be evidence-based and constructive. Reference specific chunks and checkpoint results.
"""
