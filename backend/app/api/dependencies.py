from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.core.config import get_settings
from app.services.storage import LocalStorageService, StorageService


@lru_cache
def get_storage_service() -> StorageService:
    return LocalStorageService(get_settings())


StorageServiceDependency = Annotated[
    StorageService,
    Depends(get_storage_service),
]