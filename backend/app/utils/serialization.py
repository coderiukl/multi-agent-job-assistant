from collections.abc import Mapping
from enum import Enum
from typing import Any

from pydantic import BaseModel


def to_json_compatible(value: Any) -> Any:
    """Serialize values from live or restored LangGraph state."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, Mapping):
        return {str(key): to_json_compatible(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [to_json_compatible(item) for item in value]

    return value
