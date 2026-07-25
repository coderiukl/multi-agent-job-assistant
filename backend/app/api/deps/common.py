from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings, get_settings


SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


RequestIdDep = Annotated[str | None, Depends(get_request_id)]