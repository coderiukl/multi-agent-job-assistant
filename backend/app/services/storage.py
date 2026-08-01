from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import Settings
from app.core.exceptions import FileValidationException

class LocalStorageService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.upload_dir = Path(settings.upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    async def save_upload_file(self, file: UploadFile) -> Path:
        self._validate_content_type(file)

        content = await file.read()
        self._validate_size(content)

        suffix = Path(file.filename or "").suffix.lower()
        filename = f"{uuid4().hex}{suffix}"
        destination = self.upload_dir / filename

        destination.write_bytes(content)

        return destination

    def _validate_content_type(self, file: UploadFile) -> None:
        if file.content_type not in self.settings.allowed_cv_content_types:
            raise FileValidationException(
                message="File không hợp lệ. Chỉ hỗ trợ PDF.",
                details={
                    "content_type": file.content_type,
                    "allowed_content_types": self.settings.allowed_cv_content_types
                },
            )

    def _validate_size(self, content: bytes) -> None:
        max_size_bytes = self.settings.max_upload_size_mb * 1024 * 1024

        if len(content) > max_size_bytes:
            raise FileValidationException(
                message=f"File vượt quá dung lượng tối đa {self.settings.max_upload_size_mb}MB.",
                details={
                    "max_size_mb": self.settings.max_upload_size_mb,
                    "actual_size_mb": len(content),
                },
            )

        
