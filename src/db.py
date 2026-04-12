"""
db.py — Centralized SQLite database helper for NetAI Agent
"""
import sqlite3
import datetime
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "netai.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_all_tables():
    conn = get_conn()
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            username     TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role         TEXT DEFAULT 'viewer',
            created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS devices (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            ip           TEXT NOT NULL UNIQUE,
            type         TEXT DEFAULT 'router',
            location     TEXT DEFAULT '',
            ssh_user     TEXT DEFAULT '',
            ssh_pass     TEXT DEFAULT '',
            enable_pass  TEXT DEFAULT '',
            status       TEXT DEFAULT 'unknown',
            last_seen    DATETIME,
            created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS diagnostics_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            query        TEXT,
            device_ip    TEXT,
            severity     TEXT,
            root_cause   TEXT,
            intent       TEXT,
            created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)

    conn.commit()
    conn.close()
    print("✅ Database tables initialized.")


def seed_default_user():
    """Insert default admin user if users table is empty."""
    try:
        import bcrypt as _bcrypt
        hashed = _bcrypt.hashpw(b"admin123", _bcrypt.gensalt()).decode()
    except ImportError:
        print("⚠️  bcrypt not installed — skipping user seed")
        return

    conn = get_conn()
    existing = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if existing == 0:
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("admin", hashed, "admin")
        )
        conn.commit()
        print("✅ Default user created: admin / admin123")
    conn.close()


def seed_demo_devices():
    """Insert demo devices if devices table is empty."""
    conn = get_conn()
    existing = conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
    if existing == 0:
        demo = [
            ("Core Switch",     "192.168.1.1",   "switch",   "Server Room A", "admin", "cisco123", "enable123"),
            ("Core Router",     "192.168.1.254",  "router",   "Server Room A", "admin", "cisco123", "enable123"),
            ("Access Switch 1", "192.168.1.2",   "switch",   "Floor 2",       "admin", "cisco123", ""),
            ("Access Switch 2", "192.168.1.3",   "switch",   "Floor 3",       "admin", "cisco123", ""),
        ]
        conn.executemany(
            "INSERT INTO devices (name, ip, type, location, ssh_user, ssh_pass, enable_pass) VALUES (?,?,?,?,?,?,?)",
            demo
        )
        conn.commit()
        print("✅ Demo devices seeded.")
    conn.close()


def log_diagnostic(query: str, device_ip: str, severity: str, root_cause: str, intent: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO diagnostics_log (query, device_ip, severity, root_cause, intent, created_at) VALUES (?,?,?,?,?,?)",
        (query, device_ip, severity, root_cause, intent, datetime.datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
