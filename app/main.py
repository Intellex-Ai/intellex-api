import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Iterable, List, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

APP_VERSION = "0.2.0"
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "intellex.db"


def now_ms() -> int:
    return int(time.time() * 1000)


def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def execute_script(conn: sqlite3.Connection, script: str, params: Iterable = ()):
    conn.execute(script, params)
    conn.commit()


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

    # Seed demo data if empty
    user_count = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()["count"]
    if user_count == 0:
        conn.execute(
            """
            INSERT INTO users (id, email, name, avatar_url, preferences)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "user-1",
                "demo@intellex.ai",
                "Demo Researcher",
                "https://api.dicebear.com/7.x/avataaars/svg?seed=Felix",
                json.dumps({"theme": "system"}),
            ),
        )

    project_count = conn.execute("SELECT COUNT(*) as count FROM projects").fetchone()["count"]
    if project_count == 0:
        now = now_ms()
        conn.execute(
            """
            INSERT INTO projects (id, user_id, title, goal, status, created_at, updated_at, last_message_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "proj-1",
                "user-1",
                "Quantum Computing Trends 2025",
                "Analyze the emerging trends in Quantum Computing for the next fiscal year.",
                "active",
                now - 1000 * 60 * 60 * 24 * 2,
                now,
                now,
            ),
        )

        plan_items = [
            {
                "id": "item-1",
                "title": "Market Analysis",
                "description": "Analyze current market leaders and investment flows.",
                "status": "completed",
            },
            {
                "id": "item-2",
                "title": "Technology Assessment",
                "description": "Evaluate superconducting vs trapped ion qubits.",
                "status": "in-progress",
                "subItems": [
                    {"id": "sub-1", "title": "IBM Roadmap", "description": "", "status": "completed"},
                    {"id": "sub-2", "title": "IonQ Progress", "description": "", "status": "in-progress"},
                ],
            },
        ]

        conn.execute(
            """
            INSERT INTO research_plans (id, project_id, items, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            ("plan-1", "proj-1", json.dumps(plan_items), now),
        )

        demo_messages = [
            (
                "msg-1",
                "proj-1",
                "user-1",
                "user",
                "I need to understand the current state of Quantum Computing.",
                None,
                now - 100000,
            ),
            (
                "msg-2",
                "proj-1",
                "agent-planner",
                "agent",
                "I can help with that. I will start by analyzing the market landscape and then dive into specific technologies. Does that sound good?",
                json.dumps(
                    [
                        {
                            "id": "th-1",
                            "title": "Analyzing Request",
                            "content": "User wants a broad overview. Breaking into Market and Technology.",
                            "status": "completed",
                            "timestamp": now - 95000,
                        }
                    ]
                ),
                now - 90000,
            ),
        ]

        conn.executemany(
            """
            INSERT INTO messages (id, project_id, sender_id, sender_type, content, thoughts, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            demo_messages,
        )

    conn.commit()
    conn.close()


# Schemas
class Preferences(BaseModel):
    theme: str = "system"


class User(BaseModel):
    id: str
    email: str
    name: str
    avatarUrl: Optional[str] = None
    preferences: Preferences

    class Config:
        json_schema_extra = {"example": {"id": "user-1", "email": "demo@intellex.ai", "name": "Demo Researcher"}}


class LoginRequest(BaseModel):
    email: str = Field(..., example="demo@intellex.ai")
    name: Optional[str] = Field(None, example="Demo Researcher")


class ResearchProject(BaseModel):
    id: str
    userId: str
    title: str
    goal: str
    status: str
    createdAt: int
    updatedAt: int
    lastMessageAt: Optional[int] = None


class ResearchPlanItem(BaseModel):
    id: str
    title: str
    description: str
    status: str
    subItems: Optional[List["ResearchPlanItem"]] = None


ResearchPlanItem.model_rebuild()


class ResearchPlan(BaseModel):
    id: str
    projectId: str
    items: List[ResearchPlanItem]
    updatedAt: int


class AgentThought(BaseModel):
    id: str
    title: str
    content: str
    status: str
    timestamp: int


class ChatMessage(BaseModel):
    id: str
    projectId: str
    senderId: str
    senderType: str
    content: str
    thoughts: Optional[List[AgentThought]] = None
    timestamp: int


class CreateProjectRequest(BaseModel):
    title: str
    goal: str
    userId: Optional[str] = None


class CreateMessageRequest(BaseModel):
    content: str


class SendMessageResponse(BaseModel):
    userMessage: ChatMessage
    agentMessage: ChatMessage
    plan: Optional[ResearchPlan] = None


def row_to_user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        email=row["email"],
        name=row["name"],
        avatarUrl=row["avatar_url"],
        preferences=json.loads(row["preferences"] or "{}"),
    )


def row_to_project(row: sqlite3.Row) -> ResearchProject:
    return ResearchProject(
        id=row["id"],
        userId=row["user_id"],
        title=row["title"],
        goal=row["goal"],
        status=row["status"],
        createdAt=row["created_at"],
        updatedAt=row["updated_at"],
        lastMessageAt=row["last_message_at"],
    )


def row_to_plan(row: sqlite3.Row) -> ResearchPlan:
    return ResearchPlan(
        id=row["id"],
        projectId=row["project_id"],
        items=json.loads(row["items"] or "[]"),
        updatedAt=row["updated_at"],
    )


def row_to_message(row: sqlite3.Row) -> ChatMessage:
    return ChatMessage(
        id=row["id"],
        projectId=row["project_id"],
        senderId=row["sender_id"],
        senderType=row["sender_type"],
        content=row["content"],
        thoughts=json.loads(row["thoughts"]) if row["thoughts"] else None,
        timestamp=row["timestamp"],
    )


def get_or_create_user(conn: sqlite3.Connection, email: str, name: Optional[str]) -> User:
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


def ensure_plan_for_project(conn: sqlite3.Connection, project: ResearchProject) -> ResearchPlan:
    existing = conn.execute(
        "SELECT * FROM research_plans WHERE project_id = ?", (project.id,)
    ).fetchone()
    if existing:
        return row_to_plan(existing)

    now = now_ms()
    plan_id = f"plan-{uuid.uuid4().hex[:8]}"
    goal_summary = project.goal or project.title
    items = [
        {
            "id": f"item-{uuid.uuid4().hex[:6]}",
            "title": "Clarify Objective",
            "description": f"Break down the request: {goal_summary[:60]}",
            "status": "in-progress",
        },
        {
            "id": f"item-{uuid.uuid4().hex[:6]}",
            "title": "Collect Sources",
            "description": "Query recent papers, reports, and benchmarks.",
            "status": "pending",
        },
        {
            "id": f"item-{uuid.uuid4().hex[:6]}",
            "title": "Synthesize Findings",
            "description": "Draft executive summary with risks and opportunities.",
            "status": "pending",
        },
    ]

    conn.execute(
        """
        INSERT INTO research_plans (id, project_id, items, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        (plan_id, project.id, json.dumps(items), now),
    )
    conn.commit()
    return ResearchPlan(id=plan_id, projectId=project.id, items=items, updatedAt=now)


def append_plan_item(conn: sqlite3.Connection, project_id: str, content: str) -> Optional[ResearchPlan]:
    row = conn.execute("SELECT * FROM research_plans WHERE project_id = ?", (project_id,)).fetchone()
    if not row:
        return None

    plan = row_to_plan(row)
    new_item = {
        "id": f"item-{uuid.uuid4().hex[:6]}",
        "title": "New Research Lead",
        "description": content[:140],
        "status": "in-progress",
    }
    plan.items.append(ResearchPlanItem(**new_item))
    plan.updatedAt = now_ms()

    conn.execute(
        "UPDATE research_plans SET items = ?, updated_at = ? WHERE id = ?",
        (json.dumps([item.model_dump() if isinstance(item, ResearchPlanItem) else item for item in plan.items]), plan.updatedAt, plan.id),
    )
    conn.commit()
    return plan


def craft_agent_reply(project: ResearchProject, user_content: str) -> tuple[str, List[dict]]:
    thoughts = [
        {
            "id": f"th-{uuid.uuid4().hex[:8]}",
            "title": "Parsing request",
            "content": f"Identified focus: {user_content[:90]}",
            "status": "completed",
            "timestamp": now_ms(),
        },
        {
            "id": f"th-{uuid.uuid4().hex[:8]}",
            "title": "Next actions",
            "content": "Pulling recent sources and updating the plan with a new research lead.",
            "status": "thinking",
            "timestamp": now_ms(),
        },
    ]

    content = (
        f"I will dig into \"{user_content}\" within the context of {project.title}. "
        f"Expect a snapshot of recent sources and a synthesis next. "
        f"Current objective: {project.goal}"
    )
    return content, thoughts


app = FastAPI(
    title="Intellex API",
    description="Backend for Intellex Research SaaS",
    version=APP_VERSION,
)

# Configure CORS
frontend_origins = os.getenv("FRONTEND_ORIGINS", "http://localhost:3100,http://localhost:3001").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in frontend_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/")
async def root():
    return {
        "message": "Intellex API is online",
        "status": "system_ready",
        "version": APP_VERSION,
    }


@app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": now_ms()}


@app.post("/auth/login", response_model=User)
def login(payload: LoginRequest, conn: sqlite3.Connection = Depends(get_db)):
    return get_or_create_user(conn, payload.email, payload.name)


@app.get("/auth/me", response_model=User)
def current_user(conn: sqlite3.Connection = Depends(get_db)):
    row = conn.execute("SELECT * FROM users ORDER BY rowid ASC LIMIT 1").fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No users found")
    return row_to_user(row)


@app.get("/projects", response_model=List[ResearchProject])
def list_projects(user_id: Optional[str] = None, conn: sqlite3.Connection = Depends(get_db)):
    if user_id:
        rows = conn.execute("SELECT * FROM projects WHERE user_id = ? ORDER BY updated_at DESC", (user_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
    return [row_to_project(row) for row in rows]


@app.post("/projects", response_model=ResearchProject, status_code=201)
def create_project(payload: CreateProjectRequest, conn: sqlite3.Connection = Depends(get_db)):
    user_row = conn.execute("SELECT * FROM users WHERE id = ? OR email = ?", (payload.userId, payload.userId)).fetchone()
    if not user_row:
        # Fallback to first user
        user_row = conn.execute("SELECT * FROM users ORDER BY rowid ASC LIMIT 1").fetchone()
    if not user_row:
        raise HTTPException(status_code=400, detail="No user available to assign project.")

    user = row_to_user(user_row)
    project_id = f"proj-{uuid.uuid4().hex[:8]}"
    now = now_ms()
    conn.execute(
        """
        INSERT INTO projects (id, user_id, title, goal, status, created_at, updated_at, last_message_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (project_id, user.id, payload.title, payload.goal, "active", now, now, None),
    )
    conn.commit()

    project = ResearchProject(
        id=project_id,
        userId=user.id,
        title=payload.title,
        goal=payload.goal,
        status="active",
        createdAt=now,
        updatedAt=now,
        lastMessageAt=None,
    )
    ensure_plan_for_project(conn, project)
    return project


@app.get("/projects/{project_id}", response_model=ResearchProject)
def get_project(project_id: str, conn: sqlite3.Connection = Depends(get_db)):
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    return row_to_project(row)


@app.get("/projects/{project_id}/plan", response_model=ResearchPlan)
def get_plan(project_id: str, conn: sqlite3.Connection = Depends(get_db)):
    row = conn.execute("SELECT * FROM research_plans WHERE project_id = ?", (project_id,)).fetchone()
    if not row:
        # If plan does not exist yet, create a starter one.
        project_row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project_row:
            raise HTTPException(status_code=404, detail="Project not found")
        project = row_to_project(project_row)
        return ensure_plan_for_project(conn, project)
    return row_to_plan(row)


@app.get("/projects/{project_id}/messages", response_model=List[ChatMessage])
def get_messages(project_id: str, conn: sqlite3.Connection = Depends(get_db)):
    rows = conn.execute(
        "SELECT * FROM messages WHERE project_id = ? ORDER BY timestamp ASC", (project_id,)
    ).fetchall()
    return [row_to_message(row) for row in rows]


@app.post("/projects/{project_id}/messages", response_model=SendMessageResponse)
def send_message(project_id: str, payload: CreateMessageRequest, conn: sqlite3.Connection = Depends(get_db)):
    project_row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not project_row:
        raise HTTPException(status_code=404, detail="Project not found")

    project = row_to_project(project_row)
    timestamp = now_ms()
    user_message_id = f"msg-{uuid.uuid4().hex[:8]}"

    conn.execute(
        """
        INSERT INTO messages (id, project_id, sender_id, sender_type, content, thoughts, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (user_message_id, project.id, project.userId, "user", payload.content, None, timestamp),
    )

    agent_content, thoughts = craft_agent_reply(project, payload.content)
    agent_message_id = f"msg-{uuid.uuid4().hex[:8]}"
    agent_timestamp = timestamp + 1500

    conn.execute(
        """
        INSERT INTO messages (id, project_id, sender_id, sender_type, content, thoughts, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (agent_message_id, project.id, "agent-researcher", "agent", agent_content, json.dumps(thoughts), agent_timestamp),
    )

    conn.execute(
        "UPDATE projects SET last_message_at = ?, updated_at = ? WHERE id = ?",
        (agent_timestamp, agent_timestamp, project.id),
    )

    updated_plan = append_plan_item(conn, project.id, payload.content)

    user_msg = ChatMessage(
        id=user_message_id,
        projectId=project.id,
        senderId=project.userId,
        senderType="user",
        content=payload.content,
        timestamp=timestamp,
    )

    agent_msg = ChatMessage(
        id=agent_message_id,
        projectId=project.id,
        senderId="agent-researcher",
        senderType="agent",
        content=agent_content,
        thoughts=[AgentThought(**t) for t in thoughts],
        timestamp=agent_timestamp,
    )

    return SendMessageResponse(userMessage=user_msg, agentMessage=agent_msg, plan=updated_plan)
