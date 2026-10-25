from importlib import import_module
from typing import Any

__all__ = [
    "CareerAdviceService",
    "CoverLetterService",
    "CVAnalysisService",
    "HybridJobSearchService",
    "JobCrawlingService",
    "JobMatchingService",
]

_SERVICE_MODULES = {
    "CareerAdviceService": "app.services.career_advice",
    "CoverLetterService": "app.services.cover_letter",
    "CVAnalysisService": "app.services.cv_analysis",
    "HybridJobSearchService": "app.services.job_search",
    "JobCrawlingService": "app.services.job_crawling",
    "JobMatchingService": "app.services.job_matching",
}


def __getattr__(name: str) -> Any:
    """Keep package exports without importing every service eagerly."""

    try:
        module_name = _SERVICE_MODULES[name]
    except KeyError as exc:
        raise AttributeError(name) from exc

    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value
