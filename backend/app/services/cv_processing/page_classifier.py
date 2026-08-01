from pydantic import BaseModel, Field

from app.core.config import Settings
from app.schemas.cv_processing import PageType


class PageClassificationSignals(BaseModel):
    text_length: int = Field(ge=0)
    text_block_count: int = Field(ge=0)
    image_count: int = Field(ge=0)
    image_coverage: float = Field(ge=0.0, le=1.0)
    text_coverage: float = Field(ge=0.0, le=1.0)
    has_encoding_issues: bool = False


class PageClassifier:
    """Classify each PDF page from text and image structure signals."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def classify(self, signals: PageClassificationSignals) -> PageType:
        has_no_content = (
            signals.text_length == 0
            and signals.text_block_count == 0
            and signals.image_count == 0
        )

        if has_no_content:
            return PageType.EMPTY

        has_enough_text = (
            signals.text_length >= self.settings.min_text_length_for_digital_page
            and signals.text_block_count >= self.settings.min_text_blocks_for_digital_page
        )

        if (
            signals.image_coverage >= self.settings.scan_image_coverage_threshold
            and signals.text_length < self.settings.min_text_length_for_digital_page
        ):
            return PageType.SCANNED

        if (
            has_enough_text
            and signals.image_coverage >= self.settings.hybrid_image_coverage_threshold
        ):
            return PageType.HYBRID

        if has_enough_text and not signals.has_encoding_issues:
            return PageType.DIGITAL_TEXT

        if signals.has_encoding_issues:
            return PageType.UNKNOWN

        return PageType.UNKNOWN