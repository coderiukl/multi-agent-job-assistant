import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.core.config import Settings
from app.core.exceptions import FileValidationException
from app.services.storage import LocalStorageService


@pytest.mark.asyncio
async def test_save_pdf_upload(tmp_path) -> None:
    settings = Settings(upload_dir=str(tmp_path), max_upload_size_mb=1)
    service = LocalStorageService(settings)

    file = UploadFile(
        filename="cv.pdf",
        file=None,
        headers=Headers({"content-type": "application/pdf"}),
    )
    file.file = __import__("io").BytesIO(b"%PDF-test")

    saved_path = await service.save_upload_file(file)

    assert saved_path.exists()
    assert saved_path.suffix == ".pdf"
    assert saved_path.read_bytes() == b"%PDF-test"


@pytest.mark.asyncio
async def test_reject_non_pdf(tmp_path) -> None:
    settings = Settings(upload_dir=str(tmp_path))
    service = LocalStorageService(settings)

    file = UploadFile(
        filename="cv.txt",
        file=None,
        headers=Headers({"content-type": "text/plain"}),
    )
    file.file = __import__("io").BytesIO(b"hello")

    with pytest.raises(FileValidationException):
        await service.save_upload_file(file)