import json
import sqlite3
import uuid
from typing import Generator, Optional, Protocol, Sequence, Union

from app.database import DB_PATH, ensure_schema
from app.models import (
    AgentThought,
    ChatMessage,
    Preferences,
    ResearchPlan,
    ResearchPlanItem,
    ResearchProject,
    User,
)
from app.supabase_client import get_supabase
from app.utils.time import now_ms

try:
    from supabase import Client
except ImportError:  # pragma: no cover - optional dependency path
    Client = None  # type: ignore


def default_preferences(raw: Union[str, dict, Preferences, None] = None) -> Preferences:
    if isinstance(raw, Preferences):
        return raw

    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}

    if isinstance(raw, dict):
        return Preferences(**raw)

    return Preferences()


def normalize_plan_items(raw: Union[str, Sequence[ResearchPlanItem], Sequence[dict], None]) -> list[ResearchPlanItem]:
    if raw is None:
        return []

    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = []

    items: list[ResearchPlanItem] = []
    for item in raw:
        if isinstance(item, ResearchPlanItem):
            items.append(item)
        elif isinstance(item, dict):
            items.append(ResearchPlanItem(**item))
    return items


def normalize_thoughts(raw: Union[str, Sequence[AgentThought], Sequence[dict], None]) -> Optional[list[AgentThought]]:
    if raw is None:
        return None

    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None

    thoughts: list[AgentThought] = []
    for item in raw:
        if isinstance(item, AgentThought):
            thoughts.append(item)
        elif isinstance(item, dict):
            thoughts.append(AgentThought(**item))
    return thoughts or None


def default_plan_items(goal_summary: str) -> list[ResearchPlanItem]:
    summary = goal_summary[:60] if goal_summary else "Research objective"
    return [
        ResearchPlanItem(
            id=f"item-{uuid.uuid4().hex[:6]}",
            title="Clarify Objective",
            description=f"Break down the request: {summary}",
            status="in-progress",
        ),
        ResearchPlanItem(
            id=f"item-{uuid.uuid4().hex[:6]}",
            title="Collect Sources",
            description="Query recent papers, reports, and benchmarks.",
            status="pending",
        ),
        ResearchPlanItem(
            id=f"item-{uuid.uuid4().hex[:6]}",
            title="Synthesize Findings",
            description="Draft executive summary with risks and opportunities.",
            status="pending",
        ),
    ]


def to_user(row: dict) -> User:
    return User(
        id=row.get("id"),
        email=row.get("email"),
        name=row.get("name"),
        avatarUrl=row.get("avatar_url"),
        preferences=default_preferences(row.get("preferences")),
    )


def to_project(row: dict) -> ResearchProject:
    return ResearchProject(
        id=row.get("id"),
        userId=row.get("user_id"),
        title=row.get("title"),
        goal=row.get("goal"),
        status=row.get("status"),
        createdAt=int(row.get("created_at")),
        updatedAt=int(row.get("updated_at")),
        lastMessageAt=row.get("last_message_at"),
    )


def to_plan(row: dict) -> ResearchPlan:
    return ResearchPlan(
        id=row.get("id"),
        projectId=row.get("project_id"),
        items=normalize_plan_items(row.get("items")),
        updatedAt=int(row.get("updated_at")),
    )


def to_message(row: dict) -> ChatMessage:
    return ChatMessage(
        id=row.get("id"),
        projectId=row.get("project_id"),
        senderId=row.get("sender_id"),
        senderType=row.get("sender_type"),
        content=row.get("content"),
        thoughts=normalize_thoughts(row.get("thoughts")),
        timestamp=int(row.get("timestamp")),
    )


class DataStore(Protocol):
    def close(self) -> None: ...
    def get_or_create_user(self, email: str, name: Optional[str], supabase_user_id: Optional[str] = None) -> User: ...
    def find_user(self, identifier: str) -> Optional[User]: ...
    def delete_user(self, user_id: Optional[str] = None, email: Optional[str] = None) -> bool: ...
    def get_first_user(self) -> Optional[User]: ...
    def list_projects(self, user_id: Optional[str]) -> list[ResearchProject]: ...
    def create_project(self, title: str, goal: str, user: User) -> ResearchProject: ...
    def get_project(self, project_id: str) -> Optional[ResearchProject]: ...
    def update_project(self, project_id: str, title: Optional[str], goal: Optional[str], status: Optional[str]) -> Optional[ResearchProject]: ...
    def delete_project(self, project_id: str) -> bool: ...
    def ensure_plan_for_project(self, project: ResearchProject) -> ResearchPlan: ...
    def get_plan(self, project_id: str) -> Optional[ResearchPlan]: ...
    def append_plan_item(self, project_id: str, content: str) -> Optional[ResearchPlan]: ...
    def get_messages(self, project_id: str) -> list[ChatMessage]: ...
    def insert_message(self, message: ChatMessage) -> None: ...
    def update_project_timestamps(self, project_id: str, last_message_at: int, updated_at: int) -> None: ...


class SQLiteStore:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def close(self) -> None:
        self.conn.close()

    # User operations
    def get_or_create_user(self, email: str, name: Optional[str], supabase_user_id: Optional[str] = None) -> User:
        existing = self.conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            # Update the display name if a new non-empty name is provided and differs.
            if name and str(existing["name"] or "").strip() != name.strip():
                self.conn.execute("UPDATE users SET name = ? WHERE id = ?", (name.strip(), existing["id"]))
                self.conn.commit()
                existing = self.conn.execute("SELECT * FROM users WHERE id = ?", (existing["id"],)).fetchone()
            return to_user(dict(existing))

        new_id = supabase_user_id or f"user-{uuid.uuid4().hex[:8]}"
        prefs = Preferences()
        display_name = name or (email.split("@")[0] if email else "Intellex User")
        self.conn.execute(
            """
            INSERT INTO users (id, email, name, avatar_url, preferences)
            VALUES (?, ?, ?, ?, ?)
            """,
            (new_id, email, display_name, None, json.dumps(prefs.model_dump(exclude_none=True))),
        )
        self.conn.commit()
        return User(id=new_id, email=email, name=display_name, preferences=prefs, avatarUrl=None)

    def find_user(self, identifier: str) -> Optional[User]:
        row = self.conn.execute(
            "SELECT * FROM users WHERE id = ? OR email = ?",
            (identifier, identifier),
        ).fetchone()
        return to_user(dict(row)) if row else None

    def delete_user(self, user_id: Optional[str] = None, email: Optional[str] = None) -> bool:
        if not user_id and not email:
            raise ValueError("user_id or email is required")

        criteria = user_id or email
        row = self.conn.execute(
            "SELECT * FROM users WHERE id = ? OR email = ?",
            (criteria, criteria),
        ).fetchone()
        if not row:
            return False

        uid = row["id"]
        project_rows = self.conn.execute("SELECT id FROM projects WHERE user_id = ?", (uid,)).fetchall()
        project_ids = [r["id"] for r in project_rows]

        try:
            self.conn.execute("BEGIN")
            if project_ids:
                self.conn.executemany("DELETE FROM messages WHERE project_id = ?", [(pid,) for pid in project_ids])
                self.conn.executemany("DELETE FROM research_plans WHERE project_id = ?", [(pid,) for pid in project_ids])
                self.conn.executemany("DELETE FROM projects WHERE id = ?", [(pid,) for pid in project_ids])

            self.conn.execute("DELETE FROM users WHERE id = ?", (uid,))
            self.conn.commit()
            return True
        except Exception:
            self.conn.rollback()
            raise

    def get_first_user(self) -> Optional[User]:
        row = self.conn.execute("SELECT * FROM users ORDER BY rowid ASC LIMIT 1").fetchone()
        return to_user(dict(row)) if row else None

    # Project operations
    def list_projects(self, user_id: Optional[str]) -> list[ResearchProject]:
        if user_id:
            rows = self.conn.execute(
                "SELECT * FROM projects WHERE user_id = ? ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
        return [to_project(dict(row)) for row in rows]

    def create_project(self, title: str, goal: str, user: User) -> ResearchProject:
        project_id = f"proj-{uuid.uuid4().hex[:8]}"
        timestamp = now_ms()
        self.conn.execute(
            """
            INSERT INTO projects (id, user_id, title, goal, status, created_at, updated_at, last_message_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (project_id, user.id, title, goal, "active", timestamp, timestamp, None),
        )
        self.conn.commit()
        return ResearchProject(
            id=project_id,
            userId=user.id,
            title=title,
            goal=goal,
            status="active",
            createdAt=timestamp,
            updatedAt=timestamp,
            lastMessageAt=None,
        )

    def get_project(self, project_id: str) -> Optional[ResearchProject]:
        row = self.conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return to_project(dict(row)) if row else None

    def update_project(self, project_id: str, title: Optional[str], goal: Optional[str], status: Optional[str]) -> Optional[ResearchProject]:
        existing = self.get_project(project_id)
        if not existing:
            return None

        updates = {}
        if title is not None:
            updates["title"] = title
        if goal is not None:
            updates["goal"] = goal
        if status is not None:
            updates["status"] = status
        if not updates:
            return existing

        updates["updated_at"] = now_ms()
        updates["project_id"] = project_id
        sets = ", ".join([f"{key} = :{key}" for key in updates if key != "project_id"])

        self.conn.execute(f"UPDATE projects SET {sets} WHERE id = :project_id", updates)
        self.conn.commit()
        return self.get_project(project_id)

    def delete_project(self, project_id: str) -> bool:
        existing = self.get_project(project_id)
        if not existing:
            return False
        try:
            self.conn.execute("DELETE FROM messages WHERE project_id = ?", (project_id,))
            self.conn.execute("DELETE FROM research_plans WHERE project_id = ?", (project_id,))
            self.conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            self.conn.commit()
            return True
        except Exception:
            self.conn.rollback()
            raise

    # Plan operations
    def ensure_plan_for_project(self, project: ResearchProject) -> ResearchPlan:
        existing = self.conn.execute(
            "SELECT * FROM research_plans WHERE project_id = ?",
            (project.id,),
        ).fetchone()
        if existing:
            return to_plan(dict(existing))

        items = default_plan_items(project.goal or project.title)
        plan_id = f"plan-{uuid.uuid4().hex[:8]}"
        timestamp = now_ms()
        self.conn.execute(
            """
            INSERT INTO research_plans (id, project_id, items, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (plan_id, project.id, json.dumps([item.model_dump() for item in items]), timestamp),
        )
        self.conn.commit()
        return ResearchPlan(id=plan_id, projectId=project.id, items=items, updatedAt=timestamp)

    def get_plan(self, project_id: str) -> Optional[ResearchPlan]:
        row = self.conn.execute("SELECT * FROM research_plans WHERE project_id = ?", (project_id,)).fetchone()
        return to_plan(dict(row)) if row else None

    def append_plan_item(self, project_id: str, content: str) -> Optional[ResearchPlan]:
        row = self.conn.execute(
            "SELECT * FROM research_plans WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        if not row:
            return None

        plan = to_plan(dict(row))
        new_item = ResearchPlanItem(
            id=f"item-{uuid.uuid4().hex[:6]}",
            title="New Research Lead",
            description=content[:140],
            status="in-progress",
        )
        plan.items.append(new_item)
        plan.updatedAt = now_ms()

        self.conn.execute(
            "UPDATE research_plans SET items = ?, updated_at = ? WHERE id = ?",
            (
                json.dumps([item.model_dump() for item in plan.items]),
                plan.updatedAt,
                plan.id,
            ),
        )
        self.conn.commit()
        return plan

    # Message operations
    def get_messages(self, project_id: str) -> list[ChatMessage]:
        rows = self.conn.execute(
            "SELECT * FROM messages WHERE project_id = ? ORDER BY timestamp ASC",
            (project_id,),
        ).fetchall()
        return [to_message(dict(row)) for row in rows]

    def insert_message(self, message: ChatMessage) -> None:
        self.conn.execute(
            """
            INSERT INTO messages (id, project_id, sender_id, sender_type, content, thoughts, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message.id,
                message.projectId,
                message.senderId,
                message.senderType,
                message.content,
                json.dumps([thought.model_dump() for thought in message.thoughts]) if message.thoughts else None,
                message.timestamp,
            ),
        )
        self.conn.commit()

    def update_project_timestamps(self, project_id: str, last_message_at: int, updated_at: int) -> None:
        self.conn.execute(
            "UPDATE projects SET last_message_at = ?, updated_at = ? WHERE id = ?",
            (last_message_at, updated_at, project_id),
        )
        self.conn.commit()


class SupabaseStore:
    def __init__(self, client: Client):
        self.client = client

    def close(self) -> None:
        # Supabase client does not need explicit close
        return None

    # User operations
    def get_or_create_user(self, email: str, name: Optional[str], supabase_user_id: Optional[str] = None) -> User:
        existing = self.client.table("users").select("*").eq("email", email).limit(1).execute()
        if existing.data:
            user_row = existing.data[0]
            # Update the display name if a new non-empty name is provided and differs.
            if name and str(user_row.get("name") or "").strip() != name.strip():
                updated = (
                    self.client.table("users")
                    .update({"name": name.strip()})
                    .eq("id", user_row.get("id"))
                    .select("*")
                    .single()
                    .execute()
                )
                if updated.data:
                    user_row = updated.data
            return to_user(user_row)

        new_id = supabase_user_id or f"user-{uuid.uuid4().hex[:8]}"
        prefs = Preferences()
        display_name = name or (email.split("@")[0] if email else "Intellex User")
        inserted = (
            self.client.table("users")
            .insert(
                {
                    "id": new_id,
                    "email": email,
                    "name": display_name,
                    "avatar_url": None,
                    "preferences": prefs.model_dump(exclude_none=True),
                }
            )
            .select("*")
            .single()
            .execute()
        )
        return to_user(inserted.data)

    def find_user(self, identifier: str) -> Optional[User]:
        by_email = self.client.table("users").select("*").eq("email", identifier).limit(1).execute()
        if by_email.data:
            return to_user(by_email.data[0])

        by_id = self.client.table("users").select("*").eq("id", identifier).limit(1).execute()
        if by_id.data:
            return to_user(by_id.data[0])

        return None

    def delete_user(self, user_id: Optional[str] = None, email: Optional[str] = None) -> bool:
        if not user_id and not email:
            raise ValueError("user_id or email is required")

        lookup = self.client.table("users").select("*")
        if user_id:
            lookup = lookup.eq("id", user_id)
        elif email:
            lookup = lookup.eq("email", email)
        existing = lookup.limit(1).execute()
        if not existing.data:
            return False

        user_row = existing.data[0]
        uid = user_row.get("id")

        projects = self.client.table("projects").select("id").eq("user_id", uid).execute()
        project_ids = [row.get("id") for row in (projects.data or []) if row.get("id")]

        if project_ids:
            self.client.table("messages").delete().in_("project_id", project_ids).execute()
            self.client.table("research_plans").delete().in_("project_id", project_ids).execute()
            self.client.table("projects").delete().in_("id", project_ids).execute()

        self.client.table("users").delete().eq("id", uid).execute()
        return True

    def get_first_user(self) -> Optional[User]:
        row = self.client.table("users").select("*").order("email", desc=False).limit(1).execute()
        if row.data:
            return to_user(row.data[0])
        return None

    # Project operations
    def list_projects(self, user_id: Optional[str]) -> list[ResearchProject]:
        query = self.client.table("projects").select("*").order("updated_at", desc=True)
        if user_id:
            query = query.eq("user_id", user_id)
        result = query.execute()
        return [to_project(row) for row in result.data or []]

    def create_project(self, title: str, goal: str, user: User) -> ResearchProject:
        project_id = f"proj-{uuid.uuid4().hex[:8]}"
        timestamp = now_ms()
        inserted = (
            self.client.table("projects")
            .insert(
                {
                    "id": project_id,
                    "user_id": user.id,
                    "title": title,
                    "goal": goal,
                    "status": "active",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "last_message_at": None,
                }
            )
            .select("*")
            .single()
            .execute()
        )
        return to_project(inserted.data)

    def get_project(self, project_id: str) -> Optional[ResearchProject]:
        result = self.client.table("projects").select("*").eq("id", project_id).limit(1).execute()
        if result.data:
            return to_project(result.data[0])
        return None

    def update_project(self, project_id: str, title: Optional[str], goal: Optional[str], status: Optional[str]) -> Optional[ResearchProject]:
        existing = self.get_project(project_id)
        if not existing:
            return None

        updates: dict = {}
        if title is not None:
            updates["title"] = title
        if goal is not None:
            updates["goal"] = goal
        if status is not None:
            updates["status"] = status
        if not updates:
            return existing

        updates["updated_at"] = now_ms()
        updated = (
            self.client.table("projects")
            .update(updates)
            .eq("id", project_id)
            .select("*")
            .single()
            .execute()
        )
        return to_project(updated.data) if updated.data else existing

    def delete_project(self, project_id: str) -> bool:
        existing = self.get_project(project_id)
        if not existing:
            return False

        self.client.table("messages").delete().eq("project_id", project_id).execute()
        self.client.table("research_plans").delete().eq("project_id", project_id).execute()
        self.client.table("projects").delete().eq("id", project_id).execute()
        return True

    # Plan operations
    def ensure_plan_for_project(self, project: ResearchProject) -> ResearchPlan:
        existing = self.client.table("research_plans").select("*").eq("project_id", project.id).limit(1).execute()
        if existing.data:
            return to_plan(existing.data[0])

        items = default_plan_items(project.goal or project.title)
        timestamp = now_ms()
        plan_id = f"plan-{uuid.uuid4().hex[:8]}"
        inserted = (
            self.client.table("research_plans")
            .insert(
                {
                    "id": plan_id,
                    "project_id": project.id,
                    "items": [item.model_dump() for item in items],
                    "updated_at": timestamp,
                }
            )
            .select("*")
            .single()
            .execute()
        )
        return to_plan(inserted.data)

    def get_plan(self, project_id: str) -> Optional[ResearchPlan]:
        result = self.client.table("research_plans").select("*").eq("project_id", project_id).limit(1).execute()
        if result.data:
            return to_plan(result.data[0])
        return None

    def append_plan_item(self, project_id: str, content: str) -> Optional[ResearchPlan]:
        existing = self.client.table("research_plans").select("*").eq("project_id", project_id).limit(1).execute()
        if not existing.data:
            return None

        plan = to_plan(existing.data[0])
        plan.items.append(
            ResearchPlanItem(
                id=f"item-{uuid.uuid4().hex[:6]}",
                title="New Research Lead",
                description=content[:140],
                status="in-progress",
            )
        )
        plan.updatedAt = now_ms()

        updated = (
            self.client.table("research_plans")
            .update({"items": [item.model_dump() for item in plan.items], "updated_at": plan.updatedAt})
            .eq("id", plan.id)
            .select("*")
            .single()
            .execute()
        )
        return to_plan(updated.data)

    # Message operations
    def get_messages(self, project_id: str) -> list[ChatMessage]:
        result = (
            self.client.table("messages")
            .select("*")
            .eq("project_id", project_id)
            .order("timestamp", desc=False)
            .execute()
        )
        return [to_message(row) for row in result.data or []]

    def insert_message(self, message: ChatMessage) -> None:
        payload = {
            "id": message.id,
            "project_id": message.projectId,
            "sender_id": message.senderId,
            "sender_type": message.senderType,
            "content": message.content,
            "thoughts": [thought.model_dump() for thought in message.thoughts] if message.thoughts else None,
            "timestamp": message.timestamp,
        }
        self.client.table("messages").insert(payload).execute()

    def update_project_timestamps(self, project_id: str, last_message_at: int, updated_at: int) -> None:
        self.client.table("projects").update(
            {"last_message_at": last_message_at, "updated_at": updated_at}
        ).eq("id", project_id).execute()


def get_storage_mode() -> str:
    return "supabase" if get_supabase() else "sqlite"


def get_store() -> Generator[DataStore, None, None]:
    """
    FastAPI dependency that yields a storage backend.
    Prefers Supabase when configured, falls back to SQLite.
    """
    client = get_supabase()
    if client:
        # Ensure required tables exist; otherwise fall back to SQLite to avoid 500s.
        try:
            probe = client.table("users").select("id").limit(1).execute()
            if getattr(probe, "error", None):
                raise RuntimeError(f"Supabase users table not ready: {probe.error}")
            yield SupabaseStore(client)
            return
        except Exception:
            # Supabase configured but tables not provisioned; continue to SQLite.
            client = None

    # Default to SQLite, ensuring schema exists.
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        ensure_schema(conn)
        conn.commit()
    except Exception:
        # If schema creation fails (e.g., readonly FS), continue; operations may still proceed if file exists.
        pass
    store = SQLiteStore(conn)
    try:
        yield store
    finally:
        store.close()
