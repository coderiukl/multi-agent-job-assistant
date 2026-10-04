from io import BytesIO

import pymupdf
import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.core.exceptions import FileValidationException
from app.services.pdf.inspector import PdfInspector
from app.services.pdf.text_extractor import NativePdfTextExtractor
from app.services.storage.local import LocalStorageService


def upload(content, name="cv.pdf", mime="application/pdf"):
    return UploadFile(file=BytesIO(content), filename=name, headers=Headers({"content-type": mime}))


@pytest.mark.parametrize("content,name,mime,code", [
    (b"", "cv.pdf", "application/pdf", "EMPTY_FILE"),
    (b"fake", "cv.pdf", "application/pdf", "INVALID_PDF_SIGNATURE"),
    (b"%PDF-fake", "cv.txt", "application/pdf", "INVALID_FILE_EXTENSION"),
    (b"%PDF-fake", "cv.pdf", "text/plain", "UNSUPPORTED_MEDIA_TYPE"),
])
async def test_bad_upload_leaves_no_files(settings, content, name, mime, code):
    storage = LocalStorageService(settings)
    with pytest.raises(FileValidationException) as exc:
        await storage.save(upload(content, name, mime))
    assert exc.value.code == code
    assert list(settings.upload_dir.iterdir()) == []


async def test_oversized_upload_cleans_partial_file(settings):
    settings.max_upload_size_mb = 1
    storage = LocalStorageService(settings)
    with pytest.raises(FileValidationException) as exc:
        await storage.save(upload(b"%PDF-" + b"x" * (1024 * 1024)))
    assert exc.value.status_code == 413
    assert list(settings.upload_dir.iterdir()) == []


async def test_native_pdf_roundtrip_and_delete(settings):
    with pymupdf.open() as document:
        document.new_page().insert_text((72, 72), "Python SQL developer with several portfolio projects and APIs")
        content = document.tobytes()
    storage = LocalStorageService(settings)
    stored = await storage.save(upload(content, "../../cv.pdf"))
    assert stored.path.parent == settings.upload_dir
    assert stored.original_filename == "cv.pdf"
    assert (await PdfInspector(settings).inspect(stored.path)).page_count == 1
    extraction = await NativePdfTextExtractor(settings).extract(stored.path)
    assert "Python" in extraction.full_text
    assert extraction.ocr_required_page_numbers == ()
    await storage.delete(stored)
    assert not stored.path.exists()


def test_native_text_normalizes_whitespace():
    assert NativePdfTextExtractor._normalize_text("Python\t  SQL\r\n developer") == "Python SQL\ndeveloper"


@pytest.mark.parametrize("kind", ["encrypted", "too_many_pages", "corrupt"])
async def test_inspector_rejects_invalid_pdf(settings, tmp_path, kind):
    path = tmp_path / "invalid.pdf"
    if kind == "corrupt":
        path.write_bytes(b"%PDF-broken")
    else:
        with pymupdf.open() as document:
            for _ in range(settings.max_pdf_pages + 1 if kind == "too_many_pages" else 1):
                document.new_page()
            kwargs = {"encryption": pymupdf.PDF_ENCRYPT_AES_256, "owner_pw": "owner", "user_pw": "password"} if kind == "encrypted" else {}
            document.save(path, **kwargs)
    with pytest.raises(FileValidationException):
        await PdfInspector(settings).inspect(path)
