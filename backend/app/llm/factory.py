from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.core.config import Settings
from app.core.exceptions import LLMConfigurationException

class LLMFactory:
    @staticmethod
    def create_chat_model(settings: Settings) -> BaseChatModel:
        if settings.llm_provider == "openai":
            api_key = settings.openai_api_key
            base_url = settings.openai_base_url

        elif settings.llm_provider == "9router":
            api_key = settings.nine_router_api_key
            base_url =  settings.nine_router_base_url

        else:
            raise LLMConfigurationException(
                message=(
                    f"Unsupported LLM provider: "
                    f"{settings.llm_provider}"
                ),
            )

        if not api_key:
            raise LLMConfigurationException(
                message=(
                    f"API key is missing for provider "
                    f"{settings.llm_provider}."
                ),
            )

        if settings.llm_provider == "9router" and not base_url:
            raise LLMConfigurationException(message="9router base url is missing.")

        return ChatOpenAI(
            model=settings.llm_model,
            api_key=api_key,
            base_url=base_url,
            temperature=0,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )