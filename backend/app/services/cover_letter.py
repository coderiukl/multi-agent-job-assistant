import logging

from app.agents.cover_letter_agent import CoverLetterAgent
from app.schemas.cover_letter import (
    CoverLetterDraft,
    CoverLetterInput,
    CoverLetterLanguage,
    CoverLetterResult,
)


logger = logging.getLogger(__name__)


class CoverLetterService:
    def __init__(self, *, agent: CoverLetterAgent) -> None:
        self._agent = agent

    async def generate(self, letter_input: CoverLetterInput) -> CoverLetterResult:
        draft = await self._agent.generate(letter_input)
        full_text = self._build_full_text(draft)
        word_count = len(full_text.split())

        result = CoverLetterResult(
            **draft.model_dump(),
            full_text=full_text,
            word_count=word_count,
            is_personalized=True,
        )

        logger.info(
            "Cover letter generation completed",
            extra={
                "language": result.language.value,
                "tone": result.tone.value,
                "word_count": result.word_count,
                "confidence": result.confidence,
            },
        )

        return result

    @staticmethod
    def _build_full_text(draft: CoverLetterDraft,) -> str:
        subject_label = "Tiêu đề" if (draft.language == CoverLetterLanguage.VIETNAMESE) else "Subject"

        sections = [
            f"{subject_label}: {draft.subject}",
            draft.salutation,
            draft.opening_paragraph,
            *draft.body_paragraphs,
            draft.closing_paragraph,
            draft.complimentary_close,
        ]

        if draft.signature_name:
            sections.append(draft.signature_name)

        return "\n\n".join(sections)