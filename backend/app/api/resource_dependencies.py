from typing import Annotated

from fastapi import Depends

from app.api.auth_dependencies import CurrentUserDependency
from app.core.config import get_settings
from app.repositories.conversation_turn import ConversationTurnRepository
from app.repositories.ownership import OwnershipRepository
from app.services.authorized_conversation import (
    AuthorizedConversationService,
)
from app.services.authorized_cv import (
    AuthorizedCVProcessingService,
)
from app.services.cv_lifecycle import CVDataLifecycleService
from app.services.cv_tasks import AuthorizedCVTaskService


def get_authorized_conversation_service(
    user: CurrentUserDependency,
) -> AuthorizedConversationService:
    from app.api.dependencies import (
        get_conversation_graph,
        get_job_session_factory,
    )
    from app.services.conversation import ConversationService

    graph = get_conversation_graph()

    return AuthorizedConversationService(
        user_id=user.user_id,
        service=ConversationService(graph=graph),
        graph=graph,
        ownership=OwnershipRepository(get_job_session_factory()),
        turns=ConversationTurnRepository(get_job_session_factory()),
    )


def get_authorized_cv_processing_service(
    user: CurrentUserDependency,
) -> AuthorizedCVProcessingService:
    from app.api.dependencies import (
        get_chat_model,
        get_conversation_memory,
        get_cv_ingestion_service,
        get_cv_parser_agent,
        get_cv_processing_service,
        get_cv_repository,
        get_job_session_factory,
        get_native_pdf_text_extractor,
        get_pdf_inspector,
        get_pdf_ocr_extractor,
        get_pdf_text_merger,
        get_storage_service,
    )

    storage = get_storage_service()
    repository = get_cv_repository()

    ingestion = get_cv_ingestion_service(
        storage_service=storage,
        pdf_inspector=get_pdf_inspector(),
        text_extractor=get_native_pdf_text_extractor(),
        ocr_extractor=get_pdf_ocr_extractor(),
        text_merger=get_pdf_text_merger(),
    )

    processing = get_cv_processing_service(
        ingestion_service=ingestion,
        parser_agent=get_cv_parser_agent(llm=get_chat_model()),
        storage_service=storage,
        cv_repository=repository,
    )

    ownership = OwnershipRepository(get_job_session_factory())
    turns = ConversationTurnRepository(get_job_session_factory())
    lifecycle = CVDataLifecycleService(
        user_id=user.user_id,
        ownership=ownership,
        turns=turns,
        profiles=repository,
        storage=storage,
        checkpointer=get_conversation_memory().checkpointer,
    )

    return AuthorizedCVProcessingService(
        user_id=user.user_id,
        processing=processing,
        ownership=ownership,
        cv_repository=repository,
        storage=storage,
        lifecycle=lifecycle,
        retention_days=get_settings().cv_retention_days,
    )


def get_authorized_cv_task_service(
    user: CurrentUserDependency,
) -> AuthorizedCVTaskService:
    from app.api.dependencies import (
        get_cv_repository,
        get_job_session_factory,
        get_storage_service,
    )
    from app.repositories.cv_task import CVTaskRepository

    return AuthorizedCVTaskService(
        user_id=user.user_id,
        tasks=CVTaskRepository(get_job_session_factory()),
        storage=get_storage_service(),
        profiles=get_cv_repository(),
        retention_days=get_settings().cv_retention_days,
    )


AuthorizedConversationServiceDependency = Annotated[
    AuthorizedConversationService,
    Depends(get_authorized_conversation_service),
]

AuthorizedCVProcessingServiceDependency = Annotated[
    AuthorizedCVProcessingService,
    Depends(get_authorized_cv_processing_service),
]

AuthorizedCVTaskServiceDependency = Annotated[
    AuthorizedCVTaskService,
    Depends(get_authorized_cv_task_service),
]
