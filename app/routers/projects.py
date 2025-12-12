import logging
import uuid
from typing import List

from app.queue import enqueue_message as enqueue_orchestrator_message, get_redis

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from app.models import (
    AgentThought,
    ChatMessage,
    CreateMessageRequest,
    CreateProjectRequest,
    UpdateProjectRequest,
    ResearchPlan,
    ResearchProject,
    SendMessageResponse,
    ProjectStats,
    ActivityItem,
    ShareProjectRequest,
    ProjectShare,
)
from app.services.orchestrator import orchestrator
from app.communications_client import send_email
from app.storage import DataStore, get_store, now_ms
from app.deps.auth import AuthContext, require_supabase_user

router = APIRouter(prefix="/projects", tags=["projects"])
logger = logging.getLogger(__name__)

def _ensure_owner(project: ResearchProject | None, auth_user: AuthContext) -> ResearchProject:
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.userId != auth_user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    return project


@router.get("", response_model=List[ResearchProject])
def list_projects(
    user_id: str = Query(..., alias="userId", min_length=1),
    auth_user: AuthContext = Depends(require_supabase_user),
    store: DataStore = Depends(get_store),
):
    if user_id != auth_user["id"]:
        raise HTTPException(status_code=403, detail="Cannot access projects for another user")

    user = store.find_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return store.list_projects(user.id)

@router.get("/stats", response_model=ProjectStats)
def project_stats(
    user_id: str = Query(..., alias="userId", min_length=1),
    auth_user: AuthContext = Depends(require_supabase_user),
    store: DataStore = Depends(get_store),
):
    if user_id != auth_user["id"]:
        raise HTTPException(status_code=403, detail="Cannot access stats for another user")
    return store.project_stats(user_id)


@router.get("/activity", response_model=List[ActivityItem])
def recent_activity(
    user_id: str = Query(..., alias="userId", min_length=1),
    limit: int = Query(10, ge=1, le=50),
    auth_user: AuthContext = Depends(require_supabase_user),
    store: DataStore = Depends(get_store),
):
    if user_id != auth_user["id"]:
        raise HTTPException(status_code=403, detail="Cannot access activity for another user")
    return store.recent_activity(user_id, limit)


@router.get("/{project_id}/shares", response_model=List[ProjectShare])
def list_project_shares(
    project_id: str,
    auth_user: AuthContext = Depends(require_supabase_user),
    store: DataStore = Depends(get_store),
):
    _ensure_owner(store.get_project(project_id), auth_user)
    return store.list_shares(project_id)


@router.post("/{project_id}/shares", response_model=ProjectShare, status_code=201)
def share_project(
    project_id: str,
    payload: ShareProjectRequest,
    background_tasks: BackgroundTasks,
    auth_user: AuthContext = Depends(require_supabase_user),
    store: DataStore = Depends(get_store),
):
    _ensure_owner(store.get_project(project_id), auth_user)
    if not payload.email:
        raise HTTPException(status_code=400, detail="email is required")
    access = payload.access or "viewer"
    if access not in {"viewer", "editor"}:
        raise HTTPException(status_code=400, detail="access must be viewer or editor")
    shared = store.share_project(project_id, payload.email, access)

    project = store.get_project(project_id)
    if project:
        background_tasks.add_task(
            send_email,
            to=payload.email,
            template="project-share",
            subject=f"You've been invited to '{project.title}'",
            data={
                "projectId": project_id,
                "access": access,
                "inviterEmail": auth_user.get("email"),
            },
            metadata={
                "projectId": project_id,
                "userId": auth_user.get("id"),
                "source": "api",
            },
        )

    return shared


@router.delete("/{project_id}/shares/{share_id}", status_code=204)
def revoke_project_share(
    project_id: str,
    share_id: str,
    auth_user: AuthContext = Depends(require_supabase_user),
    store: DataStore = Depends(get_store),
):
    _ensure_owner(store.get_project(project_id), auth_user)
    store.revoke_share(project_id, share_id)
    return None

@router.post("", response_model=ResearchProject, status_code=201)
def create_project(
    payload: CreateProjectRequest,
    auth_user: AuthContext = Depends(require_supabase_user),
    store: DataStore = Depends(get_store),
):
    if not payload.userId:
        raise HTTPException(status_code=400, detail="userId is required to create a project.")
    if payload.userId != auth_user["id"]:
        raise HTTPException(status_code=403, detail="Cannot create projects for another user")

    user = store.find_user(payload.userId)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    project = store.create_project(payload.title, payload.goal, user)
    store.ensure_plan_for_project(project)
    return project

@router.get("/{project_id}", response_model=ResearchProject)
def get_project(
    project_id: str,
    auth_user: AuthContext = Depends(require_supabase_user),
    store: DataStore = Depends(get_store),
):
    project = _ensure_owner(store.get_project(project_id), auth_user)
    return project

@router.patch("/{project_id}", response_model=ResearchProject)
def update_project(
    project_id: str,
    payload: UpdateProjectRequest,
    auth_user: AuthContext = Depends(require_supabase_user),
    store: DataStore = Depends(get_store),
):
    _ensure_owner(store.get_project(project_id), auth_user)

    project = store.update_project(
        project_id,
        title=payload.title,
        goal=payload.goal,
        status=payload.status,
    )
    return _ensure_owner(project, auth_user)

@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: str,
    auth_user: AuthContext = Depends(require_supabase_user),
    store: DataStore = Depends(get_store),
):
    project = _ensure_owner(store.get_project(project_id), auth_user)
    deleted = store.delete_project(project.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    return None

@router.get("/{project_id}/plan", response_model=ResearchPlan)
def get_plan(
    project_id: str,
    auth_user: AuthContext = Depends(require_supabase_user),
    store: DataStore = Depends(get_store),
):
    plan = store.get_plan(project_id)
    if plan:
        _ensure_owner(store.get_project(project_id), auth_user)
        return plan

    project = store.get_project(project_id)
    project = _ensure_owner(project, auth_user)

    return store.ensure_plan_for_project(project)

@router.get("/{project_id}/messages", response_model=List[ChatMessage])
def get_messages(
    project_id: str,
    auth_user: AuthContext = Depends(require_supabase_user),
    store: DataStore = Depends(get_store),
):
    project = _ensure_owner(store.get_project(project_id), auth_user)
    return store.get_messages(project.id)



@router.post("/{project_id}/messages", response_model=SendMessageResponse, status_code=202)
async def send_message(
    project_id: str,
    payload: CreateMessageRequest,
    auth_user: AuthContext = Depends(require_supabase_user),
    store: DataStore = Depends(get_store),
):
    project = _ensure_owner(store.get_project(project_id), auth_user)

    timestamp = now_ms()
    user_message_id = f"msg-{uuid.uuid4().hex[:8]}"

    user_msg = ChatMessage(
        id=user_message_id,
        projectId=project.id,
        senderId=project.userId,
        senderType="user",
        content=payload.content,
        timestamp=timestamp,
    )
    store.insert_message(user_msg)

    updated_plan = store.append_plan_item(project.id, payload.content)

    # If Redis is configured, enqueue orchestration work and return a placeholder agent message.
    if get_redis():
        try:
            job_id, agent_message_id = await enqueue_orchestrator_message(
                project=project,
                user_content=payload.content,
                callback_path="/orchestrator/callback",
            )
            agent_timestamp = timestamp + 500
            placeholder_thought = AgentThought(
                id=f"th-{uuid.uuid4().hex[:8]}",
                title="Queued",
                content="Message queued for processing.",
                status="thinking",
                timestamp=agent_timestamp,
            )
            agent_msg = ChatMessage(
                id=agent_message_id,
                projectId=project.id,
                senderId="agent-researcher",
                senderType="agent",
                content=f"Processing (job {job_id})…",
                thoughts=[placeholder_thought],
                timestamp=agent_timestamp,
            )
            store.insert_message(agent_msg)
            store.update_project_timestamps(project.id, agent_timestamp, agent_timestamp)
            return SendMessageResponse(
                userMessage=user_msg,
                agentMessage=agent_msg,
                jobId=job_id,
                agentMessageId=agent_message_id,
                plan=updated_plan,
            )
        except Exception as exc:
            # Fall back to inline orchestration if enqueue fails.
            logger.warning("Redis enqueue failed; falling back to inline orchestration", exc_info=exc)

    # Inline orchestrator path (dev / no Redis).
    agent_content, thoughts = await orchestrator.process_message(project, payload.content)

    agent_message_id = f"msg-{uuid.uuid4().hex[:8]}"
    agent_timestamp = timestamp + 1500

    agent_msg = ChatMessage(
        id=agent_message_id,
        projectId=project.id,
        senderId="agent-researcher",
        senderType="agent",
        content=agent_content,
        thoughts=thoughts,
        timestamp=agent_timestamp,
    )

    store.insert_message(agent_msg)
    store.update_project_timestamps(project.id, agent_timestamp, agent_timestamp)

    return SendMessageResponse(userMessage=user_msg, agentMessage=agent_msg, plan=updated_plan)
