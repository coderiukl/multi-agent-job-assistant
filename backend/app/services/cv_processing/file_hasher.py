import hashlib
from pathlib import Path


class FileHasher:
    """Calculate stable SHA-256 hashes for uploaded CV files."""

    chunk_size = 1024 * 1024

    def sha256_bytes(self, content: bytes) -> str:
        digest = hashlib.sha256()
        digest.update(content)
        return digest.hexdigest()

    def sha256_file(self, file_path: Path) -> str:
        digest = hashlib.sha256()

        with file_path.open("rb") as file:
            while chunk := file.read(self.chunk_size):
                digest.update(chunk)

        return digest.hexdigest()