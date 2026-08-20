from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.core.config import get_settings
from app.services.cv_ingestion import CVIngestionService
from app.services.pdf import PdfInspector, PdfOcrExtractor, NativePdfTextExtractor, PdfTextMerger
from app.services.storage import LocalStorageService, StorageService

from langchain_core.language_models.chat_models import BaseChatModel
from app.agents import CVParserAgent
from app.llm import LLMFactory
from app.services.cv_processing import CVProcessingService


@lru_cache
def get_storage_service() -> StorageService:
    return LocalStorageService(get_settings())

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
) -> CVProcessingService:
    return CVProcessingService(
        ingestion_service=ingestion_service,
        parser_agent=parser_agent,
        storage_service=storage_service
    )

CVIngestionServiceDependency = Annotated[
    CVIngestionService,
    Depends(get_cv_ingestion_service),
]

CVProcessingServiceDependency = Annotated[
    CVProcessingService,
    Depends(get_cv_processing_service),
]
