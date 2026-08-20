import asyncio
import logging
from pathlib import Path
from typing import Any

import pymupdf

from app.core.config import Settings
from app.core.exceptions import (
    FileValidationException,
    ResourceNotFoundException,
    StorageException
)
from app.services.pdf.models import (
    PdfInspectionResult,
    PdfMetadata
)

logger = logging.getLogger(__name__)

MAX_METADATA_LENGTH = 500

class PdfInspector:
    def __init__(self, settings: Settings) -> None:
        self._max_pdf_pages = settings.max_pdf_pages

    async def inspect(self, path: Path) -> PdfInspectionResult:

        return await asyncio.to_thread(self._inspect_sync, path)

    def _inspect_sync(self, path: Path) -> PdfInspectionResult:
        try:
            with pymupdf.open(str(path)) as document:
                if not document.is_pdf:
                    raise FileValidationException(
                        message=(
                            "The uploaded document is not a PDF."
                        ),
                        code="INVALID_PDF_FORMAT",
                    )

                if document.needs_pass:
                    raise FileValidationException(
                        message=(
                            "Password-protected PDF files are "
                            "not supported."
                        ),
                        code="ENCRYPTED_PDF_NOT_SUPPORTED",
                    )

                page_count = document.page_count

                if page_count < 1:
                    raise FileValidationException(
                        message=(
                            "The PDF document does not contain "
                            "any pages."
                        ),
                        code="PDF_HAS_NO_PAGES",
                    )

                if page_count > self._max_pdf_pages:
                    raise FileValidationException(
                        message=(
                            "The PDF document exceeds the "
                            "maximum page limit."
                        ),
                        code="PDF_PAGE_LIMIT_EXCEEDED",
                        details={
                            "page_count": page_count,
                            "max_pdf_pages": (
                                self._max_pdf_pages
                            ),
                        },
                    )

                # Load từng trang để phát hiện object/page hỏng.
                for page_number in range(page_count):
                    document.load_page(page_number)

                metadata = self._extract_metadata(
                    document.metadata or {},
                )

                result = PdfInspectionResult(
                    page_count=page_count,
                    is_repaired=bool(document.is_repaired),
                    metadata=metadata,
                )

                logger.info(
                    "PDF inspection completed",
                    extra={
                        "page_count": page_count,
                        "is_repaired": bool(
                            document.is_repaired,
                        ),
                    },
                )

                return result

        except FileValidationException:
            raise

        except FileNotFoundError as exc:
            raise ResourceNotFoundException(
                resource="Stored CV",
                identifier=path.name
            ) from exc

        except (
            pymupdf.EmptyFileError,
            pymupdf.FileDataError,
            RuntimeError,
            ValueError,
        ) as exc:
            logger.warning(
                "Invalid PDF structure detected",
                extra={"stored_filename": path.name},
            )

            raise FileValidationException(
                message=(
                    "The PDF file is corrupted or has an "
                    "invalid structure."
                ),
                code="INVALID_PDF_STRUCTURE",
            ) from exc

        except OSError as exc:
            logger.exception(
                "Failed to read stored PDF",
                extra={"stored_filename": path.name},
            )

            raise StorageException(
                message="The stored PDF could not be read.",
            ) from exc

    @classmethod
    def _extract_metadata(cls, metadata: dict[str, Any]) -> PdfMetadata:
        return PdfMetadata(
            title=cls._clean_metadata(
                metadata.get("title"),
            ),
            author=cls._clean_metadata(
                metadata.get("author"),
            ),
            subject=cls._clean_metadata(
                metadata.get("subject"),
            ),
            keywords=cls._clean_metadata(
                metadata.get("keywords"),
            ),
            creator=cls._clean_metadata(
                metadata.get("creator"),
            ),
            producer=cls._clean_metadata(
                metadata.get("producer"),
            ),
            creation_date=cls._clean_metadata(
                metadata.get("creationDate"),
            ),
            modification_date=cls._clean_metadata(
                metadata.get("modDate"),
            ),
        )

    @staticmethod
    def _clean_metadata(value: Any) -> str | None:
        if not isinstance(value, str):
            return None

        cleaned_value = value.strip()

        if not cleaned_value:
            return None

        return cleaned_value[:MAX_METADATA_LENGTH]
