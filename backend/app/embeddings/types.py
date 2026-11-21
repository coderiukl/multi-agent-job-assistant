from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class SparseEmbedding:
    """Lexical weights of BGE-M3: one (token id, weight) pair per kept token."""

    indices: list[int]
    values: list[float]


@dataclass(frozen=True)
class HybridEmbedding:
    dense: list[float]
    sparse: SparseEmbedding


@runtime_checkable
class HybridEmbeddings(Protocol):
    """Embeddings that also produce a sparse (lexical) vector per text."""

    async def aembed_hybrid(self, texts: list[str]) -> list[HybridEmbedding]: ...


def supports_sparse(embeddings: Any) -> bool:
    """True when ``embeddings`` can produce sparse vectors right now."""
    return isinstance(embeddings, HybridEmbeddings) and bool(
        getattr(embeddings, "sparse_enabled", True)
    )
