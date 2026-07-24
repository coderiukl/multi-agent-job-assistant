from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Initialize and clean up application resources.

    Future resources:
    - Qdrant client
    - LLM provider
    - LangGraph workflows
    - HTTP clients
    """
    yield


app = FastAPI(
    title="Multi-Agent Job Assistant API",
    version="0.1.0",
    description="API for CV analysis, job matching, and career recommendations.",
    lifespan=lifespan,
)


@app.get("/health", tags=["System"])
async def health_check() -> dict[str, str]:
    return {
        "status": "healthy",
        "service": "multi-agent-job-assistant",
        "version": "0.1.0",
    }
