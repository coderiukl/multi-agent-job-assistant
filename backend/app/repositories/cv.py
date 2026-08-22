import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Protocol

import aiofiles
from pydantic import ValidationError

from app.core.config import Settings
from app.core.exceptions import StorageException
from app.schemas.cv_profile import CVProfile

logger = logging.getLogger(__name__)

CV_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")

class CVRepository(Protocol):
    async def save(self, cv_id: str, profile: CVProfile) -> None:
        ...

    async def get(self, cv_id: str) -> CVProfile | None:
        ...

    async def delete(self, cv_id: str) -> None:
        ...

class LocalJsonCVRepository:
    def __init__(self, settings: Settings) -> None:
        self._profile_dir = settings.upload_dir / "profiles"
        self._profile_dir.mkdir(parents=True, exist_ok=True)

    async def save(self, cv_id: str, profile: CVProfile) -> None:
        if not self._is_valid_cv_id(cv_id):
            raise StorageException(
                message="The CV identifier is invalid.",
            )
        
        profile_path = self._build_profile_path(cv_id)
        temporary_path = profile_path.with_suffix(".json.part")

        try:
            payload = profile.model_dump_json(indent=2)

            async with aiofiles.open(
                temporary_path,
                mode='w',
                encoding='utf-8'
            ) as output:
                await output.write(payload)

            await asyncio.to_thread(os.replace, temporary_path, profile_path)

            logger.info(
                "CV profile persisted",
                extra={"cv_id": cv_id},
            )

        except OSError as exc:
            logger.exception(
                "Failed to persist CV profile",
                extra={"cv_id": cv_id},
            )

            raise StorageException(
                message="The CV profile could not be stored.",
            ) from exc

        finally:
            try:
                await asyncio.to_thread(
                    temporary_path.unlink,
                    missing_ok=True,
                )
            except OSError:
                logger.warning(
                    "Could not remove temporary CV profile",
                    extra={"cv_id": cv_id},
                    exc_info=True,
                )

    async def get(self, cv_id: str) -> CVProfile | None:
        if not self._is_valid_cv_id(cv_id):
            return None

        profile_path = self._build_profile_path(cv_id)

        try:
            async with aiofiles.open(
                profile_path,
                mode="r",
                encoding="utf-8",
            ) as input_file:
                payload = await input_file.read()

            return CVProfile.model_validate_json(payload)

        except FileNotFoundError:
            return None

        except (OSError, ValidationError) as exc:
            logger.exception(
                "Failed to read CV profile",
                extra={"cv_id": cv_id},
            )

            raise StorageException(
                message="The stored CV profile could not be read.",
            ) from exc

    async def delete(self, cv_id: str) -> None:
        if not self._is_valid_cv_id(cv_id):
            return

        profile_path = self._build_profile_path(cv_id)

        try:
            await asyncio.to_thread(
                profile_path.unlink,
                missing_ok=True,
            )

            logger.info(
                "CV profile deleted",
                extra={"cv_id": cv_id},
            )

        except OSError as exc:
            logger.exception(
                "Failed to delete CV profile",
                extra={"cv_id": cv_id},
            )

            raise StorageException(
                message="The stored CV profile could not be deleted.",
            ) from exc

    def _build_profile_path(self, cv_id: str) -> Path:
        return self._profile_dir / f"{cv_id}.json"

    @staticmethod
    def _is_valid_cv_id(cv_id: str) -> bool:
        if not cv_id:
            return False

        return "/" not in cv_id and "\\" not in cv_id