from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True, slots=True)
class StoredFile:
    file_id: str
    path: Path
    original_filename: str
    content_type: str
    size_bytes: int
    