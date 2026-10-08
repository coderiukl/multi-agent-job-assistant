import os
import socket
from uuid import uuid4

from app.agents import CVParserAgent
from app.core.config import get_settings
from app.database import create_job_database_engine, create_job_session_factory
from app.llm import LLMFactory
from app.repositories.cv import LocalJsonCVRepository
from app.repositories.cv_task import CVTaskRepository
from app.services.cv_ingestion import CVIngestionService
from app.services.cv_processing import CVProcessingService
from app.services.cv_tasks import CVTaskWorker
from app.services.pdf import (
    NativePdfTextExtractor,
    PdfInspector,
    PdfOcrExtractor,
    PdfTextMerger,
)
from app.services.storage import LocalStorageService


async def run_cv_worker(*, once: bool = False) -> None:
    settings = get_settings()
    engine = create_job_database_engine(settings)
    session_factory = create_job_session_factory(engine)
    storage = LocalStorageService(settings)
    profiles = LocalJsonCVRepository(settings)
    ingestion = CVIngestionService(
        storage=storage,
        pdf_inspector=PdfInspector(settings),
        text_extractor=NativePdfTextExtractor(settings),
        ocr_extractor=PdfOcrExtractor(settings),
        text_merger=PdfTextMerger(),
    )
    processing = CVProcessingService(
        ingestion_service=ingestion,
        parser_agent=CVParserAgent(
            llm=LLMFactory.create_chat_model(settings),
            settings=settings,
        ),
        storage_service=storage,
        cv_repository=profiles,
    )
    worker = CVTaskWorker(
        worker_id=(f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"),
        tasks=CVTaskRepository(session_factory),
        processing=processing,
        upload_dir=settings.upload_dir,
        lease_seconds=settings.cv_task_lease_seconds,
        max_attempts=settings.cv_task_max_attempts,
        poll_seconds=settings.cv_worker_poll_seconds,
    )
    try:
        if once:
            await worker.run_once()
        else:
            await worker.run_forever()
    finally:
        await engine.dispose()
