import streamlit as st
import json
import os
from auth_casesim import require_login
from case_manager import (
    create_case, upload_case_file, generate_blueprint, get_latest_blueprint,
    save_blueprint_version, get_professor_cases, get_case, publish_case,
    get_student_assigned_cases, assign_case_to_students, get_all_students,
    get_case_student_results, log_audit,
)
from simulation import (
    create_session, get_session, process_chat_turn, submit_checkpoint,
    finalize_session, get_student_sessions, get_session_transcript,
    get_phase_intro, get_current_checkpoint, get_resumable_session,
    save_session_state,
)
from reporting import generate_report, get_report, render_report_html, export_report_html
from ingest import get_case_chunks
from prompts import checkpoint_suggestion_prompt

st.set_page_config(
    page_title="CaseSim",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Design System ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=DM+Sans:wght@400;500;600&display=swap');

*{font-family:'DM Sans',-apple-system,sans-serif;}

[data-testid="stAppViewContainer"],.main{background-color:#fdfcf7;}
[data-testid="stSidebar"]{background-color:#f5f0e8;border-right:1px solid #e0d7ca;}
[data-testid="stSidebar"]>div:first-child{padding-top:2rem;}

.sidebar-brand{font-family:'Playfair Display',serif;font-size:1.4rem;font-weight:700;
  color:#2c2c2c;letter-spacing:-.5px;padding:0 1rem 1.5rem 1rem;
  border-bottom:1px solid #e0d7ca;margin-bottom:1.5rem;}
.sidebar-brand span{display:block;font-family:'DM Sans',sans-serif;font-size:.75rem;
  font-weight:500;color:#8b8680;text-transform:uppercase;letter-spacing:1px;margin-bottom:.3rem;}

h1{font-family:'Playfair Display',serif;font-size:2.2rem;font-weight:700;
  color:#2c2c2c;letter-spacing:-.8px;line-height:1.2;margin-bottom:.5rem;}
h2{font-family:'Playfair Display',serif;font-size:1.5rem;font-weight:700;
  color:#2c2c2c;letter-spacing:-.4px;margin-top:2rem;margin-bottom:1rem;}
h3{font-size:.78rem;font-weight:600;color:#8b8680;text-transform:uppercase;
  letter-spacing:1px;margin-bottom:.6rem;margin-top:1.2rem;}
p{color:#5a5a5a;line-height:1.8;}
.subtitle{font-size:1rem;color:#6a6460;line-height:1.7;margin-bottom:2rem;}

.card{background:#fef9f3;border:1px solid #e8e0d5;border-radius:2px;padding:1.5rem;margin-bottom:1rem;}
.card-sm{background:#fef9f3;border:1px solid #e8e0d5;border-radius:2px;padding:1.2rem;text-align:center;}
.card-sm .card-label{font-size:.72rem;color:#8b8680;text-transform:uppercase;
  letter-spacing:.8px;font-weight:600;margin-bottom:.5rem;}
.card-sm .card-value{font-size:1.5rem;font-weight:600;color:#2c2c2c;}

.info-strip{background:#f9f4ed;border-left:2px solid #8b8680;padding:1rem 1.2rem;
  color:#4a4a4a;font-size:.92rem;line-height:1.7;margin:1rem 0;border-radius:0 2px 2px 0;}
.success-strip{background:#f0f7f0;border-left:2px solid #6a9a6a;padding:1rem 1.2rem;
  color:#3a5a3a;font-size:.92rem;line-height:1.7;margin:1rem 0;border-radius:0 2px 2px 0;}
.error-strip{background:#fdf0f0;border-left:2px solid #c0706a;padding:1rem 1.2rem;
  color:#6a3a3a;font-size:.92rem;line-height:1.7;margin:1rem 0;border-radius:0 2px 2px 0;}
.warn-strip{background:#fdf6ed;border-left:2px solid #d4a060;padding:1rem 1.2rem;
  color:#7a4a10;font-size:.92rem;line-height:1.7;margin:1rem 0;border-radius:0 2px 2px 0;}

.stTextInput input,.stTextArea textarea,.stSelectbox>div>div,.stNumberInput input{
  border:1px solid #d4cfc0!important;border-radius:2px!important;
  background-color:#fef9f3!important;color:#3a3a3a!important;font-size:.94rem!important;}
.stTextInput input:focus,.stTextArea textarea:focus{border-color:#8b8680!important;}
.stTextInput label,.stTextArea label,.stSelectbox label,.stNumberInput label{
  font-size:.78rem!important;font-weight:600!important;color:#6a6460!important;
  text-transform:uppercase!important;letter-spacing:.8px!important;}

.stButton>button{background-color:#f5f0e8;color:#2c2c2c;border:1.5px solid #d4cfc0;
  border-radius:2px;font-weight:600;font-size:.9rem;padding:.6rem 1.5rem;transition:all .2s ease;}
.stButton>button:hover{background-color:#ebe5db;border-color:#8b8680;}
.stButton>button[kind="primary"]{background-color:#2c2c2c;color:#fdfcf7;border-color:#2c2c2c;}
.stDownloadButton>button{background-color:#f5f0e8;color:#2c2c2c;border:1.5px solid #d4cfc0;
  border-radius:2px;font-weight:500;font-size:.88rem;transition:all .2s ease;}
.stDownloadButton>button:hover{background-color:#ebe5db;border-color:#8b8680;}

.stTabs [data-baseweb="tab-list"]{gap:2rem;border-bottom:1px solid #e0d7ca;}
.stTabs [data-baseweb="tab"]{padding:0 0 .6rem 0;color:#9a9490;font-weight:500;
  font-size:.88rem;border-bottom:2px solid transparent;}
.stTabs [aria-selected="true"]{color:#2c2c2c;border-bottom-color:#2c2c2c;}

hr{border:none;border-top:1px solid #e0d7ca;margin:2rem 0;}

.badge{display:inline-block;padding:.2rem .6rem;background:#f5f0e8;border:1px solid #d4cfc0;
  border-radius:20px;font-size:.75rem;font-weight:600;color:#5a5a5a;text-transform:uppercase;letter-spacing:.5px;}
.badge-green{background:#f0f7f0;border-color:#9aba9a;color:#3a5a3a;}
.badge-amber{background:#fdf6ed;border-color:#d4a060;color:#7a4a10;}
.badge-blue{background:#f0f4fd;border-color:#8aacda;color:#1a3a6a;}

.phase-header{background:#f5f0e8;border:1px solid #e0d7ca;border-radius:2px;
  padding:1.2rem 1.5rem;margin:1rem 0;}
.phase-header .phase-num{font-size:.72rem;font-weight:600;color:#8b8680;
  text-transform:uppercase;letter-spacing:1px;}
.phase-header .phase-title{font-family:'Playfair Display',serif;font-size:1.3rem;
  color:#2c2c2c;margin:.3rem 0;}

.checkpoint-box{background:#fef9f3;border:1.5px solid #d4cfc0;border-radius:2px;
  padding:1.5rem;margin:1rem 0;}
.checkpoint-box.passed{border-color:#9aba9a;background:#f5fbf5;}
.checkpoint-box .cp-label{font-size:.72rem;font-weight:600;color:#8b8680;
  text-transform:uppercase;letter-spacing:1px;margin-bottom:.5rem;}

.progress-bar-wrap{background:#e8e0d5;border-radius:20px;height:6px;margin:.8rem 0;}
.progress-bar-fill{background:#2c2c2c;border-radius:20px;height:6px;transition:width .4s ease;}

.score-ring{display:flex;flex-direction:column;align-items:center;justify-content:center;
  width:100px;height:100px;border-radius:50%;border:3px solid #2c2c2c;margin:0 auto 1rem;}
.score-ring .score-num{font-family:'Playfair Display',serif;font-size:1.8rem;font-weight:700;
  color:#2c2c2c;line-height:1;}
.score-ring .score-pct{font-size:.7rem;color:#8b8680;text-transform:uppercase;}

.stAlert{border-radius:2px;border-left-width:2px;}
#MainMenu,footer{visibility:hidden;}
[data-testid="stDecoration"]{display:none;}

.stRadio>div{gap:.3rem;}
.stRadio label{display:flex!important;align-items:center;padding:.7rem 1rem!important;
  border-radius:2px!important;cursor:pointer;font-size:.9rem!important;font-weight:500!important;
  color:#4a4a4a!important;transition:all .15s ease;border:1px solid transparent!important;
  background:transparent!important;margin:0!important;}
.stRadio label:hover{background-color:#ede8df!important;}
</style>
""", unsafe_allow_html=True)

# ── Auth ───────────────────────────────────────────────────────────────────────
os.environ["OPENAI_API_KEY"] = st.secrets.get("OPENAI_API_KEY", "")

authenticated, role, user_id, username = require_login()
if not authenticated:
    st.stop()

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div class='sidebar-brand'>
        <span>Goizueta Business School</span>
        CaseSim
    </div>
    """, unsafe_allow_html=True)

    if role == "Professor":
        nav_options = ["🏠  Dashboard", "✏️  Create Case", "📂  My Cases", "🧪  Test Sim", "📊  Reports"]
    elif role == "Student":
        nav_options = ["🏠  Dashboard", "📋  My Cases", "📄  My Reports"]
    else:
        nav_options = ["🏠  Dashboard", "⚙️  Admin"]

    page = st.radio("nav", nav_options, label_visibility="collapsed")

    st.markdown("<hr style='margin:1.5rem 0;'>", unsafe_allow_html=True)
    role_badge = "badge-blue" if role == "Professor" else "badge-green" if role == "Student" else ""
    st.markdown(f"""
    <div style='padding:0 .5rem;'>
        <div style='font-size:.72rem;color:#8b8680;text-transform:uppercase;
                    letter-spacing:.8px;font-weight:600;margin-bottom:.3rem;'>Signed in as</div>
        <div style='font-size:.9rem;color:#3a3a3a;font-weight:500;'>{username}</div>
        <div style='margin-top:.4rem;'>
            <span class='badge {role_badge}'>{role}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Sign Out", use_container_width=True):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# PROFESSOR INTERFACE
# ══════════════════════════════════════════════════════════════════════════════
if role == "Professor":

    # ── Dashboard ─────────────────────────────────────────────────────────────
    if "🏠" in page:
        st.markdown("<h1>Welcome back.</h1>", unsafe_allow_html=True)
        st.markdown(f"<p class='subtitle'>Here's what's happening with your cases.</p>",
                    unsafe_allow_html=True)

        cases = get_professor_cases(user_id)
        published = [c for c in cases if c["status"] == "published"]
        drafts = [c for c in cases if c["status"] == "draft"]

        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""<div class='card-sm'>
                <div class='card-label'>Total Cases</div>
                <div class='card-value'>{len(cases)}</div></div>""", unsafe_allow_html=True)
        with col2:
            st.markdown(f"""<div class='card-sm'>
                <div class='card-label'>Published</div>
                <div class='card-value'>{len(published)}</div></div>""", unsafe_allow_html=True)
        with col3:
            st.markdown(f"""<div class='card-sm'>
                <div class='card-label'>Drafts</div>
                <div class='card-value'>{len(drafts)}</div></div>""", unsafe_allow_html=True)

        if cases:
            st.markdown("<h2>Recent Cases</h2>", unsafe_allow_html=True)
            for case in cases[:5]:
                badge = {"draft": "badge-amber", "published": "badge-green",
                         "archived": ""}.get(case["status"], "")
                st.markdown(f"""
                <div class='card' style='margin-bottom:.75rem;'>
                    <div style='display:flex;justify-content:space-between;align-items:flex-start;'>
                        <div>
                            <div style='font-size:1rem;font-weight:600;color:#2c2c2c;'>
                                {case['title']}</div>
                            <div style='font-size:.85rem;color:#8b8680;margin-top:.25rem;'>
                                {case['course']} · {case['created_at'][:10]}</div>
                        </div>
                        <span class='badge {badge}'>{case['status']}</span>
                    </div>
                </div>""", unsafe_allow_html=True)

    # ── Create Case Wizard ─────────────────────────────────────────────────────
    elif "✏️" in page:
        st.markdown("<h1>Create a Case</h1>", unsafe_allow_html=True)
        st.markdown("<p class='subtitle'>Upload your case document — AI will suggest checkpoints and a rubric for you to review.</p>",
                    unsafe_allow_html=True)

        # Step tracker
        step = st.session_state.get("wizard_step", 1)
        steps = ["Upload & Basics", "Checkpoints & Rubric", "Review & Generate"]
        cols = st.columns(len(steps))
        for i, (col, label) in enumerate(zip(cols, steps), 1):
            with col:
                active = "font-weight:600;color:#2c2c2c;" if i == step else "color:#8b8680;"
                dot = "background:#2c2c2c;" if i == step else ("background:#9aba9a;" if i < step else "background:#d4cfc0;")
                st.markdown(f"""
                <div style='text-align:center;'>
                    <div style='width:28px;height:28px;border-radius:50%;{dot}
                        color:#fff;font-size:.8rem;font-weight:600;display:flex;
                        align-items:center;justify-content:center;margin:0 auto .4rem;'>
                        {"✓" if i < step else i}</div>
                    <div style='font-size:.8rem;{active}'>{label}</div>
                </div>""", unsafe_allow_html=True)

        st.markdown("<hr>", unsafe_allow_html=True)

        # ── Step 1: Upload & Basics ────────────────────────────────────────────
        if step == 1:
            col1, col2 = st.columns([3, 2])
            with col1:
                case_title = st.text_input("Case Title", value=st.session_state.get("w_title", ""),
                                           placeholder="e.g., Maersk Supply Chain Crisis")
                course = st.text_input("Course", value=st.session_state.get("w_course", ""),
                                       placeholder="e.g., MGT 501")
            with col2:
                hint_policy = st.selectbox(
                    "Coaching Style",
                    ["coaching", "strict", "open"],
                    index=["coaching","strict","open"].index(
                        st.session_state.get("w_hint","coaching")),
                    help="Strict = only guiding questions. Coaching = frameworks without answers. Open = more direct."
                )

            objectives_text = st.text_area(
                "Learning Objectives (one per line)",
                value=st.session_state.get("w_objectives", ""),
                placeholder="Analyze supply chain vulnerabilities\nDevelop contingency frameworks\nPresent a recommendation",
                height=100,
            )

            uploaded_file = st.file_uploader("Case Document (PDF or DOCX)", type=["pdf", "docx"])

            if st.button("Next →", type="primary"):
                if not case_title or not uploaded_file:
                    st.markdown("<div class='error-strip'>Case title and document are required.</div>",
                                unsafe_allow_html=True)
                else:
                    st.session_state.w_title = case_title
                    st.session_state.w_course = course
                    st.session_state.w_hint = hint_policy
                    st.session_state.w_objectives = objectives_text
                    st.session_state.w_uploaded_file = uploaded_file
                    st.session_state.wizard_step = 2
                    st.session_state.ai_suggestions = None
                    st.rerun()

        # ── Step 2: Checkpoints & Rubric ──────────────────────────────────────
        elif step == 2:
            objectives = [o.strip() for o in
                          st.session_state.get("w_objectives","").split("\n") if o.strip()]

            # AI suggestion
            if st.session_state.get("ai_suggestions") is None:
                with st.spinner("Scanning your case document and generating suggestions..."):
                    try:
                        uploaded_file = st.session_state.w_uploaded_file
                        import tempfile, os as _os
                        suffix = _os.path.splitext(uploaded_file.name)[1]
                        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                            tmp.write(uploaded_file.getbuffer())
                            tmp_path = tmp.name

                        from ingest import extract_text_from_file
                        text = extract_text_from_file(tmp_path)
                        _os.unlink(tmp_path)

                        from llm_client import get_llm_client
                        llm = get_llm_client()
                        prompt = checkpoint_suggestion_prompt(text, objectives)
                        suggestions = llm.generate_json(prompt)
                        st.session_state.ai_suggestions = suggestions
                        st.session_state.w_full_text = text
                    except Exception as e:
                        st.markdown(f"<div class='warn-strip'>AI suggestion failed: {e}. Define manually below.</div>",
                                    unsafe_allow_html=True)
                        st.session_state.ai_suggestions = {}

            suggestions = st.session_state.get("ai_suggestions", {})

            st.markdown("<div class='info-strip'>AI has suggested checkpoints and a rubric based on your case document. Edit freely before continuing.</div>",
                        unsafe_allow_html=True)

            # Checkpoints
            st.markdown("<h2>Checkpoints</h2>", unsafe_allow_html=True)
            suggested_cps = suggestions.get("suggested_checkpoints", [])

            # Allow editing suggested checkpoints
            if "w_checkpoints" not in st.session_state:
                st.session_state.w_checkpoints = suggested_cps or []
            if "w_num_cps" not in st.session_state:
                st.session_state.w_num_cps = max(len(suggested_cps), 2)

            num_cps = st.number_input("Number of checkpoints", 1, 10,
                                      value=st.session_state.w_num_cps, key="ncp_input")
            st.session_state.w_num_cps = num_cps

            checkpoints = []
            for i in range(num_cps):
                default = suggested_cps[i] if i < len(suggested_cps) else {}
                with st.expander(f"Checkpoint {i+1}" + (f" — {default.get('checkpoint_key','')}" if default.get('checkpoint_key') else ""),
                                 expanded=(i == 0)):
                    c1, c2 = st.columns([1, 2])
                    with c1:
                        cp_key = st.text_input("Key (snake_case)", value=default.get("checkpoint_key",""),
                                               key=f"cpk_{i}")
                        cp_type = st.selectbox("Response type",
                            ["short_answer","choose_one","upload_text"],
                            key=f"cpt_{i}")
                    with c2:
                        cp_prompt = st.text_area("Question for student",
                            value=default.get("prompt_to_student",""), height=80, key=f"cpp_{i}")
                        cp_eval = st.text_area("Evaluation notes (instructor only)",
                            value=default.get("evaluation_notes",""), height=60, key=f"cpe_{i}")

                    if cp_key and cp_prompt:
                        checkpoints.append({
                            "checkpoint_key": cp_key,
                            "prompt_to_student": cp_prompt,
                            "required_submission_type": cp_type,
                            "evaluation_notes": cp_eval,
                            "progression_rule": "student demonstrates understanding",
                        })

            # Rubric
            st.markdown("<h2>Rubric</h2>", unsafe_allow_html=True)
            suggested_rubric = suggestions.get("suggested_rubric", {})

            if "w_rubric_text" not in st.session_state:
                rubric_lines = []
                total = sum(v.get("weight", 0) if isinstance(v, dict) else v
                            for v in suggested_rubric.values())
                for cat, details in suggested_rubric.items():
                    w = details.get("weight", 0) if isinstance(details, dict) else details
                    pct = round((w / total) * 100) if total > 0 else 0
                    rubric_lines.append(f"{cat} | {pct}")
                st.session_state.w_rubric_text = "\n".join(rubric_lines) if rubric_lines else \
                    "Decision Quality | 40\nAnalysis | 35\nCommunication | 25"

            rubric_text = st.text_area(
                "Criteria — one per line: 'Name | Weight %'",
                value=st.session_state.w_rubric_text,
                height=120,
            )
            st.session_state.w_rubric_text = rubric_text

            professor_instructions = st.text_area(
                "Additional Instructions for AI Blueprint Generator",
                value=st.session_state.get("w_instructions", ""),
                placeholder="Any extra context about learning goals, key decision points, or how to guide students...",
                height=80,
            )
            st.session_state.w_instructions = professor_instructions

            col_back, col_next = st.columns([1, 3])
            with col_back:
                if st.button("← Back"):
                    st.session_state.wizard_step = 1
                    st.rerun()
            with col_next:
                if st.button("Next →", type="primary"):
                    st.session_state.w_checkpoints_final = checkpoints
                    st.session_state.w_rubric_final = rubric_text
                    st.session_state.wizard_step = 3
                    st.rerun()

        # ── Step 3: Review & Generate ──────────────────────────────────────────
        elif step == 3:
            st.markdown("<h2>Review & Generate Blueprint</h2>", unsafe_allow_html=True)

            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"""<div class='card'>
                    <div style='font-size:.75rem;color:#8b8680;text-transform:uppercase;
                        letter-spacing:.8px;margin-bottom:.5rem;'>Case</div>
                    <div style='font-size:1.1rem;font-weight:600;color:#2c2c2c;'>
                        {st.session_state.get('w_title','')}</div>
                    <div style='font-size:.9rem;color:#6a6460;margin-top:.3rem;'>
                        {st.session_state.get('w_course','')} · {st.session_state.get('w_hint','')}</div>
                </div>""", unsafe_allow_html=True)

            cps = st.session_state.get("w_checkpoints_final", [])
            with col2:
                st.markdown(f"""<div class='card'>
                    <div style='font-size:.75rem;color:#8b8680;text-transform:uppercase;
                        letter-spacing:.8px;margin-bottom:.5rem;'>Checkpoints</div>
                    <div style='font-size:1.5rem;font-weight:600;color:#2c2c2c;'>{len(cps)}</div>
                    <div style='font-size:.85rem;color:#6a6460;'>
                        {", ".join(c.get("checkpoint_key","") for c in cps[:3])}</div>
                </div>""", unsafe_allow_html=True)

            # Parse rubric
            rubric = {}
            rubric_text = st.session_state.get("w_rubric_final", "")
            for line in rubric_text.split("\n"):
                line = line.strip()
                if "|" in line:
                    parts = line.split("|")
                    if len(parts) == 2:
                        try:
                            rubric[parts[0].strip()] = {
                                "weight": float(parts[1].strip()) / 100
                            }
                        except ValueError:
                            pass
            # Normalize
            total_w = sum(v["weight"] for v in rubric.values())
            if total_w > 0:
                for k in rubric:
                    rubric[k]["weight"] = rubric[k]["weight"] / total_w

            objectives = [o.strip() for o in
                          st.session_state.get("w_objectives","").split("\n") if o.strip()]

            col_back, col_gen = st.columns([1, 3])
            with col_back:
                if st.button("← Back"):
                    st.session_state.wizard_step = 2
                    st.rerun()
            with col_gen:
                if st.button("🤖 Create Case & Generate Blueprint", type="primary", use_container_width=True):
                    if not cps:
                        st.markdown("<div class='error-strip'>Add at least one checkpoint before generating.</div>",
                                    unsafe_allow_html=True)
                    else:
                        with st.spinner("Creating case and generating AI blueprint from full document..."):
                            try:
                                instructions = st.session_state.get("w_instructions","")
                                case_id = create_case(
                                    user_id,
                                    st.session_state.w_title,
                                    st.session_state.get("w_course",""),
                                    instructions,
                                    objectives,
                                    cps,
                                    rubric,
                                    st.session_state.get("w_hint","coaching"),
                                )
                                file_path = upload_case_file(
                                    case_id, st.session_state.w_uploaded_file)
                                blueprint = generate_blueprint(case_id, user_id)

                                st.session_state.wizard_step = 1
                                for k in list(st.session_state.keys()):
                                    if k.startswith("w_") or k == "ai_suggestions":
                                        del st.session_state[k]

                                st.markdown(f"""
                                <div class='success-strip'>
                                    Case created successfully (ID {case_id}).
                                    Blueprint generated with {len(blueprint.get('phases',[]))} phases.
                                    Head to <strong>My Cases</strong> to publish and assign students.
                                </div>""", unsafe_allow_html=True)
                            except Exception as e:
                                st.markdown(f"<div class='error-strip'>Error: {str(e)}</div>",
                                            unsafe_allow_html=True)

    # ── My Cases ───────────────────────────────────────────────────────────────
    elif "📂" in page:
        st.markdown("<h1>My Cases</h1>", unsafe_allow_html=True)

        cases = get_professor_cases(user_id)
        if not cases:
            st.markdown("<div class='info-strip'>No cases yet. Head to <strong>Create Case</strong> to get started.</div>",
                        unsafe_allow_html=True)
        else:
            for case in cases:
                badge = {"draft": "badge-amber", "published": "badge-green",
                         "archived": ""}.get(case["status"], "")
                with st.expander(f"{case['title']} — {case['course']}", expanded=False):
                    col1, col2, col3 = st.columns([2, 1, 1])
                    with col1:
                        st.markdown(f"""
                        <span class='badge {badge}'>{case['status']}</span>
                        <span style='font-size:.85rem;color:#8b8680;margin-left:.5rem;'>
                            Created {case['created_at'][:10]}</span>
                        """, unsafe_allow_html=True)
                    with col2:
                        if case["status"] == "draft":
                            if st.button("🚀 Publish", key=f"pub_{case['id']}"):
                                try:
                                    publish_case(case["id"], user_id)
                                    st.markdown("<div class='success-strip'>Case published!</div>",
                                                unsafe_allow_html=True)
                                    st.rerun()
                                except Exception as e:
                                    st.markdown(f"<div class='error-strip'>{e}</div>",
                                                unsafe_allow_html=True)
                    with col3:
                        if case["status"] == "published":
                            if st.button("📋 Assign Students", key=f"assign_{case['id']}"):
                                st.session_state.assign_case_id = case["id"]

                    # Blueprint status
                    blueprint = get_latest_blueprint(case["id"])
                    if blueprint:
                        phases = blueprint.get("phases", [])
                        st.markdown(f"""
                        <div style='margin-top:.75rem;'>
                            <span class='badge badge-green'>Blueprint ready</span>
                            <span style='font-size:.85rem;color:#8b8680;margin-left:.5rem;'>
                                {len(phases)} phases · {sum(len(p.get('checkpoints',[])) for p in phases)} checkpoints</span>
                        </div>""", unsafe_allow_html=True)
                    else:
                        st.markdown("<div class='warn-strip'>No blueprint yet — regenerate from Test Sim tab.</div>",
                                    unsafe_allow_html=True)

                    # Assign students panel
                    if st.session_state.get("assign_case_id") == case["id"]:
                        st.markdown("<hr>", unsafe_allow_html=True)
                        st.markdown("<h3>Assign Students</h3>", unsafe_allow_html=True)
                        all_students = get_all_students()
                        if all_students:
                            student_options = {s["username"]: s["id"] for s in all_students}
                            selected = st.multiselect(
                                "Select students",
                                options=list(student_options.keys()),
                                key=f"sel_students_{case['id']}",
                            )
                            if st.button("Assign", key=f"do_assign_{case['id']}", type="primary"):
                                ids = [student_options[s] for s in selected]
                                assign_case_to_students(case["id"], ids, user_id)
                                st.markdown(f"<div class='success-strip'>Assigned {len(ids)} student(s).</div>",
                                            unsafe_allow_html=True)
                                st.session_state.assign_case_id = None
                                st.rerun()
                        else:
                            st.markdown("<div class='info-strip'>No student accounts found.</div>",
                                        unsafe_allow_html=True)

    # ── Test Sim ───────────────────────────────────────────────────────────────
    elif "🧪" in page:
        st.markdown("<h1>Test Simulation</h1>", unsafe_allow_html=True)
        st.markdown("<p class='subtitle'>Run a case as a student would experience it.</p>",
                    unsafe_allow_html=True)

        cases = get_professor_cases(user_id)
        if not cases:
            st.markdown("<div class='info-strip'>Create a case first.</div>", unsafe_allow_html=True)
        else:
            case_options = {c["title"]: c["id"] for c in cases}
            selected_title = st.selectbox("Select case", list(case_options.keys()))
            test_case_id = case_options[selected_title]

            blueprint = get_latest_blueprint(test_case_id)
            if not blueprint:
                st.markdown("<div class='warn-strip'>No blueprint for this case. Generate one first.</div>",
                            unsafe_allow_html=True)
                if st.button("Generate Blueprint Now", type="primary"):
                    with st.spinner("Generating..."):
                        try:
                            generate_blueprint(test_case_id, user_id)
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
            else:
                if st.button("▶ Start New Test Session", type="primary"):
                    session_id = create_session(test_case_id, user_id, is_test=True)
                    st.session_state.test_session_id = session_id
                    st.session_state.test_case_id = test_case_id
                    st.rerun()

                if "test_session_id" in st.session_state:
                    _render_case_chat(
                        st.session_state.test_session_id,
                        st.session_state.get("test_case_id", test_case_id),
                        user_id,
                        is_test=True,
                    )

    # ── Reports ────────────────────────────────────────────────────────────────
    elif "📊" in page:
        st.markdown("<h1>Student Reports</h1>", unsafe_allow_html=True)

        cases = get_professor_cases(user_id)
        published = [c for c in cases if c["status"] == "published"]

        if not published:
            st.markdown("<div class='info-strip'>No published cases yet.</div>",
                        unsafe_allow_html=True)
        else:
            selected_title = st.selectbox("Select case", [c["title"] for c in published])
            selected_case = next(c for c in published if c["title"] == selected_title)
            results = get_case_student_results(selected_case["id"])

            if not results:
                st.markdown("<div class='info-strip'>No student sessions for this case yet.</div>",
                            unsafe_allow_html=True)
            else:
                # Summary metrics
                completed = [r for r in results if r["is_complete"]]
                all_scores = []
                for r in completed:
                    if r["scores"]:
                        avg = sum(r["scores"].values()) / len(r["scores"])
                        all_scores.append(avg)

                c1, c2, c3 = st.columns(3)
                with c1:
                    st.markdown(f"""<div class='card-sm'>
                        <div class='card-label'>Students</div>
                        <div class='card-value'>{len(results)}</div></div>""",
                        unsafe_allow_html=True)
                with c2:
                    st.markdown(f"""<div class='card-sm'>
                        <div class='card-label'>Completed</div>
                        <div class='card-value'>{len(completed)}</div></div>""",
                        unsafe_allow_html=True)
                with c3:
                    avg_score = round(sum(all_scores)/len(all_scores)) if all_scores else "—"
                    st.markdown(f"""<div class='card-sm'>
                        <div class='card-label'>Avg Score</div>
                        <div class='card-value'>{avg_score}</div></div>""",
                        unsafe_allow_html=True)

                st.markdown("<h2>Student Results</h2>", unsafe_allow_html=True)
                for r in results:
                    score_display = ""
                    if r["scores"]:
                        avg = round(sum(r["scores"].values()) / len(r["scores"]))
                        score_display = f"<span class='badge badge-green'>{avg}/100</span>"

                    status_badge = ("<span class='badge badge-green'>Complete</span>"
                                    if r["is_complete"]
                                    else "<span class='badge badge-amber'>In Progress</span>")

                    cps_done = len(r["completed_checkpoints"])

                    with st.expander(f"{r['username']} — {r['started_at'][:10]}"):
                        st.markdown(f"""
                        <div style='display:flex;gap:.75rem;align-items:center;margin-bottom:.75rem;'>
                            {status_badge} {score_display}
                            <span style='font-size:.85rem;color:#8b8680;'>
                                {cps_done} checkpoint(s) completed</span>
                        </div>""", unsafe_allow_html=True)

                        report = get_report(r["session_id"])
                        if report:
                            data = report["data"]
                            st.markdown(f"**Summary:** {data.get('summary','')}")
                            if data.get("scores"):
                                for cat, details in data["scores"].items():
                                    score = details.get("score",0) if isinstance(details,dict) else details
                                    st.markdown(f"- **{cat}:** {score}/100")
                            html = export_report_html(report, r["username"])
                            st.download_button(
                                f"📥 Download Report",
                                html,
                                file_name=f"report_{r['username']}_{r['session_id']}.html",
                                mime="text/html",
                                key=f"dl_{r['session_id']}",
                            )
                        else:
                            st.markdown("<div class='info-strip'>No report yet for this session.</div>",
                                        unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# STUDENT INTERFACE
# ══════════════════════════════════════════════════════════════════════════════
elif role == "Student":

    if "🏠" in page:
        st.markdown("<h1>Welcome back.</h1>", unsafe_allow_html=True)
        cases = get_student_assigned_cases(user_id)
        sessions = get_student_sessions(user_id)
        completed = [s for s in sessions if s["is_complete"] and not s["is_test"]]
        in_progress = [s for s in sessions if not s["is_complete"] and not s["is_test"]]

        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f"""<div class='card-sm'>
                <div class='card-label'>Assigned Cases</div>
                <div class='card-value'>{len(cases)}</div></div>""", unsafe_allow_html=True)
        with c2:
            st.markdown(f"""<div class='card-sm'>
                <div class='card-label'>In Progress</div>
                <div class='card-value'>{len(in_progress)}</div></div>""", unsafe_allow_html=True)
        with c3:
            st.markdown(f"""<div class='card-sm'>
                <div class='card-label'>Completed</div>
                <div class='card-value'>{len(completed)}</div></div>""", unsafe_allow_html=True)

    elif "📋" in page:
        st.markdown("<h1>My Cases</h1>", unsafe_allow_html=True)

        # If in an active session, render the chat
        if st.session_state.get("current_session_id") and st.session_state.get("current_case_id"):
            if st.button("← Back to case list"):
                del st.session_state["current_session_id"]
                del st.session_state["current_case_id"]
                st.rerun()
            _render_case_chat(
                st.session_state.current_session_id,
                st.session_state.current_case_id,
                user_id,
                is_test=False,
            )
        else:
            cases = get_student_assigned_cases(user_id)
            if not cases:
                st.markdown("<div class='info-strip'>No cases assigned yet — check back soon.</div>",
                            unsafe_allow_html=True)
            else:
                for case in cases:
                    resumable = get_resumable_session(user_id, case["id"])
                    with st.container():
                        st.markdown(f"""<div class='card'>
                            <div style='font-size:1.1rem;font-weight:600;color:#2c2c2c;'>
                                {case['title']}</div>
                            <div style='font-size:.85rem;color:#8b8680;margin-top:.25rem;'>
                                {case['course']}</div>
                        </div>""", unsafe_allow_html=True)
                        col1, col2 = st.columns([2, 1])
                        with col2:
                            if resumable:
                                if st.button("▶ Resume", key=f"resume_{case['id']}", type="primary",
                                             use_container_width=True):
                                    st.session_state.current_session_id = resumable
                                    st.session_state.current_case_id = case["id"]
                                    st.rerun()
                                if st.button("Start Over", key=f"newstart_{case['id']}",
                                             use_container_width=True):
                                    session_id = create_session(case["id"], user_id, is_test=False)
                                    st.session_state.current_session_id = session_id
                                    st.session_state.current_case_id = case["id"]
                                    st.rerun()
                            else:
                                if st.button("▶ Start", key=f"start_{case['id']}", type="primary",
                                             use_container_width=True):
                                    session_id = create_session(case["id"], user_id, is_test=False)
                                    st.session_state.current_session_id = session_id
                                    st.session_state.current_case_id = case["id"]
                                    st.rerun()

    elif "📄" in page:
        st.markdown("<h1>My Reports</h1>", unsafe_allow_html=True)
        sessions = get_student_sessions(user_id)
        completed = [s for s in sessions if s["is_complete"] and not s["is_test"]]

        if not completed:
            st.markdown("<div class='info-strip'>No completed cases yet.</div>",
                        unsafe_allow_html=True)
        else:
            for session in completed:
                case = get_case(session["case_id"])
                report = get_report(session["id"])
                with st.expander(f"{case['title']} — {session['started_at'][:10]}"):
                    if report:
                        data = report["data"]
                        total = data.get("total_score", 0)
                        st.markdown(f"""
                        <div style='text-align:center;padding:1rem 0;'>
                            <div class='score-ring'>
                                <div class='score-num'>{total}</div>
                                <div class='score-pct'>/ 100</div>
                            </div>
                        </div>""", unsafe_allow_html=True)
                        st.markdown(f"**Summary:** {data.get('summary','')}")
                        if data.get("improvement_areas"):
                            st.markdown("**Areas to Improve:**")
                            for item in data["improvement_areas"]:
                                st.markdown(f"- {item}")
                        html = export_report_html(report, username)
                        st.download_button(
                            "📥 Download Full Report",
                            html,
                            file_name=f"report_{session['id']}.html",
                            mime="text/html",
                            key=f"dl_s_{session['id']}",
                        )
                    else:
                        st.markdown("<div class='info-strip'>Report not yet generated.</div>",
                                    unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# SHARED: Case Chat Renderer (semi-guided, phase-by-phase)
# ══════════════════════════════════════════════════════════════════════════════
def _render_case_chat(session_id: int, case_id: int, user_id: int, is_test: bool = False):
    session = get_session(session_id)
    case = get_case(case_id)
    blueprint = get_latest_blueprint(case_id)

    if not session or not case or not blueprint:
        st.error("Session or case data not found.")
        return

    state = session["state"]
    phases = blueprint.get("phases", [])
    total_cps = sum(len(p.get("checkpoints", [])) for p in phases)
    completed_cps = len(state.get("completed_checkpoints", []))

    # Header
    st.markdown(f"<h2>{case['title']}</h2>", unsafe_allow_html=True)

    # Progress bar
    pct = int((completed_cps / total_cps) * 100) if total_cps > 0 else 0
    phase_num = state.get("current_phase", 1)
    phase_title = next(
        (p.get("phase_title", f"Phase {p['phase_id']}") for p in phases
         if p.get("phase_id") == phase_num), f"Phase {phase_num}"
    )
    st.markdown(f"""
    <div style='margin-bottom:1.5rem;'>
        <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:.4rem;'>
            <span style='font-size:.8rem;font-weight:600;color:#6a6460;text-transform:uppercase;
                letter-spacing:.8px;'>{phase_title}</span>
            <span style='font-size:.8rem;color:#8b8680;'>
                {completed_cps}/{total_cps} checkpoints</span>
        </div>
        <div class='progress-bar-wrap'>
            <div class='progress-bar-fill' style='width:{pct}%;'></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Phase intro (narrator) — show once when phase starts
    if not state.get("phase_introduced"):
        intro = get_phase_intro(blueprint, phase_num)
        if intro:
            st.markdown(f"""
            <div class='phase-header'>
                <div class='phase-num'>Phase {phase_num} · {phase_title}</div>
                <div class='phase-title' style='font-size:1rem;margin-top:.3rem;color:#5a5a5a;
                    font-family:"DM Sans",sans-serif;font-weight:400;'>{intro}</div>
            </div>""", unsafe_allow_html=True)
            # Mark phase as introduced
            state["phase_introduced"] = True
            save_session_state(session_id, state)

    # Chat transcript
    transcript = get_session_transcript(session_id)
    for msg in transcript:
        avatar = "🎓" if msg["role"] == "assistant" else "👤"
        with st.chat_message(msg["role"] if msg["role"] != "student" else "user",
                             avatar=avatar if msg["role"] == "assistant" else None):
            st.markdown(msg["content"])
            if msg.get("citations"):
                st.caption(f"Sources: chunks {', '.join(map(str, msg['citations']))}")

    # Current checkpoint
    current_cp = get_current_checkpoint(blueprint, state)

    if current_cp and current_cp["checkpoint_key"] not in state.get("completed_checkpoints", []):
        st.markdown(f"""
        <div class='checkpoint-box'>
            <div class='cp-label'>Checkpoint — {current_cp['checkpoint_key']}</div>
            <div style='font-size:1rem;color:#2c2c2c;font-weight:500;margin:.5rem 0;'>
                {current_cp['prompt_to_student']}</div>
        </div>""", unsafe_allow_html=True)

        with st.form(key=f"cp_form_{current_cp['checkpoint_key']}"):
            submission = st.text_area("Your answer", height=120,
                                      placeholder="Write your response here...")
            submitted = st.form_submit_button("Submit Checkpoint", type="primary")
            if submitted and submission.strip():
                with st.spinner("Evaluating your submission..."):
                    eval_result = submit_checkpoint(
                        session_id, case_id,
                        current_cp["checkpoint_key"],
                        submission, user_id
                    )
                if eval_result.get("is_passed"):
                    st.markdown(f"""
                    <div class='success-strip'>
                        <strong>Passed</strong> · Score: {eval_result.get('score',0)}/100<br>
                        {eval_result.get('feedback','')}
                    </div>""", unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class='warn-strip'>
                        <strong>Not yet</strong> · Score: {eval_result.get('score',0)}/100<br>
                        {eval_result.get('feedback','')}<br>
                        <em>{', '.join(eval_result.get('suggestions',[]))}</em>
                    </div>""", unsafe_allow_html=True)
                st.rerun()

    elif not current_cp:
        # All checkpoints done
        st.markdown("""
        <div class='success-strip'>
            All checkpoints complete. You can finalize the case to receive your report.
        </div>""", unsafe_allow_html=True)

        if not session.get("ended_at") and not is_test:
            if st.button("🏁 Finalize Case & Generate Report", type="primary"):
                finalize_session(session_id)
                with st.spinner("Generating your performance report..."):
                    try:
                        report = generate_report(session_id, case_id, user_id)
                        st.session_state.show_report = report
                        st.rerun()
                    except Exception as e:
                        st.error(f"Report error: {str(e)}")

    # Chat input
    if not session.get("ended_at") or is_test:
        user_input = st.chat_input("Ask a question or explore the case...")
        if user_input:
            with st.spinner("Thinking..."):
                try:
                    process_chat_turn(session_id, case_id, user_input, user_id)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {str(e)}")

    # Final report display
    if st.session_state.get("show_report"):
        report = st.session_state.show_report
        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown("<h2>Your Performance Report</h2>", unsafe_allow_html=True)
        total = report.get("total_score", 0)

        col1, col2 = st.columns([1, 3])
        with col1:
            st.markdown(f"""
            <div class='score-ring' style='margin-top:1rem;'>
                <div class='score-num'>{total}</div>
                <div class='score-pct'>/ 100</div>
            </div>""", unsafe_allow_html=True)
        with col2:
            st.markdown(f"**Summary:** {report.get('summary','')}")
            if report.get("scores"):
                for cat, details in report["scores"].items():
                    score = details.get("score",0) if isinstance(details,dict) else details
                    fb = details.get("feedback","") if isinstance(details,dict) else ""
                    st.markdown(f"**{cat}:** {score}/100 — {fb}")

        if report.get("improvement_areas"):
            st.markdown("**Areas to Improve:**")
            for area in report["improvement_areas"]:
                st.markdown(f"- {area}")

        html = export_report_html({"data": report}, st.session_state.get("username","Student"))
        st.download_button(
            "📥 Download Full Report (HTML)",
            html,
            file_name=f"report_{session_id}.html",
            mime="text/html",
        )
