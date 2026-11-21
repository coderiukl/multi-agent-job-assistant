import asyncio
from typing import Any

from langchain_core.embeddings import Embeddings
from sentence_transformers import SentenceTransformer

from app.embeddings.types import HybridEmbedding, SparseEmbedding

SPARSE_HEAD_FILENAME = "sparse_linear.pt"


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
        enable_sparse: bool = True,
    ) -> None:
        self._batch_size = batch_size
        self._async_lock = asyncio.Lock()

        self._model = SentenceTransformer(
            model_name,
            device=device,
            cache_folder=cache_folder,
        )

        self._model.max_seq_length = max_length

        actual_dimensions = self._model.get_embedding_dimension()

        if actual_dimensions != expected_dimensions:
            raise ValueError(
                "Embedding dimension mismatch: "
                f"expected {expected_dimensions}, "
                f"received {actual_dimensions}."
            )

        self._sparse_linear: Any = None
        self._unused_token_ids: set[int] = set()

        if enable_sparse:
            self._load_sparse_head(
                model_name=model_name,
                cache_folder=cache_folder,
                hidden_size=actual_dimensions,
            )

    @property
    def sparse_enabled(self) -> bool:
        return self._sparse_linear is not None

    def _load_sparse_head(
        self,
        *,
        model_name: str,
        cache_folder: str,
        hidden_size: int,
    ) -> None:
        """Load BGE-M3's sparse head (Linear(hidden, 1)) shipped with the model.

        The sparse weight of a token is relu(W . h_token), computed on the same
        last hidden states as the dense CLS vector, so one forward pass yields
        both representations (as in FlagEmbedding's BGEM3FlagModel).
        """
        import torch
        from huggingface_hub import hf_hub_download

        path = hf_hub_download(
            repo_id=model_name,
            filename=SPARSE_HEAD_FILENAME,
            cache_dir=cache_folder,
        )
        linear = torch.nn.Linear(hidden_size, 1)
        linear.load_state_dict(
            torch.load(path, map_location="cpu", weights_only=True)
        )
        self._sparse_linear = linear.to(self._model.device).eval()

        tokenizer = self._model.tokenizer
        self._unused_token_ids = {
            token_id
            for token_id in (
                tokenizer.cls_token_id,
                tokenizer.eos_token_id,
                tokenizer.pad_token_id,
                tokenizer.unk_token_id,
            )
            if token_id is not None
        }

    @staticmethod
    def _normalize_texts(texts: list[str]) -> list[str]:
        normalized_texts = [text.strip() for text in texts]

        if any(not text for text in normalized_texts):
            raise ValueError("Embedding input must not be empty.")

        return normalized_texts

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        normalized_texts = self._normalize_texts(texts)

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

    def embed_hybrid(self, texts: list[str]) -> list[HybridEmbedding]:
        if self._sparse_linear is None:
            raise RuntimeError("The BGE-M3 sparse head is disabled.")

        if not texts:
            return []

        import torch

        normalized_texts = self._normalize_texts(texts)
        results: list[HybridEmbedding] = []

        for start in range(0, len(normalized_texts), self._batch_size):
            batch = normalized_texts[start : start + self._batch_size]
            # sentence-transformers >= 6 renamed tokenize() to preprocess();
            # the features may also carry non-tensor entries.
            preprocess = (
                getattr(self._model, "preprocess", None) or self._model.tokenize
            )
            features = {
                key: (
                    value.to(self._model.device)
                    if isinstance(value, torch.Tensor)
                    else value
                )
                for key, value in preprocess(batch).items()
            }

            with torch.inference_mode():
                output = self._model(features)
                dense = torch.nn.functional.normalize(
                    output["sentence_embedding"],
                    dim=-1,
                )
                weights = torch.relu(
                    self._sparse_linear(output["token_embeddings"])
                ).squeeze(-1)

            dense_rows = dense.float().cpu().tolist()
            input_ids = features["input_ids"].cpu().tolist()
            attention = features["attention_mask"].cpu().tolist()
            weight_rows = weights.float().cpu().tolist()

            for row in range(len(batch)):
                results.append(
                    HybridEmbedding(
                        dense=dense_rows[row],
                        sparse=self._to_sparse(
                            token_ids=input_ids[row],
                            weights=weight_rows[row],
                            attention_mask=attention[row],
                        ),
                    )
                )

        return results

    def _to_sparse(
        self,
        *,
        token_ids: list[int],
        weights: list[float],
        attention_mask: list[int],
    ) -> SparseEmbedding:
        # One weight per distinct token id: the maximum over its occurrences,
        # skipping special tokens and padding (same rule as FlagEmbedding).
        best: dict[int, float] = {}

        for token_id, weight, keep in zip(
            token_ids, weights, attention_mask, strict=True
        ):
            if not keep or token_id in self._unused_token_ids or weight <= 0:
                continue
            if weight > best.get(token_id, 0.0):
                best[token_id] = weight

        return SparseEmbedding(
            indices=list(best),
            values=list(best.values()),
        )

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        async with self._async_lock:
            return await asyncio.to_thread(
                self.embed_documents,
                texts,
            )

    async def aembed_query(self, text: str) -> list[float]:
        async with self._async_lock:
            return await asyncio.to_thread(self.embed_query, text)

    async def aembed_hybrid(self, texts: list[str]) -> list[HybridEmbedding]:
        async with self._async_lock:
            return await asyncio.to_thread(self.embed_hybrid, texts)
