from typing import List, Optional, Literal
from pydantic import BaseModel, Field, ConfigDict

class Preferences(BaseModel):
    model_config = ConfigDict(extra="allow")
    theme: str = "system"
    title: str | None = None
    organization: str | None = None
    location: str | None = None
    bio: str | None = None
    apiKeys: dict[str, dict] | None = None

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


class ProjectStats(BaseModel):
    totalProjects: int
    activeProjects: int
    completedProjects: int
    updatedLastDay: int


class ActivityItem(BaseModel):
    id: str
    type: str
    description: str
    timestamp: int
    meta: Optional[str] = None


class ApiKeyRecord(BaseModel):
    last4: str
    storedAt: int


class ApiKeyPayload(BaseModel):
    openai: Optional[str] = Field(None, description="OpenAI API key")
    anthropic: Optional[str] = Field(None, description="Anthropic API key")


class ApiKeySummary(BaseModel):
    provider: str
    last4: str
    storedAt: int


class ApiKeysResponse(BaseModel):
    keys: list[ApiKeySummary]


class ShareProjectRequest(BaseModel):
    email: str = Field(..., description="Email to share the project with")
    access: str = Field("viewer", description="viewer | editor")


class ProjectShare(BaseModel):
    id: str
    projectId: str
    email: str
    access: str
    invitedAt: int


class DeviceUpsertRequest(BaseModel):
    deviceId: str = Field(..., min_length=6, max_length=160, description="Client-generated stable device identifier")
    userAgent: Optional[str] = None
    platform: Optional[str] = None
    browser: Optional[str] = None
    os: Optional[str] = None
    timezone: Optional[str] = None
    locale: Optional[str] = None
    screen: Optional[str] = Field(None, description="Viewport or screen size summary")
    deviceMemory: Optional[float] = None
    city: Optional[str] = None
    region: Optional[str] = None
    ip: Optional[str] = Field(None, description="Client-reported IP if available; server IP is authoritative")
    label: Optional[str] = None
    isTrusted: Optional[bool] = None
    login: bool = Field(False, description="Whether this event is a login (updates last_login_at)")
    refreshToken: Optional[str] = Field(None, description="Supabase refresh token to allow remote sign-out")


class DeviceRecord(BaseModel):
    id: str
    userId: str
    deviceId: str
    userAgent: Optional[str] = None
    platform: Optional[str] = None
    browser: Optional[str] = None
    os: Optional[str] = None
    timezone: Optional[str] = None
    locale: Optional[str] = None
    screen: Optional[str] = None
    deviceMemory: Optional[float] = None
    city: Optional[str] = None
    region: Optional[str] = None
    ip: Optional[str] = None
    label: Optional[str] = None
    isTrusted: bool = False
    firstSeenAt: int
    lastSeenAt: int
    lastLoginAt: Optional[int] = None
    revokedAt: Optional[int] = None


class DeviceListResponse(BaseModel):
    devices: list[DeviceRecord]


class DeviceRevokeRequest(BaseModel):
    scope: Literal["single", "others", "all"] = Field("single", description="Revoke a specific device, all except the caller, or all devices")
    deviceId: Optional[str] = Field(None, description="Target device id. Required for scope=single or scope=others")


class DeviceRevokeResponse(BaseModel):
    revoked: int = Field(..., description="Number of device records marked revoked")
    tokensRevoked: int = Field(..., description="Number of refresh tokens invalidated via auth admin")

Preferences.model_rebuild()
