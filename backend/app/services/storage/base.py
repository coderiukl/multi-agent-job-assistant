from typing import Protocol

from fastapi import UploadFile

from app.services.storage.models import StoredFile

class StorageService(Protocol):
    async def save_cv(self, file: UploadFile) -> StoredFile:
        """Validate and store an uploaded CV."""
        ...