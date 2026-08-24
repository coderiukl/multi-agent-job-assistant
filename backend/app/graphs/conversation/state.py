from typing import TypedDict

from app.schemas.conversation import (
    ConversationRoute,
    ConversationStatus,
    RequiredInput,
)
from app.schemas.conversations_intent import IntentAnalysisResult
from app.schemas.cv_profile import CVProfile

class ConversationState(TypedDict, total=False):
    # Dữ liệu từ request
    message: str
    cv_id: str | None
    job_description: str | None

    # Context được backend xác thực
    cv_profile: CVProfile | None
    has_cv: bool
    has_jd: bool

    # Kết quả Intent Analysis
    intent: IntentAnalysisResult

    # Kết quả điều phối
    route: ConversationRoute
    status: ConversationStatus
    missing_inputs: list[RequiredInput]

    # Nội dung trả về người dùng
    assistant_message: str