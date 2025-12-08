import os
import sqlite3
from pathlib import Path
from typing import Generator

BASE_DIR = Path(__file__).resolve().parent
# Default to /tmp in serverless (Vercel) to avoid read-only filesystem; allow override via env.
DB_PATH = Path(os.getenv("DB_PATH", "/tmp/intellex.db"))

def ensure_schema(conn: sqlite3.Connection) -> None:
    """
    Create core tables if they do not exist.
    Kept idempotent so it can be called from multiple initialization paths.
    """
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE,
            name TEXT,
            avatar_url TEXT,
            preferences TEXT
        );

        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            title TEXT,
            goal TEXT,
            status TEXT,
            created_at INTEGER,
            updated_at INTEGER,
            last_message_at INTEGER,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS research_plans (
            id TEXT PRIMARY KEY,
            project_id TEXT UNIQUE,
            items TEXT,
            updated_at INTEGER,
            FOREIGN KEY (project_id) REFERENCES projects (id)
        );

        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            sender_id TEXT,
            sender_type TEXT,
            content TEXT,
            thoughts TEXT,
            timestamp INTEGER,
            FOREIGN KEY (project_id) REFERENCES projects (id)
        );
        """
    )

def get_db() -> Generator[sqlite3.Connection, None, None]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    ensure_schema(conn)
    conn.commit()
    conn.close()

def check_db_health() -> dict:
    """
    Return lightweight database health info: path, presence of core tables, and user count.
    """
    conn = None
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")

        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        required_tables = {"users", "projects", "research_plans", "messages"}
        missing = sorted(required_tables - tables)

        user_count = None
        if "users" in tables:
            user_count = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()["count"]

        status = "ok" if not missing else "degraded"
        return {
            "status": status,
            "path": str(DB_PATH),
            "missingTables": missing,
            "userCount": user_count,
        }
    except Exception as exc:  # pragma: no cover - simple runtime guard
        return {"status": "error", "path": str(DB_PATH), "error": str(exc)}
    finally:
        if conn:
            conn.close()
