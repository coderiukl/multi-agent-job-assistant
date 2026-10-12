from typing import Protocol

from fastapi import UploadFile

from app.services.storage.models import StoredFile


class StorageService(Protocol):
    async def save(self, file: UploadFile) -> StoredFile:
        """Validate and store an uploaded PDF or image CV."""
        ...

    async def save_many(self, files: list[UploadFile]) -> StoredFile:
        """Validate and store one PDF or an ordered collection of CV images."""
        ...

    async def delete(self, stored_file: StoredFile) -> None:
        """Delete a stored file."""
        ...

    async def delete_by_id(self, file_id: str) -> None:
        """Delete a stored CV when only its identifier is available."""
        ...
