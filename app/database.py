import sqlite3
from pathlib import Path
from typing import Generator

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "intellex.db"

def get_db() -> Generator[sqlite3.Connection, None, None]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

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
    conn.commit()
    conn.close()
