import uuid
import json
import sqlite3
import time
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from app.database import get_db
from app.models import (
    ResearchProject,
    ResearchPlan,
    ResearchPlanItem,
    ChatMessage,
    CreateProjectRequest,
    CreateMessageRequest,
    SendMessageResponse,
    AgentThought,
    User
)
from app.services.orchestrator import orchestrator

router = APIRouter(prefix="/projects", tags=["projects"])

def now_ms() -> int:
    return int(time.time() * 1000)

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


@router.get("", response_model=List[ResearchProject])
def list_projects(user_id: Optional[str] = None, conn: sqlite3.Connection = Depends(get_db)):
    if user_id:
        rows = conn.execute("SELECT * FROM projects WHERE user_id = ? ORDER BY updated_at DESC", (user_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
    return [row_to_project(row) for row in rows]

@router.post("", response_model=ResearchProject, status_code=201)
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

@router.get("/{project_id}", response_model=ResearchProject)
def get_project(project_id: str, conn: sqlite3.Connection = Depends(get_db)):
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    return row_to_project(row)

@router.get("/{project_id}/plan", response_model=ResearchPlan)
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

@router.get("/{project_id}/messages", response_model=List[ChatMessage])
def get_messages(project_id: str, conn: sqlite3.Connection = Depends(get_db)):
    rows = conn.execute(
        "SELECT * FROM messages WHERE project_id = ? ORDER BY timestamp ASC", (project_id,)
    ).fetchall()
    return [row_to_message(row) for row in rows]



@router.post("/{project_id}/messages", response_model=SendMessageResponse)
async def send_message(project_id: str, payload: CreateMessageRequest, conn: sqlite3.Connection = Depends(get_db)):
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

    # Use Orchestrator to generate response
    agent_content, thoughts = await orchestrator.process_message(project, payload.content)
    
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
