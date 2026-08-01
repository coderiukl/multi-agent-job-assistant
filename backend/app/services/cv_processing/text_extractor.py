
from typing import Any
from uuid import uuid4

import fitz
from pydantic import BaseModel

from app.core.exceptions import PDFInspectionException
from app.schemas.cv_processing import (
    DocumentBlock,
    DocumentBlockSource,
    DocumentBlockType,
)

class BlockFontMetadata(BaseModel):
    font_name: str | None = None
    font_size: float | None = None
    is_bold: bool = False
    is_italic: bool = False

class NativeTextExtractor:
    """Extract native PDF text blocks using PyMuPDF."""

    def extract_bytes(self, content: bytes) -> list[DocumentBlock]:
        try:
            document = fitz.open(stream=content, filetype="pdf")
        except fitz.FileDataError as exc:
            raise PDFInspectionException(message="PDF cannot be opened.") from exc

        try:
            if document.is_encrypted:
                raise PDFInspectionException(
                    message="Encrypted PDF is not supported.",
                )

            blocks: list[DocumentBlock] = []

            for page_index in range(document.page_count):
                page = document.load_page(page_index)
                blocks.extend(
                    self._extract_page_blocks(
                        page=page,
                        page_number=page_index + 1,
                    )
                )

            return blocks
        finally:
            document.close()

    def _extract_page_blocks(self, page: fitz.Page, page_number: int) -> list[DocumentBlock]:
        page_dict = page.get_text("dict")
        document_blocks: list[DocumentBlock] = []

        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:
                continue

            raw_text = self._extract_block_text(block).strip()

            if not raw_text:
                continue

            font_metadata = self._extract_block_font_metadata(block)
            bbox = self._extract_bbox(block)

            document_blocks.append(
                DocumentBlock(
                    block_id=str(uuid4()),
                    page_number=page_number,
                    source=DocumentBlockSource.PDF_TEXT,
                    block_type=DocumentBlockType.TEXT,
                    text=raw_text,
                    raw_text=raw_text,
                    normalized_text=None,
                    bbox=bbox,
                    confidence=1.0,
                    font_name=font_metadata.font_name,
                    font_size=font_metadata.font_size,
                    is_bold=font_metadata.is_bold,
                    is_italic=font_metadata.is_italic,
                    metadata={
                        "line_count": len(block.get("lines", [])),
                    },
                )
            )

        return document_blocks

    def _extract_block_text(self, block: dict[str, Any]) -> str:
        lines: list[str] = []

        for line in block.get("lines", []):
            spans: list[str] = []

            for span in line.get("spans", []):
                text = span.get("text", "")
                if text:
                    spans.append(text)

            if spans:
                lines.append("".join(spans))

        return "\n".join(lines)

    def _extract_block_font_metadata(self, block: dict[str, Any]) -> BlockFontMetadata:
        first_span = self._get_first_span(block)

        if first_span is None:
            return BlockFontMetadata()

        return BlockFontMetadata(
            font_name=first_span.get("font"),
            font_size=float(first_span["size"]) if "size" in first_span else None,
            is_bold=self._is_bold_span(first_span),
            is_italic=self._is_italic_span(first_span),
        )

    def _get_first_span(self, block: dict[str, Any]) -> dict[str, Any] | None:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                return span

        return None

    def _is_bold_span(self, span: dict[str, Any]) -> bool:
        font_name = str(span.get("font", "")).lower()
        flags = int(span.get("flags", 0))

        return "bold" in font_name or bool(flags & 16)


    def _is_italic_span(self, span: dict[str, Any]) -> bool:
        font_name = str(span.get("font", "")).lower()
        flags = int(span.get("flags", 0))

        return "italic" in font_name or "oblique" in font_name or bool(flags & 2)

    def _extract_bbox(self, block: dict[str, Any]) -> tuple[float, float, float, float]:
        bbox = block.get("bbox")

        if bbox is None or len(bbox) != 4:
            return (0.0, 0.0, 0.0, 0.0)

        x0, y0, x1, y1 = bbox

        return (
            float(x0),
            float(y0),
            float(x1),
            float(y1),
        )