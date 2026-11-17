import logging

from app.agents.cover_letter_agent import CoverLetterAgent
from app.schemas.cover_letter import (
    CoverLetterDraft,
    CoverLetterInput,
    CoverLetterLanguage,
    CoverLetterResult,
)
from app.utils.cv_grounding import CVGroundingChecker, fold_text

logger = logging.getLogger(__name__)

# A letter with unverifiable claims is never presented as high-confidence.
UNGROUNDED_CONFIDENCE_CAP = 0.5


class CoverLetterService:
    def __init__(self, *, agent: CoverLetterAgent) -> None:
        self._agent = agent

    async def generate(self, letter_input: CoverLetterInput) -> CoverLetterResult:
        draft = await self._agent.generate(letter_input)
        draft, warnings, grounded_evidence = self._ground_draft(draft, letter_input)
        full_text = self._build_full_text(draft)
        word_count = len(full_text.split())

        confidence = draft.confidence
        if warnings:
            confidence = min(confidence, UNGROUNDED_CONFIDENCE_CAP)

        result = CoverLetterResult(
            **draft.model_dump(exclude={"confidence"}),
            confidence=round(confidence, 3),
            full_text=full_text,
            word_count=word_count,
            is_personalized=bool(grounded_evidence),
            grounding_warnings=warnings,
        )

        logger.info(
            "Cover letter generation completed",
            extra={
                "language": result.language.value,
                "tone": result.tone.value,
                "word_count": result.word_count,
                "confidence": result.confidence,
                "grounding_warning_count": len(warnings),
            },
        )

        return result

    @staticmethod
    def _ground_draft(
        draft: CoverLetterDraft, letter_input: CoverLetterInput
    ) -> tuple[CoverLetterDraft, list[str], list[str]]:
        """Post-check the draft against the CV (BUG-015).

        * The signature is always the CV owner's name (or omitted).
        * cv_evidence_used items that do not come from the CV are removed.
        * Years-of-experience figures the CV cannot support are flagged.
        The human reviewer sees every warning before approving the letter.
        """
        checker = CVGroundingChecker(letter_input.cv_profile)
        warnings: list[str] = []
        updates: dict[str, object] = {}

        cv_name = checker.full_name
        signature = draft.signature_name
        name_differs = cv_name is None or (
            fold_text(signature or "") != fold_text(cv_name)
        )
        if signature and name_differs:
            warnings.append(
                "The signature did not match the CV owner's name and was replaced."
                if cv_name
                else "The signature name is not in the CV and was removed."
            )
        updates["signature_name"] = cv_name if (signature or cv_name) else None

        grounded, ungrounded = checker.split(draft.cv_evidence_used)
        if ungrounded:
            updates["cv_evidence_used"] = grounded
            warnings.extend(
                f"Claim not found in the CV and removed from the evidence: {claim}"
                for claim in ungrounded
            )

        letter_text = "\n".join(
            [draft.opening_paragraph, *draft.body_paragraphs, draft.closing_paragraph]
        )
        for years in checker.overstated_years(letter_text):
            supported = (
                f"the CV shows about {checker.total_years:g} years"
                if checker.total_years is not None
                else "the CV has no verifiable work duration"
            )
            warnings.append(
                f"The letter mentions {years:g} years of experience, but {supported}."
            )

        return draft.model_copy(update=updates), warnings[:10], grounded

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