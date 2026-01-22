import streamlit as st
import json
from datetime import datetime
from auth_casesim import require_login
from case_manager import (
    create_case, upload_case_file, generate_blueprint, get_latest_blueprint,
    save_blueprint_version, get_professor_cases, get_case, publish_case,
    get_student_assigned_cases, assign_case_to_students, log_audit
)
from simulation import (
    create_session, get_session, process_chat_turn, submit_checkpoint,
    finalize_session, get_student_sessions, get_session_transcript
)
from reporting import generate_report, get_report, render_report_html
from ingest import get_case_chunks

# Page config
st.set_page_config(
    page_title="CaseSim - AI Case Simulation Platform",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .professor-badge { background-color: #e3f2fd; padding: 2px 8px; border-radius: 3px; color: #1976d2; font-size: 0.8em; }
    .student-badge { background-color: #f3e5f5; padding: 2px 8px; border-radius: 3px; color: #7b1fa2; font-size: 0.8em; }
    .case-status-draft { color: #ff9800; }
    .case-status-published { color: #4caf50; }
    .case-status-archived { color: #9e9e9e; }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# Require login
authenticated, role, user_id, username = require_login()

if not authenticated:
    st.stop()

# ============================================================================
# PROFESSOR INTERFACE
# ============================================================================

if role == "Professor":
    st.title("👨‍🏫 Professor Dashboard")
    
    tab1, tab2, tab3, tab4 = st.tabs(["Create Case", "Manage Cases", "Test Sim", "Reports"])
    
    # TAB 1: Create Case
    with tab1:
        st.subheader("Create New Case")
        
        col1, col2 = st.columns(2)
        with col1:
            case_title = st.text_input("Case Title", placeholder="e.g., Supply Chain Crisis")
            course = st.text_input("Course", placeholder="e.g., MBA 501")
        
        with col2:
            hint_policy = st.selectbox("Coaching Policy", ["strict", "coaching", "open"])
        
        st.write("**Learning Objectives** (one per line)")
        objectives_text = st.text_area(
            "objectives",
            placeholder="1. Analyze supply chain risks\n2. Develop contingency plans",
            height=80,
            label_visibility="collapsed"
        )
        objectives = [o.strip() for o in objectives_text.split("\n") if o.strip()]
        
        st.write("**Case File** (PDF or DOCX)")
        uploaded_file = st.file_uploader("Upload case document", type=["pdf", "docx"])
        
        st.write("**Define Checkpoints** (professor-defined milestones)")
        num_checkpoints = st.number_input("Number of checkpoints", 1, 10, 2)
        
        checkpoints = []
        for i in range(num_checkpoints):
            st.write(f"**Checkpoint {i+1}**")
            col1, col2 = st.columns(2)
            with col1:
                cp_key = st.text_input(f"Key (e.g., 'analyze_problem')", key=f"cp_key_{i}")
                cp_prompt = st.text_area(f"Question for student", key=f"cp_prompt_{i}", height=60)
            with col2:
                cp_type = st.selectbox(f"Response type", 
                    ["short_answer", "choose_one", "upload_text"], key=f"cp_type_{i}")
                cp_eval = st.text_area(f"Evaluation notes (instructor only)", 
                    key=f"cp_eval_{i}", height=60)
            
            if cp_key and cp_prompt:
                checkpoints.append({
                    "checkpoint_key": cp_key,
                    "prompt_to_student": cp_prompt,
                    "required_submission_type": cp_type,
                    "evaluation_notes": cp_eval,
                    "progression_rule": "student submits answer"
                })
        
        st.write("**Rubric** (scoring categories)")
        rubric_categories = st.text_area(
            "Categories (JSON format)",
            placeholder='{"Decision Quality": {"weight": 0.4}, "Analysis": {"weight": 0.3}, "Communication": {"weight": 0.3}}',
            height=100
        )
        
        try:
            rubric = json.loads(rubric_categories) if rubric_categories.strip() else {}
        except json.JSONDecodeError:
            st.error("Invalid JSON in rubric categories")
            rubric = {}
        
        professor_instructions = st.text_area(
            "Instructions for AI Blueprint Generator",
            placeholder="Explain what the case is about, key learning goals, decision points...",
            height=100
        )
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Create Case", use_container_width=True):
                if not case_title or not uploaded_file or not checkpoints or not professor_instructions:
                    st.error("Please fill all required fields")
                else:
                    with st.spinner("Creating case..."):
                        try:
                            # Create case
                            case_id = create_case(
                                user_id, case_title, course, professor_instructions,
                                objectives, checkpoints, rubric, hint_policy
                            )
                            st.success(f"Case created! ID: {case_id}")
                            
                            # Upload file
                            file_path = upload_case_file(case_id, uploaded_file)
                            st.info(f"File uploaded: {file_path}")
                            
                            st.session_state.created_case_id = case_id
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {str(e)}")
    
    # TAB 2: Manage Cases
    with tab2:
        st.subheader("My Cases")
        
        cases = get_professor_cases(user_id)
        
        if cases:
            for case in cases:
                col1, col2, col3 = st.columns([3, 1, 1])
                
                with col1:
                    status_color = {
                        "draft": "orange",
                        "published": "green",
                        "archived": "gray"
                    }.get(case["status"], "gray")
                    
                    st.write(f"**{case['title']}** | {case['course']}")
                    st.caption(f"Status: :{status_color}[{case['status'].upper()}] | Created: {case['created_at']}")
                
                with col2:
                    if st.button("📋", key=f"view_{case['id']}"):
                        st.session_state.selected_case_id = case['id']
                
                with col3:
                    if case['status'] == 'draft':
                        if st.button("🚀 Publish", key=f"pub_{case['id']}"):
                            try:
                                publish_case(case['id'], user_id)
                                st.success("Case published!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Publish error: {str(e)}")
            
            # Show selected case details
            if "selected_case_id" in st.session_state:
                st.divider()
                case_id = st.session_state.selected_case_id
                case = get_case(case_id)
                
                if case:
                    st.write(f"### {case['title']}")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**Course:** {case['course']}")
                        st.write(f"**Hint Policy:** {case['hint_policy']}")
                        st.write(f"**Status:** {case['status']}")
                    
                    with col2:
                        st.write(f"**Objectives:** {len(case['objectives'])} defined")
                        st.write(f"**Checkpoints:** {len(case['checkpoints'])} defined")
                        st.write(f"**Created:** {case['created_at']}")
                    
                    # Blueprint management
                    st.write("---")
                    st.write("**Blueprint Management**")
                    
                    blueprint = get_latest_blueprint(case_id)
                    
                    if blueprint:
                        st.success("✅ Blueprint exists (v1)")
                        with st.expander("View Blueprint JSON"):
                            st.json(blueprint)
                        
                        if st.button("🔄 Regenerate Blueprint", key=f"regen_{case_id}"):
                            with st.spinner("Regenerating blueprint..."):
                                try:
                                    new_bp = generate_blueprint(case_id, user_id)
                                    st.success("Blueprint regenerated!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error: {str(e)}")
                    else:
                        if st.button("🤖 Generate Blueprint", key=f"gen_{case_id}"):
                            with st.spinner("Generating blueprint with AI..."):
                                try:
                                    blueprint = generate_blueprint(case_id, user_id)
                                    st.success("Blueprint generated!")
                                    with st.expander("View Generated Blueprint"):
                                        st.json(blueprint)
                                except Exception as e:
                                    st.error(f"Generation error: {str(e)}")
        else:
            st.info("No cases yet. Create one in the 'Create Case' tab.")
    
    # TAB 3: Test Sim
    with tab3:
        st.subheader("Test Case Simulation")
        
        cases = get_professor_cases(user_id)
        if cases:
            case_options = {c['title']: c['id'] for c in cases if c['status'] in ['draft', 'published']}
            
            if case_options:
                selected_case_title = st.selectbox("Select case to test", list(case_options.keys()))
                case_id = case_options[selected_case_title]
                
                if st.button("Start Test Session"):
                    session_id = create_session(case_id, user_id, is_test=True)
                    st.session_state.test_session_id = session_id
                    st.rerun()
                
                if "test_session_id" in st.session_state:
                    st.divider()
                    st.write("**Test Session Chat**")
                    
                    session_id = st.session_state.test_session_id
                    session = get_session(session_id)
                    
                    # Display chat
                    transcript = get_session_transcript(session_id)
                    for msg in transcript:
                        with st.chat_message(msg["role"]):
                            st.write(msg["content"])
                    
                    # Input
                    user_input = st.chat_input("Type your message...")
                    if user_input:
                        with st.spinner("Processing..."):
                            try:
                                result = process_chat_turn(session_id, case_id, user_input, user_id)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {str(e)}")
            else:
                st.info("No cases available for testing.")
        else:
            st.info("Create a case first.")
    
    # TAB 4: Reports
    with tab4:
        st.subheader("Student Reports")
        st.info("Reports are generated automatically when students complete cases.")
        st.write("(Reports view coming soon)")

# ============================================================================
# STUDENT INTERFACE
# ============================================================================

elif role == "Student":
    st.title("🎓 Student Dashboard")
    
    tab1, tab2 = st.tabs(["Available Cases", "My Sessions & Reports"])
    
    # TAB 1: Available Cases
    with tab1:
        st.subheader("Cases Assigned to You")
        
        cases = get_student_assigned_cases(user_id)
        
        if cases:
            for case in cases:
                col1, col2 = st.columns([4, 1])
                
                with col1:
                    st.write(f"**{case['title']}**")
                    st.write(f"Course: {case['course']}")
                    st.caption(f"Created: {case['created_at']}")
                
                with col2:
                    if st.button("▶️ Start", key=f"start_{case['id']}"):
                        session_id = create_session(case['id'], user_id, is_test=False)
                        st.session_state.current_session_id = session_id
                        st.session_state.current_case_id = case['id']
                        st.rerun()
            
            # Case play interface
            if "current_session_id" in st.session_state:
                st.divider()
                session_id = st.session_state.current_session_id
                case_id = st.session_state.current_case_id
                
                case = get_case(case_id)
                st.write(f"### {case['title']}")
                
                # Display transcript
                transcript = get_session_transcript(session_id)
                for msg in transcript:
                    with st.chat_message(msg["role"]):
                        st.write(msg["content"])
                        if msg["citations"]:
                            st.caption(f"Citations: {', '.join(map(str, msg['citations']))}")
                
                # Input
                col1, col2 = st.columns([4, 1])
                with col1:
                    user_input = st.chat_input("Your response...")
                
                with col2:
                    if st.button("Finalize Case", key="finalize"):
                        finalize_session(session_id)
                        
                        # Generate report
                        with st.spinner("Generating report..."):
                            try:
                                report = generate_report(session_id, case_id, user_id)
                                st.session_state.final_report = report
                                st.success("Case complete! View your report below.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Report error: {str(e)}")
                
                if user_input:
                    with st.spinner("Processing..."):
                        try:
                            result = process_chat_turn(session_id, case_id, user_input, user_id)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {str(e)}")
                
                # Show final report if generated
                if "final_report" in st.session_state:
                    st.divider()
                    report = st.session_state.final_report
                    
                    st.write("## 📊 Your Performance Report")
                    st.write(report.get("summary", ""))
                    
                    st.metric("Total Score", f"{report.get('total_score', 0)}/100")
                    
                    if report.get("scores"):
                        cols = st.columns(len(report["scores"]))
                        for col, (cat, details) in zip(cols, report["scores"].items()):
                            with col:
                                score = details.get("score") if isinstance(details, dict) else details
                                st.metric(cat, f"{score}/100")
                    
                    st.write("**Feedback**")
                    st.write(report.get("decision_quality", ""))
                    
                    if report.get("improvement_areas"):
                        st.write("**Areas to Improve**")
                        for area in report["improvement_areas"]:
                            st.write(f"• {area}")
                    
                    # Export
                    html_content = render_report_html(report, username)
                    st.download_button(
                        "📥 Download Report (HTML)",
                        html_content,
                        file_name=f"report_{session_id}.html",
                        mime="text/html"
                    )
        else:
            st.info("No cases assigned yet. Check back soon!")
    
    # TAB 2: My Sessions & Reports
    with tab2:
        st.subheader("Your Session History")
        
        sessions = get_student_sessions(user_id)
        
        if sessions:
            for session in sessions:
                case = get_case(session['case_id'])
                
                col1, col2 = st.columns([3, 1])
                with col1:
                    status_indicator = "✅ Complete" if session['is_complete'] else "🔄 In Progress"
                    st.write(f"**{case['title']}** {status_indicator}")
                    st.caption(f"Started: {session['started_at']}")
                
                with col2:
                    if st.button("📄 View", key=f"view_session_{session['id']}"):
                        st.session_state.view_session_id = session['id']
            
            # Show session details
            if "view_session_id" in st.session_state:
                st.divider()
                session_id = st.session_state.view_session_id
                
                # Check if report exists
                report = get_report(session_id)
                if report:
                    report_data = report["data"]
                    st.write(f"### {report_data.get('title', 'Report')}")
                    st.write(report_data.get("summary", ""))
                    st.metric("Score", f"{report_data.get('total_score', 0)}/100")
                    
                    html_content = render_report_html(report_data)
                    st.download_button(
                        "📥 Download Report",
                        html_content,
                        file_name=f"report_{session_id}.html",
                        mime="text/html"
                    )
                else:
                    st.info("Report not yet generated for this session.")
        else:
            st.info("No sessions yet. Start a case to see history here.")

# ============================================================================
# ADMIN INTERFACE (Basic)
# ============================================================================

elif role == "Admin":
    st.title("⚙️ Admin Panel")
    
    st.write("Admin features coming soon.")
    st.info("Current capabilities: User management via database.")
