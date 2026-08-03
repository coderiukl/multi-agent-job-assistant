from pathlib import Path

import fitz
from pydantic import BaseModel, Field

from app.core.config import Settings
from app.core.exceptions import FileValidationException
from app.services.cv_processing.file_hasher import FileHasher


class FileValidationResult(BaseModel):
    filename: str
    content_type: str | None = None
    size_bytes: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)
    page_count: int = Field(ge=1)
    is_valid: bool = True


class CVFileValidator:
    """Validate uploaded CV PDF files before processing."""

    def __init__(self, settings: Settings, hasher: FileHasher) -> None:
        self.settings = settings
        self.hasher = hasher

    def validate_bytes(
        self,
        *,
        content: bytes,
        filename: str,
        content_type: str | None = None,
    ) -> FileValidationResult:
        safe_filename = self._validate_filename(filename)

        self._validate_extension(safe_filename)
        self._validate_content_type(content_type)
        self._validate_size(content)
        self._validate_magic_bytes(content)

        sha256 = self.hasher.sha256_bytes(content)
        page_count = self._read_pdf_page_count(content)

        return FileValidationResult(
            filename=safe_filename,
            content_type=content_type,
            size_bytes=len(content),
            sha256=sha256,
            page_count=page_count,
        )

    def _validate_filename(self, filename: str) -> str:
        name = Path(filename or "").name

        if not name:
            raise FileValidationException(message="Filename is required.")

        if name in {".", ".."}:
            raise FileValidationException(message="Filename is invalid.")

        return name

    def _validate_extension(self, filename: str) -> None:
        suffix = Path(filename).suffix.lower()

        if suffix not in self.settings.allowed_cv_extensions:
            raise FileValidationException(
                message="File extension is not supported.",
                details={
                    "extension": suffix,
                    "allowed_extensions": self.settings.allowed_cv_extensions,
                },
            )

    def _validate_content_type(self, content_type: str | None) -> None:
        if content_type is None:
            return

        if content_type not in self.settings.allowed_cv_content_types:
            raise FileValidationException(
                message="File content type is not supported.",
                details={
                    "content_type": content_type,
                    "allowed_content_types": self.settings.allowed_cv_content_types,
                },
            )

    def _validate_size(self, content: bytes) -> None:
        max_size_bytes = self.settings.max_upload_size_mb * 1024 * 1024

        if not content:
            raise FileValidationException(message="File is empty.")

        if len(content) > max_size_bytes:
            raise FileValidationException(
                message="File exceeds maximum allowed size.",
                details={
                    "max_size_mb": self.settings.max_upload_size_mb,
                    "actual_size_bytes": len(content),
                },
            )

    def _validate_magic_bytes(self, content: bytes) -> None:
        if not content.startswith(b"%PDF"):
            raise FileValidationException(message="File is not a valid PDF.")

    def _read_pdf_page_count(self, content: bytes) -> int:
        try:
            document = fitz.open(stream=content, filetype="pdf")
        except fitz.FileDataError as exc:
            raise FileValidationException(message="PDF cannot be opened.") from exc

        try:
            if document.is_encrypted:
                raise FileValidationException(
                    message="Encrypted PDF is not supported.",
                )

            if document.page_count <= 0:
                raise FileValidationException(message="PDF has no pages.")

            if document.page_count > self.settings.max_pdf_pages:
                raise FileValidationException(
                    message="PDF exceeds maximum page limit.",
                    details={
                        "page_count": document.page_count,
                        "max_pdf_pages": self.settings.max_pdf_pages,
                    },
                )

            return document.page_count
        finally:
            document.close()