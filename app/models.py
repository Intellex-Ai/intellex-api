from typing import List, Optional
from pydantic import BaseModel, Field

class Preferences(BaseModel):
    theme: str = "system"
    title: str | None = None
    organization: str | None = None
    location: str | None = None
    bio: str | None = None

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
    supabaseUserId: Optional[str] = Field(None, example="00000000-0000-0000-0000-000000000000")

class DeleteAccountRequest(BaseModel):
    userId: Optional[str] = Field(None, description="App user id / Supabase auth id")
    email: Optional[str] = Field(None, description="Email address for lookup")
    supabaseUserId: Optional[str] = Field(None, description="Supabase auth user id for auth deletion")

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
    userId: str = Field(..., min_length=1, description="Supabase auth/user id")

class UpdateProjectRequest(BaseModel):
    title: Optional[str] = None
    goal: Optional[str] = None
    status: Optional[str] = Field(None, description="draft | active | completed | archived")

class CreateMessageRequest(BaseModel):
    content: str

class SendMessageResponse(BaseModel):
    userMessage: ChatMessage
    agentMessage: ChatMessage
    plan: Optional[ResearchPlan] = None
