from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings, get_settings

from app.providers import create_llm

from app.services.storage import LocalStorageService

from langchain_core.language_models.chat_models import BaseChatModel

SettingsDep = Annotated[Settings, Depends(get_settings)]

def get_request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)

def get_llm(settings: SettingsDep) -> BaseChatModel:
    return create_llm(settings)

def get_storage_service(settings: Settings) -> LocalStorageService:
    return LocalStorageService(settings)

RequestIdDep = Annotated[str | None, Depends(get_request_id)]
LlmDep = Annotated[BaseChatModel, Depends(get_llm)]
StorageDep = Annotated[LocalStorageService, Depends(get_storage_service)]
