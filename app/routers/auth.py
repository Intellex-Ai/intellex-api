import uuid
import json
import sqlite3
from fastapi import APIRouter, Depends, HTTPException
from app.database import get_db
from app.models import User, LoginRequest, Preferences

router = APIRouter(prefix="/auth", tags=["auth"])

def row_to_user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        email=row["email"],
        name=row["name"],
        avatarUrl=row["avatar_url"],
        preferences=json.loads(row["preferences"] or "{}"),
    )

def get_or_create_user(conn: sqlite3.Connection, email: str, name: str | None) -> User:
    existing = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        return row_to_user(existing)

    new_id = f"user-{uuid.uuid4().hex[:8]}"
    preferences = {"theme": "system"}
    conn.execute(
        """
        INSERT INTO users (id, email, name, avatar_url, preferences)
        VALUES (?, ?, ?, ?, ?)
        """,
        (new_id, email, name or "Intellex User", None, json.dumps(preferences)),
    )
    conn.commit()
    return User(id=new_id, email=email, name=name or "Intellex User", preferences=Preferences(**preferences))

@router.post("/login", response_model=User)
def login(payload: LoginRequest, conn: sqlite3.Connection = Depends(get_db)):
    return get_or_create_user(conn, payload.email, payload.name)

@router.get("/me", response_model=User)
def current_user(conn: sqlite3.Connection = Depends(get_db)):
    row = conn.execute("SELECT * FROM users ORDER BY rowid ASC LIMIT 1").fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No users found")
    return row_to_user(row)
