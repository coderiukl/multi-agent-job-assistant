from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.core.config import Settings

def create_llm(settings: Settings) -> BaseChatModel:
    common_kwargs = {
        "model": settings.llm_model,
        "temperature": settings.llm_temperature,
    }

    if settings.llm_max_tokens is not None:
        common_kwargs["max_tokens"] = settings.llm_max_tokens

    if settings.llm_provider == "openai":
        return ChatOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            **common_kwargs,
        )

    raise ValueError(f"Unsuported LLM provider: {settings.llm_provider}")