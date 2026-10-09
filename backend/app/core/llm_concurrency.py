import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class LLMConcurrencyLimiter:
    """Process-wide limiter shared by all matching requests."""

    def __init__(self, limit: int) -> None:
        self._semaphore = asyncio.Semaphore(limit)

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        async with self._semaphore:
            yield
