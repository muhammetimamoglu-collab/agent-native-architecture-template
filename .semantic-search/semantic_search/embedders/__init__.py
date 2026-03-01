from __future__ import annotations

from abc import ABC, abstractmethod

from semantic_search.config import settings


class BaseEmbedder(ABC):
    """Common interface for all embedding backends."""

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a list of documents for indexing.
        Use input_type="document" for asymmetric models (e.g. VoyageAI).
        """

    @abstractmethod
    def embed_query(self, query: str) -> list[float]:
        """
        Embed a single search query.
        Use input_type="query" for asymmetric models (e.g. VoyageAI).
        """

    @property
    @abstractmethod
    def vector_size(self) -> int:
        """Dimension of the produced vectors."""


def get_embedder() -> BaseEmbedder:
    """Return the configured embedder instance."""
    t = settings.embedder_type.lower()
    if t == "voyage":
        from semantic_search.embedders.voyage import VoyageEmbedder
        return VoyageEmbedder()
    if t == "local":
        from semantic_search.embedders.local import LocalEmbedder
        return LocalEmbedder()
    raise ValueError(
        f"Unknown EMBEDDER_TYPE '{t}'. Supported values: 'voyage', 'local'."
    )
