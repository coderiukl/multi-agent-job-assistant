import asyncio
import logging
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import Settings
from app.core.exceptions import FileValidationException

logger = logging.getLogger(__name__)

class LocalStorageService:
    """Lưu trữ và kiểm tra file tải lên trên local filesystem."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.upload_dir = Path(settings.upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    async def save_upload_file(self, file: UploadFile) -> Path:
        """Kiểm tra và lưu file upload vào local storage."""
        self._validate_content_type(file)
        self._validate_extension(file)

        try: 
            content = await file.read()
            self._validate_size(content)

            suffix = Path(file.filename or "").suffix.lower()
            filename = f"{uuid4().hex}{suffix}"
            destination = self.upload_dir / filename

            await asyncio.to_thread(destination.write_bytes, content)

            logger.info(
                "Upload file saved successfully",
                extra={
                    "original_filename": file.filename,
                    "stored_filename": filename,
                    "size_bytes": len(content),
                },
            )

            return destination

        except FileValidationException:
            raise

        except OSError as exc:
            logger.exception(
                "Failed to save uploaded file",
                extra={"filename": file.filename},
            )
            raise FileValidationException(
                message="Không thể lưu file tải lên.",
                details={"filename": file.filename},
            ) from exc

        finally:
            await file.close()

    def _validate_content_type(self, file: UploadFile) -> None:
        if file.content_type not in self.settings.allowed_cv_content_types:
            raise FileValidationException(
                message="File không hợp lệ. Chỉ hỗ trợ PDF.",
                details={
                    "content_type": file.content_type,
                    "allowed_content_types": self.settings.allowed_cv_content_types
                },
            )

    def _validate_extension(self, file: UploadFile) -> None:
        suffix = Path(file.filename or "").suffix.lower()

        if suffix != ".pdf":
            raise FileValidationException(
                message="Phần mở rộng file không hợp lệ. Chỉ hỗ trợ .pdf.",
                details={
                    "filename": file.filename,
                    "extension": suffix or None,
                    "allowed_extensions": [".pdf"],
                },
            )

    def _validate_size(self, content: bytes) -> None:
        if not content:
            raise FileValidationException(
                message="File tải lên không được rỗng.",
                details={"size_bytes": 0},
            )

        
        max_size_bytes = self.settings.max_upload_size_mb * 1024 * 1024
        actual_size_mb = len(content) / (1024 * 1024)

        if len(content) > max_size_bytes:
            raise FileValidationException(
                message=(
                    "File vượt quá dung lượng tối đa "
                    f"{self.settings.max_upload_size_mb}MB."
                ),
                details={
                    "max_size_mb": self.settings.max_upload_size_mb,
                    "actual_size_mb": round(actual_size_mb, 2),
                    "actual_size_bytes": len(content),
                },
            )

        
