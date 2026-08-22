from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from langchain_core.language_models.chat_models import BaseChatModel

from app.agents import CVParserAgent
from app.llm import LLMFactory
from app.core.config import get_settings

from app.repositories.cv import CVRepository, LocalJsonCVRepository
from app.services.conversation import ConversationIntentAnalyzer, ConservationService
from app.services.cv_ingestion import CVIngestionService
from app.services.cv_processing import CVProcessingService
from app.services.pdf import PdfInspector, PdfOcrExtractor, NativePdfTextExtractor, PdfTextMerger
from app.services.storage import LocalStorageService, StorageService


@lru_cache
def get_storage_service() -> StorageService:
    return LocalStorageService(get_settings())

@lru_cache
def get_cv_repository() -> CVRepository:
    return LocalJsonCVRepository(get_settings())

@lru_cache
def get_pdf_inspector() -> PdfInspector:
    return PdfInspector(get_settings())

@lru_cache
def get_native_pdf_text_extractor() -> NativePdfTextExtractor:
    return NativePdfTextExtractor(get_settings())

@lru_cache
def get_pdf_ocr_extractor() -> PdfOcrExtractor:
    return PdfOcrExtractor(get_settings())

@lru_cache
def get_pdf_text_merger() -> PdfTextMerger:
    return PdfTextMerger()

@lru_cache
def get_chat_model() -> BaseChatModel:
    return LLMFactory.create_chat_model(get_settings())

def get_cv_parser_agent(llm: BaseChatModel = Depends(get_chat_model)) -> CVParserAgent:
    return CVParserAgent(llm=llm, settings=get_settings())

def get_cv_ingestion_service(
    storage_service: StorageService = Depends(get_storage_service),
    pdf_inspector: PdfInspector = Depends(get_pdf_inspector),
    text_extractor: NativePdfTextExtractor = Depends(get_native_pdf_text_extractor),
    ocr_extractor: PdfOcrExtractor = Depends(get_pdf_ocr_extractor),
    text_merger: PdfTextMerger = Depends(get_pdf_text_merger),
) -> CVIngestionService:
    return CVIngestionService(
        storage=storage_service,
        pdf_inspector=pdf_inspector,
        text_extractor=text_extractor,
        ocr_extractor=ocr_extractor,
        text_merger=text_merger,
    )

def get_cv_processing_service(
        ingestion_service: CVIngestionService = Depends(get_cv_ingestion_service),
        parser_agent: CVParserAgent = Depends(get_cv_parser_agent),
        storage_service: StorageService = Depends(get_storage_service),
        cv_repository: CVRepository = Depends(get_cv_repository),
) -> CVProcessingService:
    return CVProcessingService(
        ingestion_service=ingestion_service,
        parser_agent=parser_agent,
        storage_service=storage_service,
        cv_repository=cv_repository,
    )

CVIngestionServiceDependency = Annotated[
    CVIngestionService,
    Depends(get_cv_ingestion_service),
]

CVProcessingServiceDependency = Annotated[
    CVProcessingService,
    Depends(get_cv_processing_service),
]

ChatModelDependency = Annotated[
    BaseChatModel,
    Depends(get_chat_model)
]

def get_conversation_intent_analyzer(llm: ChatModelDependency) -> ConversationIntentAnalyzer:
    return ConversationIntentAnalyzer(llm=llm)

ConversationIntentAnalyzerDependency = Annotated[
    ConversationIntentAnalyzer,
    Depends(get_conversation_intent_analyzer)
]

def get_conversation_service(
    analyzer: ConversationIntentAnalyzerDependency,
    cv_repository: CVRepository = Depends(get_cv_repository)
) -> ConservationService:
    return ConservationService(
        analyzer=analyzer,
        cv_repository=cv_repository,
    )

ConservationServiceDependency = Annotated[
    ConservationService,
    Depends(get_conversation_service)
]