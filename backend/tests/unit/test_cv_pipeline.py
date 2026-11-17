"""CV upload / PDF / OCR-merge / parsing tests (Phase 2A) using real files
generated on the fly with PyMuPDF and Pillow. No LLM or OCR model is called:
the parser agent and OCR extractor are fakes where they would be needed."""

from __future__ import annotations

import io
from pathlib import Path

import pymupdf
import pytest
from PIL import Image
from starlette.datastructures import Headers, UploadFile

from app.core.config import Settings
from app.core.exceptions import FileValidationException
from app.schemas.cv_profile import CVFieldProvenance
from app.services.cv_ingestion import CVIngestionService
from app.services.cv_processing import CVProcessingService
from app.services.pdf import NativePdfTextExtractor, PdfInspector, PdfTextMerger
from app.services.pdf.models import OcrTextExtractionResult
from app.services.storage import LocalStorageService
from tests.conftest import FakeCVRepository, make_cv_profile

VI_FONT = Path("C:/Windows/Fonts/arial.ttf")
VI_TEXT = "Kỹ năng: Python, FastAPI. Kinh nghiệm 2 năm tại Công ty Đại Việt."
EN_TEXT = "Backend developer with PostgreSQL and Docker experience."


def settings(tmp_path: Path, **overrides) -> Settings:
    return Settings(storage_dir=tmp_path, upload_dir=tmp_path / "uploads", **overrides)


def pdf_bytes(pages: list[str], *, password: str | None = None) -> bytes:
    document = pymupdf.open()
    for text in pages:
        page = document.new_page()
        if text:
            if VI_FONT.exists():
                page.insert_font(fontname="viet", fontfile=str(VI_FONT))
                page.insert_text((50, 72), text, fontname="viet", fontsize=11)
            else:  # pragma: no cover - CI without Windows fonts
                page.insert_text((50, 72), text, fontsize=11)
    options = {}
    if password:
        options = {"encryption": pymupdf.PDF_ENCRYPT_AES_256, "owner_pw": password,
                   "user_pw": password}
    data = document.tobytes(**options)
    document.close()
    return data


def png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (60, 40), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def upload(name: str, data: bytes, content_type: str) -> UploadFile:
    return UploadFile(io.BytesIO(data), filename=name,
                      headers=Headers({"content-type": content_type}))


# --------------------------------------------------------------------------
# Upload validation (LocalStorageService)
# --------------------------------------------------------------------------
async def test_cv_01_valid_pdf_is_stored(tmp_path):
    """TC-CV-01: valid PDF is stored under a random id, original name kept."""
    storage = LocalStorageService(settings(tmp_path))
    stored = await storage.save(upload("cv.pdf", pdf_bytes([EN_TEXT]), "application/pdf"))
    assert stored.path.exists() and stored.path.name == f"{stored.file_id}.pdf"
    assert stored.original_filename == "cv.pdf"


async def test_cv_02_single_image_is_converted_to_pdf(tmp_path):
    """TC-CV-02: PNG CV -> 1-page PDF."""
    storage = LocalStorageService(settings(tmp_path))
    stored = await storage.save(upload("cv.png", png_bytes(), "image/png"))
    with pymupdf.open(stored.path) as document:
        assert document.page_count == 1


async def test_cv_03_multi_image_cv_keeps_order(tmp_path):
    """TC-CV-03: up to 5 images combine into one ordered PDF."""
    storage = LocalStorageService(settings(tmp_path))
    files = [upload(f"p{i}.png", png_bytes(), "image/png") for i in range(3)]
    stored = await storage.save_many(files)
    with pymupdf.open(stored.path) as document:
        assert document.page_count == 3
    assert stored.original_filename == "cv-3-pages.pdf"


@pytest.mark.parametrize(
    ("name", "data", "content_type", "code", "status"),
    [
        ("cv.pdf", b"", "application/pdf", "EMPTY_FILE", 422),
        ("cv.pdf", b"hello, I am text", "application/pdf", "INVALID_FILE_SIGNATURE", 422),
        ("cv.docx", b"PK\x03\x04", "application/vnd.openxmlformats", "UNSUPPORTED_MEDIA_TYPE", 415),
        ("cv.png", b"%PDF-1.7", "application/pdf", "INVALID_FILE_EXTENSION", 422),
        ("", b"%PDF-1.7", "application/pdf", "MISSING_FILENAME", 422),
    ],
)
async def test_cv_04_invalid_uploads_rejected(tmp_path, name, data, content_type, code, status):
    """TC-CV-04: empty / spoofed / unsupported / mismatched / corrupt files rejected."""
    storage = LocalStorageService(settings(tmp_path))
    with pytest.raises(FileValidationException) as error:
        await storage.save(upload(name, data, content_type))
    assert (error.value.code, error.value.status_code) == (code, status)
    assert list((tmp_path / "uploads").glob("*")) == []  # no partial files left


@pytest.mark.parametrize("multi", [False, True])
@pytest.mark.parametrize(("name", "data", "content_type"), [
    ("cv.png", b"\x89PNG\r\n\x1a\nbroken", "image/png"),
    ("cv.jpg", b"\xff\xd8\xff\xe0broken-jpeg-body", "image/jpeg"),
])
async def test_cv_04b_corrupted_image_returns_422(tmp_path, multi, name, data, content_type):
    """TC-CV-04b (BUG-016 fixed): an image with a valid signature but corrupt
    body is a 422 INVALID_CV_IMAGE (not a 500) and leaves no file behind."""
    storage = LocalStorageService(settings(tmp_path))
    broken = upload(name, data, content_type)
    with pytest.raises(FileValidationException) as error:
        if multi:
            await storage.save_many([broken, upload("ok.png", png_bytes(), "image/png")])
        else:
            await storage.save(broken)
    assert (error.value.code, error.value.status_code) == ("INVALID_CV_IMAGE", 422)
    assert [p for p in (tmp_path / "uploads").rglob("*") if p.is_file()] == []


async def test_cv_05_oversized_upload_rejected(tmp_path):
    """TC-CV-05: file > MAX_UPLOAD_SIZE_MB -> 413, partial file removed."""
    storage = LocalStorageService(settings(tmp_path, max_upload_size_mb=1,
                                           upload_chunk_size_bytes=64 * 1024))
    with pytest.raises(FileValidationException) as error:
        await storage.save(upload("cv.pdf", b"%PDF-" + b"0" * (1024 * 1024 + 10),
                                  "application/pdf"))
    assert error.value.status_code == 413
    assert list((tmp_path / "uploads").glob("*")) == []


async def test_cv_06_image_count_and_mixing_rules(tmp_path):
    """TC-CV-06: >5 images rejected; PDF cannot be mixed with images."""
    storage = LocalStorageService(settings(tmp_path))
    with pytest.raises(FileValidationException) as too_many:
        await storage.save_many([upload(f"{i}.png", png_bytes(), "image/png") for i in range(6)])
    with pytest.raises(FileValidationException) as mixed:
        await storage.save_many([upload("a.png", png_bytes(), "image/png"),
                                 upload("b.pdf", pdf_bytes([EN_TEXT]), "application/pdf")])
    assert too_many.value.code == "CV_IMAGE_LIMIT_EXCEEDED"
    assert mixed.value.code == "INVALID_CV_FILE_COMBINATION"


async def test_cv_07_path_traversal_filename_is_neutralised(tmp_path):
    """TC-CV-07: '../../evil.pdf' cannot escape the upload directory."""
    storage = LocalStorageService(settings(tmp_path))
    stored = await storage.save(upload("..\\..\\evil.pdf", pdf_bytes([EN_TEXT]),
                                       "application/pdf"))
    assert stored.original_filename == "evil.pdf"
    assert stored.path.parent == tmp_path / "uploads"


# --------------------------------------------------------------------------
# PDF inspection and native extraction
# --------------------------------------------------------------------------
def write(tmp_path: Path, data: bytes) -> Path:
    path = tmp_path / "doc.pdf"
    path.write_bytes(data)
    return path


async def test_cv_08_encrypted_pdf_rejected(tmp_path):
    """TC-CV-08: password-protected PDF -> ENCRYPTED_PDF_NOT_SUPPORTED."""
    with pytest.raises(FileValidationException) as error:
        await PdfInspector(settings(tmp_path)).inspect(
            write(tmp_path, pdf_bytes([EN_TEXT], password="secret")))
    assert error.value.code == "ENCRYPTED_PDF_NOT_SUPPORTED"


async def test_cv_09_page_limit(tmp_path):
    """TC-CV-09: 21 pages with MAX_PDF_PAGES=20 -> PDF_PAGE_LIMIT_EXCEEDED."""
    with pytest.raises(FileValidationException) as error:
        await PdfInspector(settings(tmp_path)).inspect(write(tmp_path, pdf_bytes(["x"] * 21)))
    assert error.value.code == "PDF_PAGE_LIMIT_EXCEEDED"


async def test_cv_10_corrupted_pdf(tmp_path):
    """TC-CV-10: truncated/garbage PDF -> structured validation error, not 500."""
    with pytest.raises(FileValidationException):
        await PdfInspector(settings(tmp_path)).inspect(
            write(tmp_path, b"%PDF-1.7\n1 0 obj << /Type /Catalog >> garbage"))


@pytest.mark.skipif(not VI_FONT.exists(), reason="needs a Unicode TTF font")
async def test_cv_11_vietnamese_english_multipage_extraction(tmp_path):
    """TC-CV-11: Vietnamese diacritics and English survive native extraction;
    pages keep their order; a blank page is flagged for OCR."""
    path = write(tmp_path, pdf_bytes([VI_TEXT, "", EN_TEXT]))
    result = await NativePdfTextExtractor(settings(tmp_path)).extract(path)
    assert "Công ty Đại Việt" in result.pages[0].text
    assert "PostgreSQL" in result.pages[2].text
    assert result.ocr_required_page_numbers == (2,)


def test_cv_12_merger_prefers_native_then_ocr():
    """TC-CV-12: native text kept when meaningful; OCR fills empty pages."""
    from app.services.pdf.models import (
        NativeTextExtractionResult,
        OcrPageText,
        PdfPageText,
    )

    native = NativeTextExtractionResult(
        pages=(PdfPageText(1, "native text", (), 11, 2, True),
               PdfPageText(2, "", (), 0, 0, False)),
        full_text="native text", total_character_count=11, total_word_count=2,
        native_page_count=1, ocr_required_page_numbers=(2,))
    ocr = OcrTextExtractionResult(
        pages=(OcrPageText(2, "ocr text", (), 7, 2, 0.9),), full_text="ocr text",
        total_character_count=7, total_word_count=2, ocr_page_count=1)
    merged = PdfTextMerger().merge(native_result=native, ocr_result=ocr)
    assert [(p.text, p.method) for p in merged.pages] == [("native text", "native"),
                                                         ("ocr text", "ocr")]


# --------------------------------------------------------------------------
# Parsing guard rails and provenance verification
# --------------------------------------------------------------------------
class NoOcr:
    async def extract(self, *, file_path, page_numbers):
        return OcrTextExtractionResult(pages=(), full_text="", total_character_count=0,
                                       total_word_count=0, ocr_page_count=0)


class ParserReturning:
    def __init__(self, profile):
        self.profile = profile
        self.texts: list[str] = []

    async def parse(self, text: str):
        self.texts.append(text)
        if not text.strip():
            raise FileValidationException(message="No readable text was found in the CV.")
        return self.profile


def processing(tmp_path, parser):
    cfg = settings(tmp_path)
    storage = LocalStorageService(cfg)
    ingestion = CVIngestionService(storage=storage, pdf_inspector=PdfInspector(cfg),
                                   text_extractor=NativePdfTextExtractor(cfg),
                                   ocr_extractor=NoOcr(), text_merger=PdfTextMerger())
    repo = FakeCVRepository()
    return CVProcessingService(ingestion_service=ingestion, parser_agent=parser,
                               storage_service=storage, cv_repository=repo), repo, storage


@pytest.mark.skipif(not VI_FONT.exists(), reason="needs a Unicode TTF font")
async def test_cv_13_fabricated_provenance_is_dropped(tmp_path):
    """TC-CV-13: provenance excerpts not present on the page are discarded and
    the profile is flagged needs_review (anti-hallucination guard)."""
    profile = make_cv_profile(provenance=[
        CVFieldProvenance(field_path="skills[0]", page_number=1,
                          source_text="Kỹ năng: Python", confidence=0.95),
        CVFieldProvenance(field_path="skills[1]", page_number=1,
                          source_text="Kubernetes expert 10 years", confidence=0.99),
    ])
    service, repo, _ = processing(tmp_path, ParserReturning(profile))
    result = await service.process(upload("cv.pdf", pdf_bytes([VI_TEXT]), "application/pdf"))
    assert [p.source_text for p in result.profile.provenance] == ["Kỹ năng: Python"]
    assert result.profile.needs_review is True
    assert result.profile.provenance[0].extraction_method == "native"
    assert repo.profiles  # persisted


async def test_cv_14_blank_cv_rejected_and_rolled_back(tmp_path):
    """TC-CV-14: CV without any text -> 422 and the stored file is removed."""
    service, repo, _ = processing(tmp_path, ParserReturning(make_cv_profile()))
    with pytest.raises(FileValidationException):
        await service.process(upload("cv.pdf", pdf_bytes([""]), "application/pdf"))
    assert repo.profiles == {}
    assert list((tmp_path / "uploads").glob("*.pdf")) == []


async def test_cv_15_parser_text_limits():
    """TC-CV-15: real CVParserAgent rejects empty and oversized text before
    calling the LLM."""
    from app.agents.cv_parser_agent import CVParserAgent

    class NeverCalled:
        def with_structured_output(self, *args, **kwargs):
            return self

        async def ainvoke(self, *_):  # pragma: no cover
            raise AssertionError("LLM must not be called")

    agent = CVParserAgent(llm=NeverCalled(), settings=Settings(max_cv_text_chars=1000))
    for text in ("   ", "x" * 1001):
        with pytest.raises(FileValidationException):
            await agent.parse(text)


# --------------------------------------------------------------------------
# BUG-026: Vietnamese text through OCR
# --------------------------------------------------------------------------
# Real output of PP-OCRv6_medium_rec for a Vietnamese CV image (BUG_REPORT,
# LIVE): tone-marked letters are dropped while confidence stays ~1.0.
LOSSY_VI_LINES = [
    ("NGUYEN VAN TEST - Backend Developer", 1.0),
    ("Ký năng: Python, FastAPI, PostgreSQL, Docker", 0.98),
    ("Kinh nghim: 2 năm ti Công ty Đi Vit (01/2022 - 01/2024)", 1.0),
    ("Hc vn: C nhân Khoa hc Máy tính - HCMUS", 0.99),
    ("English: IELTS 6.5", 0.99),
]
ENGLISH_LINES = [("John Doe - Backend Developer", 0.99),
                 ("Experience: 2 years at Acme Corp", 0.98),
                 ("Education: BSc Computer Science", 0.99)]


@pytest.mark.parametrize(("text", "expected"), [
    ("\n".join(line for line, _ in LOSSY_VI_LINES), True),
    ("Kinh nghiệm 2 năm tại Công ty Đại Việt", True),
    ("\n".join(line for line, _ in ENGLISH_LINES), False),
    ("Café crème – résumé", False),
    ("", False),
])
def test_cv_16_vietnamese_ocr_text_is_detected(text, expected):
    """TC-CV-16 (BUG-026): Vietnamese pages are recognised from the letters the
    OCR model can still output (ă ơ ư đ, frequent syllables)."""
    from app.services.pdf.ocr_quality import looks_vietnamese

    assert looks_vietnamese(text) is expected


def _fake_prediction(lines):
    return [{"res": {"rec_texts": [t for t, _ in lines], "rec_scores": [s for _, s in lines],
                     "rec_boxes": [[10, 20 + 30 * i, 400, 40 + 30 * i]
                                   for i in range(len(lines))]}}]


@pytest.mark.parametrize(("lines", "lossy"), [(LOSSY_VI_LINES, True), (ENGLISH_LINES, False)])
def test_cv_16b_lossy_vietnamese_ocr_page_is_flagged(tmp_path, lines, lossy):
    """TC-CV-16b (BUG-026): an OCR page that looks Vietnamese gets the
    'vietnamese_diacritics_unsupported' issue and a confidence below the 0.7
    review threshold, although the model reported ~0.99; English is untouched."""
    from app.services.pdf import PdfOcrExtractor

    extractor = PdfOcrExtractor(settings(tmp_path))
    extractor._predict = lambda image: _fake_prediction(lines)
    with pymupdf.open() as document:
        page = document.new_page()
        result = extractor._extract_page(page=page, page_number=1)
    raw_average = sum(s for _, s in lines) / len(lines)
    if lossy:
        assert result.quality_issues == ("vietnamese_diacritics_unsupported",)
        assert result.average_confidence <= 0.5 < raw_average
    else:
        assert result.quality_issues == ()
        assert result.average_confidence == pytest.approx(raw_average)


class FixedOcr:
    def __init__(self, page):
        self.page = page

    async def extract(self, *, file_path, page_numbers):
        return OcrTextExtractionResult(pages=(self.page,), full_text=self.page.text,
                                       total_character_count=self.page.character_count,
                                       total_word_count=self.page.word_count, ocr_page_count=1)


@pytest.mark.parametrize(("issues", "needs_review"), [
    (("vietnamese_diacritics_unsupported",), True), ((), False)])
async def test_cv_16c_profile_from_lossy_ocr_needs_review(tmp_path, issues, needs_review):
    """TC-CV-16c (BUG-026): a CV whose text comes from a lossy Vietnamese OCR
    page is always flagged needs_review (no silent corruption)."""
    from app.services.pdf.models import OcrPageText

    text = "Python FastAPI Docker"
    page = OcrPageText(1, text, (), len(text), 3, 0.95, quality_issues=issues)
    cfg = settings(tmp_path)
    storage = LocalStorageService(cfg)
    ingestion = CVIngestionService(storage=storage, pdf_inspector=PdfInspector(cfg),
                                   text_extractor=NativePdfTextExtractor(cfg),
                                   ocr_extractor=FixedOcr(page), text_merger=PdfTextMerger())
    profile = make_cv_profile(skills=[], work_experiences=[], educations=[])
    service = CVProcessingService(ingestion_service=ingestion,
                                  parser_agent=ParserReturning(profile),
                                  storage_service=storage, cv_repository=FakeCVRepository())
    result = await service.process(upload("cv.pdf", pdf_bytes([""]), "application/pdf"))
    assert result.profile.needs_review is needs_review


def test_cv_16d_configured_ocr_model_vietnamese_coverage_documented():
    """TC-CV-16d (BUG-026 root cause): the configured recognition model's
    character dictionary lacks Vietnamese tone-marked letters. If a future
    model covers them, this test fails and the review flag can be revisited."""
    yaml = pytest.importorskip("yaml")
    model_dir = Path.home() / ".paddlex" / "official_models" / "PP-OCRv6_medium_rec"
    if not (model_dir / "inference.yml").is_file():
        pytest.skip("PP-OCRv6_medium_rec is not cached locally")
    config = yaml.safe_load((model_dir / "inference.yml").read_text(encoding="utf-8"))
    chars = set(config["PostProcess"]["character_dict"])
    assert not {"ệ", "ạ", "ọ", "ữ", "ỹ"} <= chars


# --------------------------------------------------------------------------
# BUG-028: page-aware CV processing budget
# --------------------------------------------------------------------------
class _RecordingTasks:
    def __init__(self, task):
        self.task = task
        self.completed, self.failed = [], []

    async def claim_next(self, **_):
        task, self.task = self.task, None
        return task

    async def renew_lease(self, **_):
        return True

    async def mark_completed(self, *, task_id, worker_id):
        self.completed.append(task_id)

    async def mark_failed(self, **kwargs):  # pragma: no cover - must not happen
        self.failed.append(kwargs)


def _worker(tmp_path, tasks, processing, **overrides):
    from app.services.cv_tasks import CVTaskWorker

    values = {"worker_id": "w", "tasks": tasks, "processing": processing,
              "upload_dir": tmp_path, "lease_seconds": 60, "heartbeat_seconds": 30,
              "timeout_seconds": 0.2, "max_attempts": 2, "poll_seconds": 0.1,
              "timeout_seconds_per_page": 0.2, "max_timeout_seconds": 5}
    return CVTaskWorker(**{**values, **overrides})


def _stored_pdf(tmp_path, pages: int):
    from app.services.storage import StoredFile

    cv_id = "c" * 32
    path = tmp_path / f"{cv_id}.pdf"
    path.write_bytes(pdf_bytes(["page"] * pages))
    return StoredFile(file_id=cv_id, path=path, original_filename="cv.pdf",
                      content_type="application/pdf", size_bytes=path.stat().st_size)


@pytest.mark.parametrize(("pages", "per_page", "cap", "expected"), [
    (1, 45, 1800, 165), (5, 45, 1800, 345), (20, 45, 600, 600), (5, 0, 1800, 120)])
async def test_cv_17_timeout_scales_with_page_count(tmp_path, pages, per_page, cap, expected):
    """TC-CV-17 (BUG-028): budget = base + pages * per_page, capped; a 5-page
    image CV gets 345 s instead of the fixed 120 s that always expired."""
    worker = _worker(tmp_path, None, None, timeout_seconds=120,
                     timeout_seconds_per_page=per_page, max_timeout_seconds=cap)
    assert await worker._timeout_for(_stored_pdf(tmp_path, pages)) == expected


async def test_cv_17b_unreadable_file_gets_base_budget(tmp_path):
    """TC-CV-17b: an unreadable file falls back to the base budget."""
    from app.services.storage import StoredFile

    worker = _worker(tmp_path, None, None, timeout_seconds=120,
                     timeout_seconds_per_page=45, max_timeout_seconds=1800)
    missing = StoredFile(file_id="d" * 32, path=tmp_path / "missing.pdf",
                         original_filename="cv.pdf", content_type="application/pdf",
                         size_bytes=1)
    assert await worker._timeout_for(missing) == 120


async def test_cv_17c_multi_page_cv_slower_than_base_timeout_completes(tmp_path):
    """TC-CV-17c (BUG-028): processing longer than the base timeout but within
    the page-aware budget completes instead of timing out (and recycling)."""
    import asyncio
    from datetime import UTC, datetime
    from uuid import uuid4

    from app.repositories.cv_task import CVTaskRecord
    from app.schemas.cv_task import CVTaskStatus

    stored = _stored_pdf(tmp_path, 3)  # budget 0.2 + 3 * 0.2 = 0.8 s

    class SlowProcessing:
        async def process_stored(self, stored_file):
            await asyncio.sleep(0.4)  # > base 0.2 s

    task = CVTaskRecord(task_id=uuid4(), cv_id=stored.file_id, user_id=uuid4(),
                        original_filename="cv.pdf", content_type="application/pdf",
                        size_bytes=stored.size_bytes, status=CVTaskStatus.PROCESSING,
                        attempt_count=1, created_at=datetime.now(UTC), started_at=None,
                        completed_at=None, error_code=None, error_message=None)
    tasks = _RecordingTasks(task)
    assert await _worker(tmp_path, tasks, SlowProcessing()).run_once() is True
    assert tasks.completed == [task.task_id] and tasks.failed == []
