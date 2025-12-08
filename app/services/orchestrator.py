import uuid
from typing import Tuple

from app.services.llm import llm_service
from app.models import AgentThought, ResearchProject
from app.utils.time import now_ms

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

    async def process_message(self, project: ResearchProject, user_content: str) -> Tuple[str, list[AgentThought]]:
        base_ts = now_ms()
        preview = f"{user_content[:50]}..." if len(user_content) > 50 else user_content

        thoughts: list[AgentThought] = [
            self._build_thought(
                "Analyzing Request",
                f"Analyzing user input: '{preview}' in context of project '{project.title}'",
                base_ts,
            ),
            self._build_thought(
                "Formulating Strategy",
                "Determining best research path and sources.",
                base_ts,
                500,
            ),
        ]

        # 2. Generate Response using LLM
        system_prompt = (
            f"You are an advanced AI Research Assistant working on a project titled '{project.title}'.\n"
            f"Project Goal: {project.goal}\n"
            "Your role is to help the user achieve this goal by providing detailed, accurate, and structured research.\n"
            "Maintain a professional, academic, yet accessible tone.\n"
            "If the user asks for a plan update, suggest specific steps."
        )

        response_content = await llm_service.generate_response(system_prompt, user_content)

        # Thought 3: Finalizing
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
