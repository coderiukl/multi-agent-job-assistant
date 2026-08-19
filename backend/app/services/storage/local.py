import asyncio
import logging
import os
from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import UploadFile

from app.core.config import Settings
from app.core.exceptions import (
    FileValidationException,
    StorageException,
)
from app.services.storage.models import StoredFile

logger = logging.getLogger(__name__)

PDF_SIGNATURE = b"%PDF-"
PDF_SUFFIX = ".pdf"

class LocalStorageService:
    def __init__(self, settings: Settings) -> None:
        self._upload_dir = settings.upload_dir
        self._max_size_bytes = settings.max_upload_size_bytes
        self._chunk_size = settings.upload_chunk_size_bytes
        self._allowed_content_types = {
            content_type.lower()
            for content_type in settings.allowed_cv_content_types
        }

        self._upload_dir.mkdir(parents=True, exist_ok=True)

    async def save_cv(self, file: UploadFile) -> StoredFile:
        original_filename = self._normalize_filename(file.filename)
        content_type = (file.content_type or "application/octet-stream").lower()

        self._validate_metadata(
            filename=original_filename,
            content_type=content_type,
        )

        file_id = uuid4().hex
        stored_filename = f"{file_id}{PDF_SUFFIX}"

        destination = self._upload_dir / stored_filename
        temporary_path = self._upload_dir / f".{stored_filename}.part"

        size_bytes = 0
        is_first_chunk = True

        try:
            async with aiofiles.open(temporary_path, mode="wb") as output:
                while chunk := await file.read(self._chunk_size):
                    if is_first_chunk and not chunk.startswith(PDF_SIGNATURE):
                        raise FileValidationException(
                            message=(
                                "The uploaded file is not a valid "
                                "PDF document."
                            ),
                            code="INVALID_PDF_SIGNATURE",
                        )

                    is_first_chunk = False
                    size_bytes += len(chunk)

                    if size_bytes > self._max_size_bytes:
                        raise FileValidationException(
                            message=(
                                "The uploaded file exceeds the "
                                "maximum allowed size."
                            ),
                            status_code=413,
                            code="FILE_TOO_LARGE",
                            details={
                                "max_size_bytes": (
                                    self._max_size_bytes
                                ),
                            },
                        )

                    await output.write(chunk)

            if size_bytes == 0:
                raise FileValidationException(
                    message="The uploaded file is empty.",
                    code="EMPTY_FILE",
                )

            await asyncio.to_thread(os.replace, temporary_path, destination)

        except FileValidationException:
            raise

        except OSError as exc:
            logger.exception(
                "Failed to store uploaded CV",
                extra={"file_id": file_id}
            )

            raise StorageException() from exc

        finally:
            await self._remove_partial_file(temporary_path)

        logger.info(
            "CV stored successfully",
            extra={
                "file_id": file_id,
                "size_bytes": size_bytes,
            },
        )

        return StoredFile(
            file_id=file_id,
            path=destination,
            original_filename=original_filename,
            content_type=content_type,
            size_bytes=size_bytes,
        )

    async def delete(self, stored_file: StoredFile) -> None:
        try:
            await asyncio.to_thread(
                stored_file.path.unlink,
                missing_ok=True,
            )

            logger.info(
                "Stored file deleted",
                extra={"file_id": stored_file.file_id},
            )

        except OSError as exc:
            logger.exception(
                "Failed to delete stored file",
                extra={"file_id": stored_file.file_id},
            )

            raise StorageException(
                message="The stored file could not be deleted.",
            ) from exc
    def _validate_metadata(self, *, filename: str, content_type: str) -> None:
        if content_type not in self._allowed_content_types:
            raise FileValidationException(
                message="Only PDF files are supported.",
                status_code=415,
                code="UNSUPPORTED_MEDIA_TYPE",
                details={
                    "allowed_content_types": sorted(
                        self._allowed_content_types,
                    ),
                },
            )

        if Path(filename).suffix.lower() != PDF_SUFFIX:
            raise FileValidationException(
                message="The uploaded file must use a .pdf extension.",
                code="INVALID_FILE_EXTENSION",
                details={"allowed_extensions": [PDF_SUFFIX]},
            )

    @staticmethod
    def _normalize_filename(filename: str | None) -> str:
        if not filename:
            raise FileValidationException(
                message="The uploaded file must have a filename.",
                code="MISSING_FILENAME",
            )

        normalized_filename = Path(filename.replace("\\", "/")).name

        if not normalized_filename:
            raise FileValidationException(
                message="The uploaded filename is invalid.",
                code="INVALID_FILENAME",
            )

        return normalized_filename

    @staticmethod
    async def _remove_partial_file(path: Path) -> None:
        try:
            await asyncio.to_thread(
                path.unlink,
                missing_ok=True,
            )
        except OSError:
            logger.warning(
                "Could not remove partial upload",
                extra={"temporary_file": path.name},
                exc_info=True,
            )