from typing import Protocol

from fastapi import UploadFile

from app.services.storage.models import StoredFile


class StorageService(Protocol):
    async def save(self, file: UploadFile) -> StoredFile:
        """Validate and store an uploaded CV."""
        ...

    async def delete(self, stored_file: StoredFile) -> None:
        """Delete a stored file."""
        ...

    async def delete_by_id(self, file_id: str) -> None:
        """Delete a stored CV when only its identifier is available."""
        ...
