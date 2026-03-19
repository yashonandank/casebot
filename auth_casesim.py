import streamlit as st
import sqlite3
import hashlib
import os


def init_db():
    """Initialize the database with all required tables."""
    db_path = "data/db/casesim.db"
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('Admin', 'Professor', 'Student')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS case_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            location_hint TEXT,
            content TEXT NOT NULL,
            embedding_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (case_id) REFERENCES cases(id)
        )
    """)
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS checkpoint_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            checkpoint_key TEXT NOT NULL,
            submission_text TEXT NOT NULL,
            is_passed INTEGER DEFAULT 0,
            score REAL,
            feedback TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """)
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

    _seed_users_from_secrets()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _seed_users_from_secrets():
    """
    Seed users from st.secrets['USERS'] list.
    Each entry: { username, password, role }
    Skips duplicates silently.
    """
    try:
        users = st.secrets.get("USERS", [])
    except Exception:
        return

    if not users:
        return

    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for u in users:
        try:
            cursor.execute(
                "INSERT OR IGNORE INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (u["username"].strip().lower(), hash_password(u["password"]), u["role"])
            )
        except Exception:
            pass

    conn.commit()
    conn.close()


def authenticate_user(username: str, password: str):
    """Returns (success, role, user_id, username) or (False, None, None, None)."""
    db_path = "data/db/casesim.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, role, password_hash FROM users WHERE username = ?",
        (username.strip().lower(),)
    )
    result = cursor.fetchone()
    conn.close()

    if result and result[2] == hash_password(password):
        return True, result[1], result[0], username.strip().lower()
    return False, None, None, None


def require_login():
    """
    Show login screen if not authenticated.
    Returns (authenticated, role, user_id, username).
    """
    init_db()

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
        st.session_state.role = None
        st.session_state.user_id = None
        st.session_state.username = None

    if st.session_state.authenticated:
        return (
            True,
            st.session_state.role,
            st.session_state.user_id,
            st.session_state.username,
        )

    # ── Login UI ──────────────────────────────────────────────────────────────
    st.markdown("""
    <div style='max-width:420px;margin:4rem auto;'>
        <div style='text-align:center;margin-bottom:2rem;'>
            <span style='font-size:0.75rem;font-weight:600;color:#8b8680;
                         text-transform:uppercase;letter-spacing:1.5px;'>
                Goizueta Business School
            </span>
            <h1 style='margin-top:0.5rem;font-family:"Playfair Display",serif;
                       font-size:2.2rem;color:#2c2c2c;letter-spacing:-0.8px;'>
                CaseSim
            </h1>
            <p style='color:#6a6460;font-size:1rem;margin-bottom:0;'>
                AI-powered case simulation platform.
            </p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        username = st.text_input("Username", placeholder="your username")
        password = st.text_input("Password", type="password", placeholder="••••••••")
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Sign In", use_container_width=True):
            success, role, user_id, uname = authenticate_user(username, password)
            if success:
                st.session_state.authenticated = True
                st.session_state.role = role
                st.session_state.user_id = user_id
                st.session_state.username = uname
                st.rerun()
            else:
                st.markdown(
                    "<div class='error-strip'>Invalid username or password.</div>",
                    unsafe_allow_html=True
                )

    return False, None, None, None
