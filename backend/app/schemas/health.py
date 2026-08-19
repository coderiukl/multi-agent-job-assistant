from typing import Literal

from pydantic import BaseModel


class HealthData(BaseModel):
    status: Literal["healthy"]
    service: str
    version: str
    environment: Literal[
        "development",
        "testing",
        "production",
    ]