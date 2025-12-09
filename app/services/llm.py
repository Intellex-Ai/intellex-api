import os
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

LLM_DISABLED_MESSAGE = (
    "I'm not connected to the model right now. Please set OPENAI_API_KEY (and OPENAI_MODEL/OPENAI_TEMPERATURE as needed)."
)

class LLMService:
    def __init__(self):
        self.model = os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview")
        self.temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.7"))
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        self.provider = self._detect_provider()
        self.llm = self._build_client()

    def _detect_provider(self) -> str:
        if self.api_key and not self.api_key.lower().startswith("placeholder"):
            return "openai"
        if self.anthropic_key and not self.anthropic_key.lower().startswith("placeholder"):
            return "anthropic"
        return "disabled"

    def _build_client(self) -> Optional[ChatOpenAI]:
        """
        Lazily construct the LLM client only when a real API key is available.
        Avoids noisy errors in environments where the key is intentionally absent.
        """
        if self.provider != "openai":
            return None
        try:
            return ChatOpenAI(
                model=self.model,
                temperature=self.temperature,
                api_key=self.api_key,
            )
        except Exception as exc:  # pragma: no cover - defensive guard
            print(f"LLM init error: {exc}")
            return None

    async def generate_response(self, system_prompt: str, user_content: str) -> str:
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content)
        ]
        try:
            if not self.llm:
                return LLM_DISABLED_MESSAGE
            response = await self.llm.ainvoke(messages)
            return response.content
        except Exception as e:
            print(f"LLM Error: {e}")
            return "I'm having trouble connecting to my brain right now. Please check my API keys."

llm_service = LLMService()
