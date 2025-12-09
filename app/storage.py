import json
import os
import uuid
from datetime import datetime
from typing import Generator, Optional, Protocol, Sequence, Union

from app.models import (
    AgentThought,
    ChatMessage,
    Preferences,
    ResearchPlan,
    ResearchPlanItem,
    ResearchProject,
    User,
    ActivityItem,
    ProjectStats,
    ApiKeyPayload,
    ApiKeysResponse,
    ApiKeySummary,
    ApiKeyRecord,
    ProjectShare,
)
from app.supabase_client import get_supabase
from fastapi import HTTPException
from app.utils.time import now_ms
from app.utils.crypto import encrypt_secret

try:
    from supabase import Client
except ImportError:  # pragma: no cover - optional dependency path
    Client = None  # type: ignore

REQUIRED_SUPABASE_TABLES = ("users", "projects", "research_plans", "messages")
_supabase_ready = False


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
    def list_projects(self, user_id: str) -> list[ResearchProject]: ...
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
    def project_stats(self, user_id: str) -> ProjectStats: ...
    def recent_activity(self, user_id: str, limit: int = 10) -> list[ActivityItem]: ...
    def save_api_keys(self, user_id: str, payload: ApiKeyPayload) -> ApiKeysResponse: ...
    def get_api_keys(self, user_id: str) -> ApiKeysResponse: ...
    def share_project(self, project_id: str, email: str, access: str) -> ProjectShare: ...
    def list_shares(self, project_id: str) -> list[ProjectShare]: ...
    def revoke_share(self, project_id: str, share_id: str) -> None: ...

class SupabaseStore:
    def __init__(self, client: Client):
        self.client = client

    def close(self) -> None:
        # Supabase client does not need explicit close
        return None

    def _load_user_row(self, user_id: str) -> dict:
        row = self.client.table("users").select("*").eq("id", user_id).limit(1).execute()
        if not row.data:
            raise HTTPException(status_code=404, detail="User not found")
        return row.data[0]

    # User operations
    def get_or_create_user(self, email: str, name: Optional[str], supabase_user_id: Optional[str] = None) -> User:
        existing = self.client.table("users").select("*").eq("email", email).limit(1).execute()
        if existing.data:
            user_row = existing.data[0]
            # If the Supabase auth id changed (e.g., password -> OAuth on same email),
            # migrate the account to the current auth uid so RLS stays aligned.
            if supabase_user_id and user_row.get("id") and user_row.get("id") != supabase_user_id:
                old_id = user_row.get("id")
                # Snapshot data for the new row.
                prefs = user_row.get("preferences") or {}
                avatar = user_row.get("avatar_url")
                display_name = user_row.get("name") or name or (email.split("@")[0] if email else "Intellex User")

                try:
                    # Create the target user row if it doesn't already exist.
                    new_row = self.client.table("users").select("*").eq("id", supabase_user_id).limit(1).execute()
                    if not new_row.data:
                        placeholder_email = f"{email}+legacy-{old_id}"
                        # Free the unique email constraint on the legacy row.
                        self.client.table("users").update({"email": placeholder_email}).eq("id", old_id).execute()
                        inserted = (
                            self.client.table("users")
                            .insert(
                                {
                                    "id": supabase_user_id,
                                    "email": email,
                                    "name": display_name,
                                    "avatar_url": avatar,
                                    "preferences": prefs,
                                }
                            )
                            .execute()
                        )
                        if inserted.data:
                            user_row = inserted.data[0]
                    else:
                        user_row = new_row.data[0]

                    # Re-point owned projects to the new auth uid now that the row exists.
                    self.client.table("projects").update({"user_id": supabase_user_id}).eq("user_id", old_id).execute()
                    # Drop the legacy user row to avoid duplicate identities.
                    self.client.table("users").delete().eq("id", old_id).execute()

                    refreshed = (
                        self.client.table("users")
                        .select("*")
                        .eq("id", supabase_user_id)
                        .limit(1)
                        .execute()
                    )
                    if refreshed.data:
                        user_row = refreshed.data[0]
                except Exception as exc:  # pragma: no cover - defensive path
                    raise HTTPException(status_code=503, detail=f"Account merge failed: {exc}")

            # Update the display name if a new non-empty name is provided and differs.
            if name and str(user_row.get("name") or "").strip() != name.strip():
                updated = (
                    self.client.table("users")
                    .update({"name": name.strip()})
                    .eq("id", user_row.get("id"))
                    .execute()
                )
                if updated.data:
                    user_row = updated.data[0]
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
            .execute()
        )
        if inserted.data:
            return to_user(inserted.data[0])
        # Fallback: re-query
        created = self.client.table("users").select("*").eq("id", new_id).limit(1).execute()
        if created.data:
            return to_user(created.data[0])
        raise RuntimeError("Failed to create user")

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
    def list_projects(self, user_id: str) -> list[ResearchProject]:
        result = (
            self.client.table("projects")
            .select("*")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .execute()
        )
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
            .execute()
        )
        if inserted.data:
            return to_project(inserted.data[0])
        created = self.client.table("projects").select("*").eq("id", project_id).limit(1).execute()
        if created.data:
            return to_project(created.data[0])
        raise RuntimeError("Failed to create project")

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
        updated = self.client.table("projects").update(updates).eq("id", project_id).execute()
        if updated.data:
            return to_project(updated.data[0])
        return existing

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
            .execute()
        )
        if inserted.data:
            return to_plan(inserted.data[0])
        created = self.client.table("research_plans").select("*").eq("id", plan_id).limit(1).execute()
        if created.data:
            return to_plan(created.data[0])
        raise RuntimeError("Failed to create research plan")

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
            .execute()
        )
        if updated.data:
            return to_plan(updated.data[0])
        return self.get_plan(project_id)

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

    def save_api_keys(self, user_id: str, payload: ApiKeyPayload) -> ApiKeysResponse:
        if not payload.openai and not payload.anthropic:
            raise HTTPException(status_code=400, detail="At least one API key is required")

        user_row = self._load_user_row(user_id)
        preferences = default_preferences(user_row.get("preferences"))
        current_keys = preferences.apiKeys or {}

        updated_keys: dict[str, ApiKeyRecord] = {}
        now = now_ms()
        if payload.openai:
            ciphertext = encrypt_secret(payload.openai)
            updated_keys["openai"] = ApiKeyRecord(last4=payload.openai[-4:], storedAt=now)
            current_keys["openai"] = {"ciphertext": ciphertext, "last4": payload.openai[-4:], "storedAt": now}
        if payload.anthropic:
            ciphertext = encrypt_secret(payload.anthropic)
            updated_keys["anthropic"] = ApiKeyRecord(last4=payload.anthropic[-4:], storedAt=now)
            current_keys["anthropic"] = {"ciphertext": ciphertext, "last4": payload.anthropic[-4:], "storedAt": now}

        preferences.apiKeys = current_keys
        self.client.table("users").update({"preferences": preferences.model_dump(exclude_none=True)}).eq("id", user_id).execute()

        summaries = [
            ApiKeySummary(provider=k, last4=v.last4, storedAt=v.storedAt)
            for k, v in updated_keys.items()
        ]
        return ApiKeysResponse(keys=summaries)

    def get_api_keys(self, user_id: str) -> ApiKeysResponse:
        user_row = self._load_user_row(user_id)
        preferences = default_preferences(user_row.get("preferences"))
        api_keys = preferences.apiKeys or {}
        summaries: list[ApiKeySummary] = []
        for provider, data in api_keys.items():
            last4 = None
            stored_at = None
            if isinstance(data, dict):
                last4 = data.get("last4")
                stored_at = data.get("storedAt")
            elif isinstance(data, ApiKeyRecord):
                last4 = data.last4
                stored_at = data.storedAt
            if last4 and stored_at:
                summaries.append(ApiKeySummary(provider=provider, last4=last4, storedAt=int(stored_at)))
        return ApiKeysResponse(keys=summaries)

    def share_project(self, project_id: str, email: str, access: str) -> ProjectShare:
        try:
            inserted = (
                self.client.table("project_shares")
                .insert(
                    {
                        "id": f"share-{uuid.uuid4().hex[:8]}",
                        "project_id": project_id,
                        "email": email,
                        "access": access,
                        "invited_at": now_ms(),
                    }
                )
                .execute()
            )
            if inserted.data:
                row = inserted.data[0]
                return ProjectShare(
                    id=row.get("id"),
                    projectId=row.get("project_id"),
                    email=row.get("email"),
                    access=row.get("access"),
                    invitedAt=int(row.get("invited_at")),
                )
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Sharing not configured: {exc}")
        raise HTTPException(status_code=500, detail="Failed to share project")

    def list_shares(self, project_id: str) -> list[ProjectShare]:
        try:
            res = self.client.table("project_shares").select("*").eq("project_id", project_id).order("invited_at", desc=True).execute()
            shares = res.data or []
            return [
                ProjectShare(
                    id=row.get("id"),
                    projectId=row.get("project_id"),
                    email=row.get("email"),
                    access=row.get("access"),
                    invitedAt=int(row.get("invited_at")),
                )
                for row in shares
            ]
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Sharing not configured: {exc}")

    def revoke_share(self, project_id: str, share_id: str) -> None:
        try:
            self.client.table("project_shares").delete().eq("project_id", project_id).eq("id", share_id).execute()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Sharing not configured: {exc}")
    def project_stats(self, user_id: str) -> ProjectStats:
        result = (
            self.client.table("projects")
            .select("status,updated_at")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .execute()
        )
        projects = result.data or []
        total = len(projects)
        active = sum(1 for p in projects if (p.get("status") or "").lower() == "active")
        completed = sum(1 for p in projects if (p.get("status") or "").lower() == "completed")
        day_ago = now_ms() - 24 * 60 * 60 * 1000
        updated_last_day = sum(1 for p in projects if isinstance(p.get("updated_at"), int) and p.get("updated_at") >= day_ago)

        return ProjectStats(
            totalProjects=total,
            activeProjects=active,
            completedProjects=completed,
            updatedLastDay=updated_last_day,
        )

    def recent_activity(self, user_id: str, limit: int = 10) -> list[ActivityItem]:
        result = (
            self.client.table("projects")
            .select("id,title,status,updated_at,created_at,last_message_at")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .limit(max(limit, 1))
            .execute()
        )
        projects = result.data or []
        activities: list[ActivityItem] = []
        for row in projects:
            status = (row.get("status") or "").lower()
            updated_at = row.get("updated_at") or row.get("last_message_at") or row.get("created_at") or now_ms()
            activity_type = "research_completed" if status == "completed" else "project_updated"
            desc = f"Research completed: \"{row.get('title') or 'Untitled'}\"" if activity_type == "research_completed" else f"Project updated: \"{row.get('title') or 'Untitled'}\""
            meta = None
            if row.get("created_at"):
                created_at = int(row["created_at"])
                meta = f"Created {datetime.utcfromtimestamp(created_at / 1000).isoformat()}Z"
            activities.append(
                ActivityItem(
                    id=str(row.get("id")),
                    type=activity_type,
                    description=desc,
                    timestamp=int(updated_at),
                    meta=meta,
                )
            )
        return activities


def get_storage_mode() -> str:
    """
    Report storage availability; Supabase is the only supported backend.
    """
    return "supabase" if get_supabase() else "supabase-unconfigured"


def validate_supabase_schema(client: Client) -> None:
    """
    Ensure the required Supabase tables are reachable. Cache the result to avoid
    redundant checks on every request.
    """
    global _supabase_ready
    if _supabase_ready:
        return

    for table in REQUIRED_SUPABASE_TABLES:
        response = client.table(table).select("id").limit(1).execute()
        if getattr(response, "error", None):
            raise RuntimeError(f"Supabase table '{table}' not ready: {response.error}")
        if not hasattr(response, "data"):
            raise RuntimeError(f"Supabase response from '{table}' missing data")

    _supabase_ready = True


def get_store() -> Generator[DataStore, None, None]:
    """
    FastAPI dependency that yields the Supabase storage backend.
    Returns 503 if Supabase is unavailable or misconfigured.
    """
    client = get_supabase()

    if not client:
        def cleaned(name: str) -> str:
            raw = os.getenv(name, "")
            return raw.strip().strip('"').strip("'")

        missing: list[str] = []
        if not (cleaned("SUPABASE_URL") or cleaned("NEXT_PUBLIC_SUPABASE_URL")):
            missing.append("SUPABASE_URL (or NEXT_PUBLIC_SUPABASE_URL)")
        if not (
            cleaned("SUPABASE_SERVICE_ROLE_KEY")
            or cleaned("SUPABASE_ANON_KEY")
            or cleaned("NEXT_PUBLIC_SUPABASE_ANON_KEY")
        ):
            missing.append("SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_ANON_KEY)")

        hint = "Supabase is required but not configured."
        if missing:
            hint += f" Missing env: {', '.join(missing)}."
        raise HTTPException(
            status_code=503,
            detail=hint + " Set the env vars in your API environment or .env and restart.",
        )

    try:
        validate_supabase_schema(client)
        yield SupabaseStore(client)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Supabase not ready: {exc}")
