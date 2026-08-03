from uuid import uuid4

import fitz

from app.core.config import Settings
from app.core.exceptions import PDFInspectionException
from app.schemas.cv_processing import (
    DocumentBlock,
    DocumentBlockSource,
    DocumentBlockType,
    PageAnalysis,
    PageType
)

from app.services.cv_processing.image_preprocessor import ImagePreprocessor
from app.services.cv_processing.ocr_engine import OCREngine
from app.services.cv_processing.page_renderer import PageRenderer

class OCRPipeline:
    """Run OCR only for scanned pages or selected hybrid image reions."""

    def __init__(self, *, settings: Settings, renderer: PageRenderer, preprocessor: ImagePreprocessor, ocr_engine: OCREngine) -> None:
        self.settings = settings
        self.renderer = renderer
        self.preprocessor = preprocessor
        self.ocr_engine = ocr_engine

    def extract_ocr_blocks(self, *, content: bytes, page_analyses: list[PageAnalysis]) -> list[DocumentBlock]:
        if not self.settings.ocr_enabled:
            return []

        try: 
            document = fitz.open(stream=content, filetype="pdf")
        except fitz.FileDataError as exc:
            raise PDFInspectionException(message="PDF cannot be opened.") from exc

        try:
            blocks : list[DocumentBlock] = []

            for analysis in page_analyses:
                page = document.load_page(analysis.page_number - 1)

                if analysis.page_type == PageType.SCANNED:
                    blocks.extend(self._ocr_full_page(page, analysis.page_number))

                if analysis.page_type == PageType.HYBRID:
                    blocks.extend(self._ocr_image_regions(page, analysis.page_number))

            return blocks
        finally:
            document.close()

    def _ocr_full_page(self, *, page: fitz.Page, page_number: int) -> list[DocumentBlock]:
        image = self.renderer.render_page(page, dpi=self.settings.pdf_render_dpi)
        processed = self.preprocessor.preprocess(image)
        results = self.ocr_engine.recognize(processed)

        page_bbox = (
            0.0,
            0.0,
            float(page.rect.width),
            float(page.rect.height)
        )

        height, width = processed.shape[:2]

        blocks: list[DocumentBlock] = []

        for result in results:
            page_text_bbox = self.renderer.image_bbox_to_page_bbox(
                image_bbox=result.bbox,
                page_bbox=page_bbox,
                image_width=width,
                image_height=height,
            )

            blocks.append(
                self._create_block(
                    page_number=page_number,
                    source=DocumentBlockSource.OCR_FULL_PAGE,
                    text=result.text,
                    bbox=page_text_bbox,
                    confidence=result.confidence,
                    metadata={"ocr_scope": "full_page"},
                )
            )

        return blocks

    def _ocr_image_regions(self, page: fitz.Page, page_number: int) -> list[DocumentBlock]:
        page_dict = page.get_text("dict")
        page_area = max(float(page.rect.width * page.rect.height), 1.0)
        blocks: list[DocumentBlock] = []

        for index, block in enumerate(page_dict.get("blocks", [])):
            if block.get("type") != 1:
                continue

            bbox = tuple(float(value) for value in block.get("bbox", []))
            if len(bbox) != 4:
                continue

            if self._bbox_area(bbox) / page_area < self.settings.min_ocr_region_area_ratio:
                continue

            image = self.renderer.render_region(page, bbox=bbox, dpi=self.settings.pdf_render_dpi)
            processed = self.preprocessor.preprocess(image)
            results = self.ocr_engine.recognize(processed)

            height, width = processed.shape[:2]

            for result in results:
                page_text_bbox = self.renderer.image_bbox_to_page_box(
                    image_bbox=result.bbox,
                    page_bbox=bbox,
                    image_width=width,
                    image_height=height
                )

                blocks.append(
                    self._create_block(
                        page_number=page_number,
                        source=DocumentBlockSource.OCR_IMAGE_REGION,
                        text=result.text,
                        bbox=page_text_bbox,
                        confidence=result.confidence,
                        metadata={
                            "ocr_scope": "image_region",
                            "region_index": index,
                            "region_bbox": bbox,
                        }
                    )
                )

        return blocks

    def _create_block(self, *, page_number: int, source: DocumentBlockSource, text: str, bbox: tuple[float, float, float, float], confidence: float, metadata: dict[str, object]) -> DocumentBlock:
        return DocumentBlock(
            block_id=str(uuid4()),
            page_number=page_number,
            source=source,
            block_type=DocumentBlockType.TEXT,
            text=text,
            raw_text=text,
            normalized_text=None,
            bbox=bbox,
            confidence=confidence,
            font_name=None,
            font_size=None,
            is_bold=False,
            is_italic=False,
            metadata=metadata,
        )

    def _bbox_area(self, bbox: tuple[float, float, float, float]) -> float:
        x0, y0, x1, y1 = bbox
        return max(0.0, x1 - x0) * max(0.0, y1 - y0)
    
        
        