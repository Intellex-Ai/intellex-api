import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

class LLMService:
    def __init__(self):
        # We will assume OpenAI for now as per user preference
        # API Key should be in env var OPENAI_API_KEY
        self.llm = ChatOpenAI(
            model="gpt-4-turbo-preview",
            temperature=0.7,
            api_key=os.getenv("OPENAI_API_KEY", "sk-placeholder") # Placeholder to prevent crash on init if missing
        )

    async def generate_response(self, system_prompt: str, user_content: str) -> str:
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content)
        ]
        try:
            response = await self.llm.ainvoke(messages)
            return response.content
        except Exception as e:
            print(f"LLM Error: {e}")
            return "I'm having trouble connecting to my brain right now. Please check my API keys."

llm_service = LLMService()
