import asyncio

from langchain_core.embeddings import Embeddings
from sentence_transformers import SentenceTransformer

class BgeM3Embeddings(Embeddings):
    def __init__(
        self,
        *,
        model_name: str,
        device: str,
        batch_size: int,
        max_length: int,
        cache_folder: str,
        expected_dimensions: int,
    ) -> None:
        self._batch_size = batch_size
        self._async_lock = asyncio.Lock()

        self._model = SentenceTransformer(
            model_name,
            device=device,
            cache_folder=cache_folder
        )

        self._model.max_seq_length = max_length

        actual_dimensions = self._model.get_embedding_dimension()

        if actual_dimensions != expected_dimensions:
            raise ValueError(
                "Embedding dimension mismatch:"
                f"expected {expected_dimensions}"
                f"received {actual_dimensions}."
            )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        normalized_texts = [text.strip() for text in texts]

        if not normalized_texts:
            return []

        if any(not text for text in normalized_texts):
            raise ValueError("Embedding input must not be empty.")

        vectors = self._model.encode(
            normalized_texts,
            batch_size=self._batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )

        return vectors.astype("float32").tolist()

    def embed_query(self, text: str) -> list[float]:
        vectors = self.embed_documents([text])

        return vectors[0]

    async def aembed_documents(self, texts: list[str],) -> list[list[float]]:
        async with self._async_lock:
            return await asyncio.to_thread(
                self.embed_documents,
                texts,
            )

    async def aembed_query(self, text: str) -> list[float]:
        async with self._async_lock:
            return await asyncio.to_thread(self.embed_query, text)