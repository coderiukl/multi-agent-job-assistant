from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request

from app.api.auth_dependencies import CurrentUserDependency
from app.core.config import get_settings
from app.core.rate_limit import (
    RateLimitExceededException,
    SlidingWindowRateLimiter,
)
from app.schemas.auth import UserData


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@lru_cache
def get_job_search_rate_limiter() -> SlidingWindowRateLimiter:
    return SlidingWindowRateLimiter(
        limit=get_settings().job_search_rate_limit_per_minute,
        window_seconds=60,
    )


@lru_cache
def get_login_email_failure_limiter() -> SlidingWindowRateLimiter:
    settings = get_settings()
    return SlidingWindowRateLimiter(
        limit=settings.auth_login_max_failures_per_email,
        window_seconds=settings.auth_login_failure_window_seconds,
    )


@lru_cache
def get_login_ip_failure_limiter() -> SlidingWindowRateLimiter:
    settings = get_settings()
    return SlidingWindowRateLimiter(
        limit=settings.auth_login_max_failures_per_ip,
        window_seconds=settings.auth_login_failure_window_seconds,
    )


@lru_cache
def get_register_rate_limiter() -> SlidingWindowRateLimiter:
    return SlidingWindowRateLimiter(
        limit=get_settings().auth_register_rate_limit_per_hour,
        window_seconds=3600,
    )


def reset_rate_limiters() -> None:
    """Clear every in-process limiter (used by tests and admin tooling)."""
    for factory in (
        get_job_search_rate_limiter,
        get_login_email_failure_limiter,
        get_login_ip_failure_limiter,
        get_register_rate_limiter,
    ):
        factory().reset()


async def require_job_search_quota(
    user: CurrentUserDependency,
) -> UserData:
    wait = get_job_search_rate_limiter().check_and_hit(str(user.user_id))
    if wait:
        raise RateLimitExceededException(
            retry_after_seconds=wait,
            message="Too many job searches. Please wait and try again.",
        )
    return user


JobSearchUserDependency = Annotated[
    UserData,
    Depends(require_job_search_quota),
]


async def require_register_quota(request: Request) -> None:
    wait = get_register_rate_limiter().check_and_hit(client_ip(request))
    if wait:
        raise RateLimitExceededException(
            retry_after_seconds=wait,
            message="Too many registration attempts. Please try again later.",
        )


class LoginThrottle:
    """Counts failed logins per e-mail and per client IP.

    Only failures are counted, so a legitimate user is never locked out by
    their own successful logins; a success clears the e-mail counter.
    """

    def __init__(self, request: Request) -> None:
        self._ip = client_ip(request)
        self._email_limiter = get_login_email_failure_limiter()
        self._ip_limiter = get_login_ip_failure_limiter()

    @staticmethod
    def _email_key(email: str) -> str:
        return email.strip().lower()[:254]

    def ensure_allowed(self, email: str) -> None:
        wait = max(
            self._email_limiter.retry_after(self._email_key(email)),
            self._ip_limiter.retry_after(self._ip),
        )
        if wait:
            raise RateLimitExceededException(
                retry_after_seconds=wait,
                message="Too many failed login attempts. Please try again later.",
            )

    def record_failure(self, email: str) -> None:
        self._email_limiter.hit(self._email_key(email))
        self._ip_limiter.hit(self._ip)

    def record_success(self, email: str) -> None:
        self._email_limiter.reset(self._email_key(email))


LoginThrottleDependency = Annotated[LoginThrottle, Depends(LoginThrottle)]
