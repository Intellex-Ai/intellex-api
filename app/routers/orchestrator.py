import os
from typing import Optional, List

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.models import AgentThought, ChatMessage
from app.queue import build_agent_message_id
from app.storage import DataStore, get_store, now_ms


router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


class OrchestratorCallback(BaseModel):
    jobId: str
    projectId: str
    response: str
    thoughts: List[AgentThought] = []
    agentMessageId: Optional[str] = None


@router.post("/callback", status_code=204)
def orchestrator_callback(
    payload: OrchestratorCallback,
    store: DataStore = Depends(get_store),
    x_orchestrator_secret: Optional[str] = Header(None, alias="x-orchestrator-secret"),
):
    """
    Receive job results from the orchestrator worker and upsert the agent message.
    If ORCHESTRATOR_CALLBACK_SECRET is set, require a matching x-orchestrator-secret header.
    """
    expected_secret = os.getenv("ORCHESTRATOR_CALLBACK_SECRET")
    if expected_secret and x_orchestrator_secret != expected_secret:
        raise HTTPException(status_code=401, detail="Invalid orchestrator secret")

    project = store.get_project(payload.projectId)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    timestamp = now_ms()
    agent_message_id = payload.agentMessageId or build_agent_message_id(payload.jobId)

    agent_msg = ChatMessage(
        id=agent_message_id,
        projectId=payload.projectId,
        senderId="agent-researcher",
        senderType="agent",
        content=payload.response,
        thoughts=payload.thoughts,
        timestamp=timestamp,
    )

    store.insert_message(agent_msg)
    store.update_project_timestamps(payload.projectId, timestamp, timestamp)
    return None

