import asyncio
import logging
import os
import re
from pathlib import Path
from uuid import uuid4

import aiofiles
import pymupdf
from fastapi import UploadFile

from app.core.config import Settings
from app.core.exceptions import (
    FileValidationException,
    StorageException,
)
from app.services.storage.models import StoredFile

logger = logging.getLogger(__name__)

PDF_SUFFIX = ".pdf"
CONTENT_TYPE_EXTENSIONS = {
    "application/pdf": {".pdf"},
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
}
FILE_SIGNATURES = {
    "application/pdf": (b"%PDF-",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
}
CV_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class LocalStorageService:
    def __init__(self, settings: Settings) -> None:
        self._upload_dir = settings.upload_dir
        self._max_size_bytes = settings.max_upload_size_bytes
        self._max_cv_images = settings.max_cv_images
        self._max_total_size_bytes = settings.max_cv_total_upload_size_bytes
        self._chunk_size = settings.upload_chunk_size_bytes
        self._allowed_content_types = {
            content_type.lower() for content_type in settings.allowed_cv_content_types
        }

        self._upload_dir.mkdir(parents=True, exist_ok=True)

    async def save(self, file: UploadFile) -> StoredFile:
        original_filename = self._normalize_filename(file.filename)
        content_type = (file.content_type or "application/octet-stream").lower()

        self._validate_metadata(
            filename=original_filename,
            content_type=content_type,
        )

        file_id = uuid4().hex
        stored_filename = f"{file_id}{PDF_SUFFIX}"

        destination = self._upload_dir / stored_filename
        source_path = self._upload_dir / f".{file_id}.source.part"
        converted_path = self._upload_dir / f".{stored_filename}.part"

        size_bytes = 0
        signature_bytes = b""

        try:
            async with aiofiles.open(source_path, mode="wb") as output:
                while chunk := await file.read(self._chunk_size):
                    if len(signature_bytes) < 8:
                        signature_bytes += chunk[: 8 - len(signature_bytes)]
                    size_bytes += len(chunk)

                    if size_bytes > self._max_size_bytes:
                        raise FileValidationException(
                            message=(
                                "The uploaded file exceeds the maximum allowed size."
                            ),
                            status_code=413,
                            code="FILE_TOO_LARGE",
                            details={
                                "max_size_bytes": (self._max_size_bytes),
                            },
                        )

                    await output.write(chunk)

            if size_bytes == 0:
                raise FileValidationException(
                    message="The uploaded file is empty.",
                    code="EMPTY_FILE",
                )

            self._validate_signature(
                chunk=signature_bytes,
                content_type=content_type,
            )

            if content_type == "application/pdf":
                await asyncio.to_thread(os.replace, source_path, destination)
            else:
                await asyncio.to_thread(
                    self._convert_image_to_pdf,
                    source_path,
                    converted_path,
                )
                await asyncio.to_thread(os.replace, converted_path, destination)

        except FileValidationException:
            raise

        except OSError as exc:
            logger.exception("Failed to store uploaded CV", extra={"file_id": file_id})

            raise StorageException() from exc

        finally:
            await self._remove_partial_file(source_path)
            await self._remove_partial_file(converted_path)

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

    async def save_many(self, files: list[UploadFile]) -> StoredFile:
        if not files:
            raise FileValidationException(
                message="At least one CV file is required.",
                code="MISSING_CV_FILE",
            )

        if len(files) == 1:
            return await self.save(files[0])

        if len(files) > self._max_cv_images:
            raise FileValidationException(
                message=(
                    f"A CV can contain at most {self._max_cv_images} images."
                ),
                code="CV_IMAGE_LIMIT_EXCEEDED",
                details={"max_cv_images": self._max_cv_images},
            )

        metadata: list[tuple[str, str]] = []
        for file in files:
            original_filename = self._normalize_filename(file.filename)
            content_type = (file.content_type or "application/octet-stream").lower()
            self._validate_metadata(
                filename=original_filename,
                content_type=content_type,
            )
            if content_type == "application/pdf":
                raise FileValidationException(
                    message=(
                        "Upload one PDF or up to five images; PDF and image "
                        "files cannot be combined."
                    ),
                    code="INVALID_CV_FILE_COMBINATION",
                )
            metadata.append((original_filename, content_type))

        file_id = uuid4().hex
        destination = self._upload_dir / f"{file_id}{PDF_SUFFIX}"
        converted_path = self._upload_dir / f".{file_id}.pdf.part"
        source_paths = [
            self._upload_dir / f".{file_id}.{index}.source.part"
            for index in range(len(files))
        ]
        total_size_bytes = 0

        try:
            for file, source_path, (_, content_type) in zip(
                files,
                source_paths,
                metadata,
                strict=True,
            ):
                size_bytes, signature_bytes = await self._write_upload(
                    file=file,
                    destination=source_path,
                )
                total_size_bytes += size_bytes
                if total_size_bytes > self._max_total_size_bytes:
                    raise FileValidationException(
                        message=(
                            "The combined CV images exceed the maximum "
                            "allowed size."
                        ),
                        status_code=413,
                        code="CV_TOTAL_SIZE_EXCEEDED",
                        details={
                            "max_total_size_bytes": self._max_total_size_bytes,
                        },
                    )
                self._validate_signature(
                    chunk=signature_bytes,
                    content_type=content_type,
                )

            await asyncio.to_thread(
                self._convert_images_to_pdf,
                source_paths,
                converted_path,
            )
            await asyncio.to_thread(os.replace, converted_path, destination)

        except FileValidationException:
            raise
        except OSError as exc:
            logger.exception(
                "Failed to store multi-image CV",
                extra={"file_id": file_id},
            )
            raise StorageException() from exc
        finally:
            for source_path in source_paths:
                await self._remove_partial_file(source_path)
            await self._remove_partial_file(converted_path)

        logger.info(
            "Multi-image CV stored successfully",
            extra={
                "file_id": file_id,
                "image_count": len(files),
                "size_bytes": total_size_bytes,
            },
        )
        return StoredFile(
            file_id=file_id,
            path=destination,
            original_filename=f"cv-{len(files)}-pages.pdf",
            content_type="application/pdf",
            size_bytes=total_size_bytes,
        )

    async def _write_upload(
        self,
        *,
        file: UploadFile,
        destination: Path,
    ) -> tuple[int, bytes]:
        size_bytes = 0
        signature_bytes = b""
        async with aiofiles.open(destination, mode="wb") as output:
            while chunk := await file.read(self._chunk_size):
                if len(signature_bytes) < 8:
                    signature_bytes += chunk[: 8 - len(signature_bytes)]
                size_bytes += len(chunk)
                if size_bytes > self._max_size_bytes:
                    raise FileValidationException(
                        message=(
                            "An uploaded CV image exceeds the maximum "
                            "allowed size."
                        ),
                        status_code=413,
                        code="FILE_TOO_LARGE",
                        details={"max_size_bytes": self._max_size_bytes},
                    )
                await output.write(chunk)

        if size_bytes == 0:
            raise FileValidationException(
                message="An uploaded CV image is empty.",
                code="EMPTY_FILE",
            )
        return size_bytes, signature_bytes

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

    async def delete_by_id(self, file_id: str) -> None:
        if not CV_ID_PATTERN.fullmatch(file_id):
            return

        try:
            await asyncio.to_thread(
                (self._upload_dir / f"{file_id}{PDF_SUFFIX}").unlink,
                missing_ok=True,
            )
        except OSError as exc:
            logger.exception(
                "Failed to delete stored file",
                extra={"file_id": file_id},
            )
            raise StorageException(
                message="The stored file could not be deleted.",
            ) from exc

    def _validate_metadata(self, *, filename: str, content_type: str) -> None:
        if content_type not in self._allowed_content_types:
            raise FileValidationException(
                message="Only PDF, PNG, and JPEG CV files are supported.",
                status_code=415,
                code="UNSUPPORTED_MEDIA_TYPE",
                details={
                    "allowed_content_types": sorted(
                        self._allowed_content_types,
                    ),
                },
            )

        suffix = Path(filename).suffix.lower()
        allowed_extensions = CONTENT_TYPE_EXTENSIONS.get(content_type, set())
        if suffix not in allowed_extensions:
            raise FileValidationException(
                message="The filename extension does not match the uploaded file type.",
                code="INVALID_FILE_EXTENSION",
                details={"allowed_extensions": sorted(allowed_extensions)},
            )

    @staticmethod
    def _validate_signature(*, chunk: bytes, content_type: str) -> None:
        signatures = FILE_SIGNATURES.get(content_type, ())
        if not signatures or not any(chunk.startswith(value) for value in signatures):
            raise FileValidationException(
                message="The uploaded CV does not match its declared file type.",
                code="INVALID_FILE_SIGNATURE",
            )

    @staticmethod
    def _convert_image_to_pdf(source_path: Path, destination_path: Path) -> None:
        try:
            with pymupdf.open(str(source_path)) as image_document:
                if image_document.page_count != 1:
                    raise FileValidationException(
                        message="The uploaded CV image must contain exactly one image.",
                        code="INVALID_CV_IMAGE",
                    )
                pdf_bytes = image_document.convert_to_pdf()
        except FileValidationException:
            raise
        except (RuntimeError, ValueError, pymupdf.FileDataError) as exc:
            raise FileValidationException(
                message="The uploaded CV image is invalid or corrupted.",
                code="INVALID_CV_IMAGE",
            ) from exc

        if not pdf_bytes.startswith(b"%PDF-"):
            raise FileValidationException(
                message="The uploaded CV image could not be converted.",
                code="INVALID_CV_IMAGE",
            )

        destination_path.write_bytes(pdf_bytes)

    @staticmethod
    def _convert_images_to_pdf(
        source_paths: list[Path],
        destination_path: Path,
    ) -> None:
        try:
            with pymupdf.open() as output_document:
                for source_path in source_paths:
                    with pymupdf.open(str(source_path)) as image_document:
                        if image_document.page_count != 1:
                            raise FileValidationException(
                                message=(
                                    "Each uploaded CV image must contain "
                                    "exactly one image."
                                ),
                                code="INVALID_CV_IMAGE",
                            )
                        pdf_bytes = image_document.convert_to_pdf()
                    with pymupdf.open("pdf", pdf_bytes) as page_document:
                        output_document.insert_pdf(page_document)

                if output_document.page_count != len(source_paths):
                    raise FileValidationException(
                        message="The CV images could not be combined.",
                        code="INVALID_CV_IMAGE",
                    )
                output_document.save(destination_path)
        except FileValidationException:
            raise
        except (RuntimeError, ValueError, pymupdf.FileDataError) as exc:
            raise FileValidationException(
                message="An uploaded CV image is invalid or corrupted.",
                code="INVALID_CV_IMAGE",
            ) from exc

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
