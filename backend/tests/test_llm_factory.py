from langchain_openai import ChatOpenAI

from app.core.config import Settings
from app.providers.llm import create_llm


def test_create_openai_llm() -> None:
    settings = Settings(
        llm_provider="openai",
        llm_model="cx/gpt-5.5",
        llm_temperature=0,
        openai_api_key="sk-4847ba7a3ca105c0-vb5blv-8a9ca649",
        openai_base_url="https://rfkg9dk.abc-tunnel.us/v1",
        _env_file=None,
    )

    llm = create_llm(settings)

    assert isinstance(llm, ChatOpenAI)