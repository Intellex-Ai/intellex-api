import json
import os
import uuid
from typing import Optional

from redis.asyncio import Redis

from app.models import ResearchProject


REDIS_URL = os.getenv("REDIS_URL")
QUEUE_KEY = os.getenv("ORCHESTRATOR_QUEUE_KEY", "intellex:message_jobs")

_redis_client: Optional[Redis] = None


def get_redis() -> Optional[Redis]:
    global _redis_client
    if not REDIS_URL:
        return None
    if _redis_client is None:
        _redis_client = Redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


def build_job_id() -> str:
    return f"job-{uuid.uuid4().hex[:10]}"


def build_agent_message_id(job_id: str) -> str:
    return f"msg-agent-{job_id}"


async def enqueue_message(project: ResearchProject, user_content: str, callback_path: str) -> tuple[str, str]:
    """
    Enqueue a message processing job into Redis.
    Returns (job_id, agent_message_id).
    """
    redis = get_redis()
    if not redis:
        raise RuntimeError("Redis is not configured")

    job_id = build_job_id()
    agent_message_id = build_agent_message_id(job_id)
    payload = {
        "jobId": job_id,
        "project": project.model_dump(),
        "userContent": user_content,
        "callbackPath": callback_path,
        "agentMessageId": agent_message_id,
    }

    await redis.rpush(QUEUE_KEY, json.dumps(payload))
    return job_id, agent_message_id

