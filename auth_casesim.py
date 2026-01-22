import streamlit as st
import sqlite3
from datetime import datetime
import hashlib
import os

def init_db():
    """Initialize the database with all required tables."""
    db_path = "data/db/casesim.db"
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('Admin', 'Professor', 'Student')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Cases table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            professor_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            course TEXT,
            instructions_text TEXT,
            objectives_json TEXT,
            checkpoints_json TEXT,
            rubric_json TEXT,
            hint_policy TEXT DEFAULT 'coaching',
            status TEXT DEFAULT 'draft' CHECK(status IN ('draft', 'published', 'archived')),
            upload_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (professor_id) REFERENCES users(id)
        )
    """)
    
    # Case chunks (extracted text)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS case_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            location_hint TEXT,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (case_id) REFERENCES cases(id)
        )
    """)
    
    # Case blueprints
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS case_blueprints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL,
            version INTEGER DEFAULT 1,
            blueprint_json TEXT NOT NULL,
            created_by TEXT DEFAULT 'ai',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (case_id) REFERENCES cases(id)
        )
    """)
    
    # Assignments
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (case_id) REFERENCES cases(id),
            FOREIGN KEY (student_id) REFERENCES users(id),
            UNIQUE(case_id, student_id)
        )
    """)
    
    # Sessions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            is_test INTEGER DEFAULT 0,
            state_json TEXT,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP,
            FOREIGN KEY (case_id) REFERENCES cases(id),
            FOREIGN KEY (student_id) REFERENCES users(id)
        )
    """)
    
    # Session messages
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS session_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('student', 'assistant', 'system')),
            content TEXT NOT NULL,
            citations_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """)
    
    # Checkpoint submissions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS checkpoint_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            checkpoint_key TEXT NOT NULL,
            submission_text TEXT NOT NULL,
            is_passed INTEGER DEFAULT 0,
            score REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """)
    
    # Reports
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            report_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(id),
            UNIQUE(session_id)
        )
    """)
    
    # Audit logs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_user_id INTEGER,
            action TEXT NOT NULL,
            entity_type TEXT,
            entity_id INTEGER,
            payload_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (actor_user_id) REFERENCES users(id)
        )
    """)
    
    conn.commit()
    conn.close()

def hash_password(password):
    """Hash password using SHA256."""
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(username, password, role, is_admin_creating=False):
    """Register a new user. Only admins can create users initially."""
    if role not in ['Admin', 'Professor', 'Student']:
        return False, "Invalid role."
    
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO users (username, password_hash, role)
            VALUES (?, ?, ?)
        """, (username, hash_password(password), role))
        conn.commit()
        conn.close()
        return True, f"User '{username}' registered as {role}!"
    except sqlite3.IntegrityError:
        conn.close()
        return False, "Username already exists."
    except Exception as e:
        conn.close()
        return False, f"Error: {str(e)}"

def authenticate_user(username, password):
    """Authenticate user and return (success, role, user_id)."""
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, role, password_hash FROM users WHERE username = ?
    """, (username,))
    result = cursor.fetchone()
    conn.close()
    
    if result and result[2] == hash_password(password):
        return True, result[1], result[0], username
    return False, None, None, None

def require_login():
    """Login/Register interface. Returns (authenticated, role, user_id, username)."""
    init_db()
    
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
        st.session_state.role = None
        st.session_state.user_id = None
        st.session_state.username = None
    
    if st.session_state.authenticated:
        col1, col2 = st.sidebar.columns([3, 1])
        with col1:
            st.sidebar.success(f"{st.session_state.username} ({st.session_state.role})")
        with col2:
            if st.sidebar.button("🚪 Logout"):
                st.session_state.clear()
                st.rerun()
        return True, st.session_state.role, st.session_state.user_id, st.session_state.username
    
    st.sidebar.title("📋 CaseSim")
    tab1, tab2 = st.sidebar.tabs(["Login", "Register"])
    
    with tab1:
        st.subheader("Login")
        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        
        if st.button("Log in"):
            success, role, user_id, username_ret = authenticate_user(username, password)
            if success:
                st.session_state.authenticated = True
                st.session_state.role = role
                st.session_state.user_id = user_id
                st.session_state.username = username_ret
                st.success(f"Logged in as {role}!")
                st.rerun()
            else:
                st.error("Invalid username or password")
    
    with tab2:
        st.subheader("Register")
        reg_role = st.radio("Register as:", ["Professor", "Student"])
        reg_username = st.text_input("Username", key="reg_username")
        reg_password = st.text_input("Password", type="password", key="reg_password")
        
        if st.button("Register"):
            if not reg_username or not reg_password:
                st.error("Username and password are required.")
            else:
                success, msg = register_user(reg_username, reg_password, reg_role)
                if success:
                    st.success(msg)
                    st.info("You can now log in with your credentials!")
                else:
                    st.error(msg)
    
    return False, None, None, None
