from typing import Any, Literal

from app.schemas.cv_profile import CVProfile

CVDisclosurePurpose = Literal[
    "analysis",
    "career_advice",
    "job_matching",
    "cover_letter",
]


def cv_profile_for_llm(
    profile: CVProfile,
    *,
    purpose: CVDisclosurePurpose,
) -> dict[str, Any]:
    """Return the minimum CV fields required for an LLM task.

    Contact details and profile URLs are never required for analysis, career
    advice, or matching. Cover letters may use the candidate's name as a
    signature, so that purpose receives only the name from the personal block.
    """

    payload = profile.model_dump(
        mode="json",
        exclude={"personal_information"},
        exclude_none=True,
    )

    if purpose == "cover_letter":
        full_name = profile.personal_information.full_name
        if full_name:
            payload["personal_information"] = {"full_name": full_name}

    return payload
