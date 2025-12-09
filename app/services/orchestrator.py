import uuid
from dataclasses import dataclass
from typing import Tuple, Optional

from app.services.llm import llm_service, LLM_DISABLED_MESSAGE
from app.models import AgentThought, ResearchProject
from app.utils.time import now_ms


@dataclass
class OrchestratorContext:
    project: ResearchProject
    user_content: str
    preview: str
    base_ts: int


class AgentOrchestrator:
    def __init__(self):
        pass

    def _build_thought(self, title: str, content: str, base_timestamp: int, offset_ms: int = 0) -> AgentThought:
        return AgentThought(
            id=f"th-{uuid.uuid4().hex[:8]}",
            title=title,
            content=content,
            status="completed",
            timestamp=base_timestamp + offset_ms,
        )

    def _plan_thoughts(self, ctx: OrchestratorContext) -> list[AgentThought]:
        return [
            self._build_thought(
                "Analyzing Request",
                f"Analyzing user input: '{ctx.preview}' in context of project '{ctx.project.title}'",
                ctx.base_ts,
            ),
            self._build_thought(
                "Formulating Strategy",
                "Determining best research path and sources.",
                ctx.base_ts,
                500,
            ),
        ]

    def _llm_prompt(self, ctx: OrchestratorContext) -> str:
        return (
            f"You are an advanced AI Research Assistant working on a project titled '{ctx.project.title}'.\n"
            f"Project Goal: {ctx.project.goal}\n"
            "Your role is to help the user achieve this goal by providing detailed, accurate, and structured research.\n"
            "Maintain a professional, academic, yet accessible tone.\n"
            "If the user asks for a plan update, suggest specific steps."
        )

    async def _llm_response(self, ctx: OrchestratorContext) -> str:
        if llm_service.provider == "disabled":
            return LLM_DISABLED_MESSAGE
        return await llm_service.generate_response(self._llm_prompt(ctx), ctx.user_content)

    async def process_message(self, project: ResearchProject, user_content: str) -> Tuple[str, list[AgentThought]]:
        base_ts = now_ms()
        preview = f"{user_content[:50]}..." if len(user_content) > 50 else user_content
        ctx = OrchestratorContext(project=project, user_content=user_content, preview=preview, base_ts=base_ts)

        thoughts: list[AgentThought] = self._plan_thoughts(ctx)
        response_content = await self._llm_response(ctx)

        thoughts.append(
            self._build_thought(
                "Generating Response",
                "Synthesizing findings and formatting output.",
                base_ts,
                1000,
            )
        )

        return response_content, thoughts

orchestrator = AgentOrchestrator()
