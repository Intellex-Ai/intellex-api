import time
import uuid
from typing import List, Tuple
from app.services.llm import llm_service
from app.models import ResearchProject

def now_ms() -> int:
    return int(time.time() * 1000)

class AgentOrchestrator:
    def __init__(self):
        pass

    async def process_message(self, project: ResearchProject, user_content: str) -> Tuple[str, List[dict]]:
        # 1. Generate Thoughts
        thoughts = []
        
        # Thought 1: Analysis
        thoughts.append({
            "id": f"th-{uuid.uuid4().hex[:8]}",
            "title": "Analyzing Request",
            "content": f"Analyzing user input: '{user_content[:50]}...' in context of project '{project.title}'",
            "status": "completed",
            "timestamp": now_ms()
        })

        # Thought 2: Planning (Mock for now, could be LLM generated)
        thoughts.append({
            "id": f"th-{uuid.uuid4().hex[:8]}",
            "title": "Formulating Strategy",
            "content": "Determining best research path and sources.",
            "status": "completed",
            "timestamp": now_ms() + 500
        })

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
        thoughts.append({
            "id": f"th-{uuid.uuid4().hex[:8]}",
            "title": "Generating Response",
            "content": "Synthesizing findings and formatting output.",
            "status": "completed",
            "timestamp": now_ms() + 1000
        })

        return response_content, thoughts

orchestrator = AgentOrchestrator()
