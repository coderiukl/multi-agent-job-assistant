from langchain_core.embeddings import Embeddings

from app.core.config import Settings
from app.embeddings.bge_m3 import BgeM3Embeddings

class EmbeddingFactory:
    @staticmethod
    def create(settings: Settings) -> Embeddings:
        settings.embedding_cache_dir.mkdir(parents=True, exist_ok=True)

        return BgeM3Embeddings(
            model_name=settings.embedding_model,
            device=settings.embedding_device,
            batch_size=settings.embedding_batch_size,
            max_length=settings.embedding_max_length,
            cache_folder=str(settings.embedding_cache_dir),
            expected_dimensions=settings.embedding_dimensions,
        )