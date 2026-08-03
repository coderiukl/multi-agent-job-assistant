from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

class PageType(StrEnum):
    DIGITAL_TEXT = "digital_text"
    SCANNED = "scanned"
    HYBRID = "hybrid"
    EMPTY = "empty"
    UNKNOWN = "unknown"

class DocumentBlockSource(StrEnum): 
    PDF_TEXT = "pdf_text"
    OCR_FULL_PAGE = "ocr_full_page"
    OCR_IMAGE_REGION = "ocr_image_region"

class DocumentBlockType(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    TABLE = "table"
    LINE = "line"
    UNKNOWN = "unknown"

class CVProcessingStatus(StrEnum):
    UPLOADED = "uploaded"
    VALIDATING = "validating"
    QUEUED = "queued"
    INSPECTING = "inspecting"
    EXTRACTING_TEXT = "extracting_text"
    RUNNING_OCR = "running_ocr"
    RECONSTRUCTING_LAYOUT = "reconstructing_layout"
    DETECTING_SECTIONS = "detecting_sections"
    PARSING = "parsing"
    VALIDATING_RESULT = "validating_result"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"

class CVSectionType(StrEnum):
    PERSONAL_INFORMATION = "personal_information"
    SUMMARY = "summary"
    OBJECTIVE = "objective"
    EDUCATION = "education"
    EXPERIENCE = "experience"
    PROJECTS = "projects"
    SKILLS = "skills"
    CERTIFICATIONS = "certifications"
    LANGUAGES = "languages"
    AWARDS = "awards"
    ACTIVITIES = "activities"
    PUBLICATIONS = "publications"
    REFERENCES = "references"
    UNKNOWN = "unknown"

class ConfidenceLevel(StrEnum):
    ACCEPTED = "accepted"
    ACCEPTED_WITH_WARNING = "accepted_with_warning"
    HUMAN_REVIEW_REQUIRED = "human_review_required"

class Evidence(BaseModel):
    page_number: int = Field(ge=1)
    block_ids: list[str] = Field(default_factory=list)
    text: str = Field(min_length=1)

class ExtractedValue(BaseModel):
    value: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence: list[Evidence] = Field(default_factory=list)

class EducationItem(BaseModel):
    institution: ExtractedValue = Field(default_factory=ExtractedValue)
    degree: ExtractedValue = Field(default_factory=ExtractedValue)
    major: ExtractedValue = Field(default_factory=ExtractedValue)
    start_date: ExtractedValue = Field(default_factory=ExtractedValue)
    end_date: ExtractedValue = Field(default_factory=ExtractedValue)
    gpa: ExtractedValue = Field(default_factory=ExtractedValue)

class ExperienceItem(BaseModel):
    company: ExtractedValue = Field(default_factory=ExtractedValue)
    job_title: ExtractedValue = Field(default_factory=ExtractedValue)
    start_date: ExtractedValue = Field(default_factory=ExtractedValue)
    end_date: ExtractedValue = Field(default_factory=ExtractedValue)
    location: ExtractedValue = Field(default_factory=ExtractedValue)
    responsibilities: list[ExtractedValue] = Field(default_factory=list)

class ProjectItem(BaseModel):
    name: ExtractedValue = Field(default_factory=ExtractedValue)
    role: ExtractedValue = Field(default_factory=ExtractedValue)
    start_date: ExtractedValue = Field(default_factory=ExtractedValue)
    end_date: ExtractedValue = Field(default_factory=ExtractedValue)
    technologies: list[ExtractedValue] = Field(default_factory=list)
    descriptions: list[ExtractedValue] = Field(default_factory=list)

class SkillGroup(BaseModel):
    programming_languages: list[ExtractedValue] = Field(default_factory=list)
    frameworks: list[ExtractedValue] = Field(default_factory=list)
    databases: list[ExtractedValue] = Field(default_factory=list)
    devops: list[ExtractedValue] = Field(default_factory=list)
    machine_learning: list[ExtractedValue] = Field(default_factory=list)
    tools: list[ExtractedValue] = Field(default_factory=list)
    other: list[ExtractedValue] = Field(default_factory=list)

class CVProfile(BaseModel):
    full_name: ExtractedValue = Field(default_factory=ExtractedValue)
    email: ExtractedValue = Field(default_factory=ExtractedValue)
    phone: ExtractedValue = Field(default_factory=ExtractedValue)
    location: ExtractedValue = Field(default_factory=ExtractedValue)
    summary: ExtractedValue = Field(default_factory=ExtractedValue)
    education: list[EducationItem] = Field(default_factory=list)
    experience: list[ExperienceItem] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)
    skills: SkillGroup = Field(default_factory=SkillGroup)
    certifications: list[ExtractedValue] = Field(default_factory=list)
    languages: list[ExtractedValue] = Field(default_factory=list)

BBox = tuple[float, float, float, float]

class DocumentBlock(BaseModel):
    block_id: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    source: DocumentBlockSource
    block_type: DocumentBlockType = DocumentBlockType.TEXT
    text: str = ""
    raw_text: str = ""
    normalized_text: str | None = None
    bbox: BBox
    confidence: float = Field(ge=0.0, le=1.0)
    font_name: str | None = None
    font_size: float | None = Field(default=None, ge=0.0)
    is_bold: bool = False
    is_italic: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, bbox: BBox) -> BBox:
        x0, y0, x1, y1 = bbox

        if x1 < x0 or y1 < y0:
            raise ValueError("bbox must be ordered as x0, y0, x1, y1")

        return bbox

class PageAnalysis(BaseModel):
    page_number: int = Field(ge=1)
    width: float = Field(gt=0.0)
    height: float = Field(gt=0.0)
    text_length: int = Field(ge=0)
    text_block_count: int = Field(ge=0)
    image_count: int = Field(ge=0)
    image_coverage: float = Field(ge=0.0, le=1.0)
    text_coverage: float = Field(ge=0.0, le=1.0)
    page_type: PageType
    has_encoding_issues: bool = False

class LayoutReconstruction(BaseModel):
    page_number: int = Field(ge=1)
    column_count: int = Field(ge=0)
    reading_order: list[str] = Field(default_factory=list)

class SectionResult(BaseModel):
    section_type: CVSectionType
    title: str | None = None
    block_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    detection_method: str = Field(min_length=1)

class DeterministicExtractionResult(BaseModel):
    values: dict[str, list[ExtractedValue]] = Field(default_factory=dict)

class ValidationResult(BaseModel):
    is_valid: bool = True
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    fields_for_review: list[str] = Field(default_factory=list)

class FieldConfidence(BaseModel):
    field: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=1.0)
    level: ConfidenceLevel
    signals: dict[str, float | bool | str] = Field(default_factory=dict)

class ProcessingErrorType(StrEnum):
    VALIDATION = "validation"
    PDF_INSPECTION = "pdf_inspection"
    TEXT_EXTRACTION = "text_extraction"
    OCR = "ocr"
    LAYOUT = "layout"
    SECTION_DETECTION = "section_detection"
    PARSING = "parsing"
    RESULT_VALIDATION = "result_validation"
    STORAGE = "storage"
    UNKNOWN = "unknown"

class ProcessingError(BaseModel):
    code: str = Field(min_length=1)
    error_type: ProcessingErrorType
    message: str = Field(min_length=1)
    step: CVProcessingStatus
    retryable: bool = False

class CVProcessingResult(BaseModel):
    status: CVProcessingStatus
    page_analyses: list[PageAnalysis] = Field(default_factory=list)
    raw_blocks: list[DocumentBlock] = Field(default_factory=list)
    normalized_blocks: list[DocumentBlock] = Field(default_factory=list)
    layouts: list[LayoutReconstruction] = Field(default_factory=list)
    sections: list[SectionResult] = Field(default_factory=list)
    deterministic_extraction: DeterministicExtractionResult = Field(
        default_factory=DeterministicExtractionResult,
    )
    profile: CVProfile = Field(default_factory=CVProfile)
    validation: ValidationResult = Field(default_factory=ValidationResult)
    confidence_scores: list[FieldConfidence] = Field(default_factory=list)
    error: ProcessingError | None = None
    pipeline_version: str
    prompt_version: str | None = None
    ocr_engine_version: str | None = None