from __future__ import annotations

import httpx

from semantic_search.config import settings
from semantic_search.embedders import BaseEmbedder

_MODEL_DIMS: dict[str, int] = {
    "nomic-embed-text": 768,
    "mxbai-embed-large": 1024,
}

_BATCH_SIZE = 32   # Conservative Ollama batch size


class LocalEmbedder(BaseEmbedder):
    """
    Embedding backend using Ollama (offline, no API key required).

    Supported models (set LOCAL_MODEL_NAME in .env):
      - nomic-embed-text  — 768-dim, fast, good general retrieval
      - mxbai-embed-large — 1024-dim, higher quality (same dim as voyage-code-3)

    Install a model: ollama pull nomic-embed-text
                 OR  ollama pull mxbai-embed-large

    WARNING: If you switch to a model with a different vector dimension,
    you must delete the Qdrant collection and run a full re-index:
      index-docs full --force
      index-code full --force
    """

    def __init__(self) -> None:
        self._model = settings.local_model_name
        self._url = settings.ollama_url.rstrip("/") + "/api/embeddings"
        self._client = httpx.Client(timeout=60.0)

        if self._model not in _MODEL_DIMS:
            supported = ", ".join(_MODEL_DIMS)
            raise ValueError(
                f"LOCAL_MODEL_NAME '{self._model}' is not supported. "
                f"Choose one of: {supported}"
            )

    def _embed_one(self, text: str) -> list[float]:
        response = self._client.post(
            self._url,
            json={"model": self._model, "prompt": text},
        )
        response.raise_for_status()
        return response.json()["embedding"]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        embeddings: list[list[float]] = []
        for i in range(0, len(texts), _BATCH_SIZE):
            for text in texts[i : i + _BATCH_SIZE]:
                embeddings.append(self._embed_one(text))
        return embeddings

    def embed_query(self, query: str) -> list[float]:
        return self._embed_one(query)

    @property
    def vector_size(self) -> int:
        return _MODEL_DIMS[self._model]
