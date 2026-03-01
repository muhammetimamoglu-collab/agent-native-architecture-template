from __future__ import annotations

import voyageai

from semantic_search.config import settings
from semantic_search.embedders import BaseEmbedder

_BATCH_SIZE = 128   # VoyageAI maximum texts per request
_MODEL = "voyage-code-3"
_VECTOR_SIZE = 1024


class VoyageEmbedder(BaseEmbedder):
    """
    Embedding backend using VoyageAI voyage-code-3.

    Uses asymmetric input types:
      - "document" for indexing (embed_documents)
      - "query"    for retrieval (embed_query)

    This asymmetry improves recall for code and structured text retrieval.
    """

    def __init__(self) -> None:
        if not settings.voyage_api_key:
            raise EnvironmentError(
                "VOYAGE_API_KEY is not set. "
                "Add it to .semantic-search/.env or set EMBEDDER_TYPE=local."
            )
        self._client = voyageai.Client(api_key=settings.voyage_api_key)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), _BATCH_SIZE):
            batch = texts[i : i + _BATCH_SIZE]
            result = self._client.embed(batch, model=_MODEL, input_type="document")
            all_embeddings.extend(result.embeddings)
        return all_embeddings

    def embed_query(self, query: str) -> list[float]:
        result = self._client.embed([query], model=_MODEL, input_type="query")
        return result.embeddings[0]

    @property
    def vector_size(self) -> int:
        return _VECTOR_SIZE
