import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.models import (
    AgentThought,
    ChatMessage,
    CreateMessageRequest,
    CreateProjectRequest,
    UpdateProjectRequest,
    ResearchPlan,
    ResearchProject,
    SendMessageResponse,
)
from app.services.orchestrator import orchestrator
from app.storage import DataStore, get_store, now_ms

router = APIRouter(prefix="/projects", tags=["projects"])

@router.get("", response_model=List[ResearchProject])
def list_projects(user_id: Optional[str] = None, store: DataStore = Depends(get_store)):
    return store.list_projects(user_id)

@router.post("", response_model=ResearchProject, status_code=201)
def create_project(payload: CreateProjectRequest, store: DataStore = Depends(get_store)):
    user = None
    if payload.userId:
        user = store.find_user(payload.userId)
    if not user:
        user = store.get_first_user()
    if not user:
        # Provision a minimal guest user to avoid hard failures in fresh environments.
        user = store.get_or_create_user("guest@intellex.local", "Guest User")

    project = store.create_project(payload.title, payload.goal, user)
    store.ensure_plan_for_project(project)
    return project

@router.get("/{project_id}", response_model=ResearchProject)
def get_project(project_id: str, store: DataStore = Depends(get_store)):
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

@router.patch("/{project_id}", response_model=ResearchProject)
def update_project(project_id: str, payload: UpdateProjectRequest, store: DataStore = Depends(get_store)):
    project = store.update_project(
        project_id,
        title=payload.title,
        goal=payload.goal,
        status=payload.status,
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, store: DataStore = Depends(get_store)):
    deleted = store.delete_project(project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    return None

@router.get("/{project_id}/plan", response_model=ResearchPlan)
def get_plan(project_id: str, store: DataStore = Depends(get_store)):
    plan = store.get_plan(project_id)
    if plan:
        return plan

    project = store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return store.ensure_plan_for_project(project)

@router.get("/{project_id}/messages", response_model=List[ChatMessage])
def get_messages(project_id: str, store: DataStore = Depends(get_store)):
    return store.get_messages(project_id)



@router.post("/{project_id}/messages", response_model=SendMessageResponse)
async def send_message(project_id: str, payload: CreateMessageRequest, store: DataStore = Depends(get_store)):
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

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

    # Use Orchestrator to generate response
    agent_content, thoughts = await orchestrator.process_message(project, payload.content)
    
    agent_message_id = f"msg-{uuid.uuid4().hex[:8]}"
    agent_timestamp = timestamp + 1500

    agent_msg = ChatMessage(
        id=agent_message_id,
        projectId=project.id,
        senderId="agent-researcher",
        senderType="agent",
        content=agent_content,
        thoughts=[AgentThought(**t) for t in thoughts],
        timestamp=agent_timestamp,
    )

    store.insert_message(agent_msg)
    store.update_project_timestamps(project.id, agent_timestamp, agent_timestamp)
    updated_plan = store.append_plan_item(project.id, payload.content)

    return SendMessageResponse(userMessage=user_msg, agentMessage=agent_msg, plan=updated_plan)
