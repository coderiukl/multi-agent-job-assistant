from importlib import import_module
from typing import Any

_EXPORTS = {
    "JobCrawlingService": "app.services.job_crawling",
    "HybridJobSearchService": "app.services.job_search",
    "JobMatchingService": "app.services.job_matching",
    "CVAnalysisService": "app.services.cv_analysis",
    "CareerAdviceService": "app.services.career_advice",
    "CoverLetterService": "app.services.cover_letter",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value
