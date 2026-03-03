from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, TypeVar

import httpx
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ApiException, ResponseHandlingException
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    ScoredPoint,
    VectorParams,
)

from semantic_search.config import settings

if TYPE_CHECKING:
    from semantic_search.chunker import Chunk

_UUID_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # URL namespace

_client: QdrantClient | None = None
_PAYLOAD_INDEXES = {
    "artifact_type": PayloadSchemaType.KEYWORD,
    "language": PayloadSchemaType.KEYWORD,
    "file_path": PayloadSchemaType.KEYWORD,
    "chunk_index": PayloadSchemaType.INTEGER,
}
_TRANSIENT_QDRANT_MESSAGES = (
    "10054",
    "broken pipe",
    "connection aborted",
    "connection closed",
    "connection refused",
    "connection reset",
    "server disconnected",
    "temporarily unavailable",
    "timed out",
    "timeout",
)

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

def get_client() -> QdrantClient:
    global _client
    if _client is None:
        if settings.qdrant_url == ":memory:":
            _client = QdrantClient(":memory:")
        else:
            _client = QdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key or None,
            )
    return _client


def _is_retryable_qdrant_error(exc: Exception) -> bool:
    if isinstance(
        exc,
        (
            httpx.HTTPError,
            ResponseHandlingException,
            TimeoutError,
            ConnectionError,
            ConnectionResetError,
        ),
    ):
        return True
    if isinstance(exc, ApiException) and getattr(exc, "status", None) in {408, 429, 500, 502, 503, 504}:
        return True

    message = str(exc).lower()
    return any(marker in message for marker in _TRANSIENT_QDRANT_MESSAGES)


def _is_existing_payload_index_error(exc: Exception) -> bool:
    if isinstance(exc, ApiException) and getattr(exc, "status", None) == 409:
        return True

    message = str(exc).lower()
    return "already exists" in message and "index" in message


def _retry_qdrant(operation: Callable[[], T], *, action: str) -> T:
    attempts = max(settings.qdrant_retry_attempts, 1)
    backoff_seconds = max(settings.qdrant_retry_backoff_seconds, 0.0)

    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as exc:
            if attempt >= attempts or not _is_retryable_qdrant_error(exc):
                raise RuntimeError(f"Qdrant {action} failed: {exc}") from exc
            if backoff_seconds:
                time.sleep(backoff_seconds * (2 ** (attempt - 1)))

    raise RuntimeError(f"Qdrant {action} failed without returning a result")


def _ensure_payload_indexes(client: QdrantClient, collection_name: str) -> None:
    collection_info = _retry_qdrant(
        lambda: client.get_collection(collection_name),
        action=f"collection inspection for '{collection_name}'",
    )
    payload_schema = getattr(collection_info, "payload_schema", {}) or {}

    for field, schema in _PAYLOAD_INDEXES.items():
        if field in payload_schema:
            continue
        try:
            _retry_qdrant(
                lambda field=field, schema=schema: client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field,
                    field_schema=schema,
                ),
                action=f"payload index creation for '{collection_name}.{field}'",
            )
        except Exception as exc:
            root_exc = exc.__cause__ if isinstance(exc, RuntimeError) and exc.__cause__ else exc
            if isinstance(root_exc, Exception) and _is_existing_payload_index_error(root_exc):
                continue
            raise


# ---------------------------------------------------------------------------
# Collection management
# ---------------------------------------------------------------------------

def ensure_collection(collection_name: str, vector_size: int) -> None:
    """Create collection and payload indexes if they do not exist."""
    client = get_client()
    existing = {
        c.name
        for c in _retry_qdrant(
            lambda: client.get_collections().collections,
            action="collection listing",
        )
    }

    if collection_name not in existing:
        _retry_qdrant(
            lambda: client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            ),
            action=f"collection creation for '{collection_name}'",
        )

    _ensure_payload_indexes(client, collection_name)


def delete_collection(collection_name: str) -> None:
    """Drop a collection entirely (use before full re-index with new model)."""
    client = get_client()
    _retry_qdrant(
        lambda: client.delete_collection(collection_name),
        action=f"collection deletion for '{collection_name}'",
    )


# ---------------------------------------------------------------------------
# Point ID
# ---------------------------------------------------------------------------

def chunk_uuid(chunk: "Chunk") -> str:
    """Deterministic UUID5 so re-indexing a file upserts rather than duplicates."""
    return str(uuid.uuid5(_UUID_NAMESPACE, f"{chunk.file_path}:{chunk.chunk_index}"))


# ---------------------------------------------------------------------------
# Smart upsert (hash-check)
# ---------------------------------------------------------------------------

def upsert_chunks_smart(
    chunks: list["Chunk"],
    embedder,             # BaseEmbedder — avoid circular import
    collection_name: str,
) -> dict[str, int]:
    """
    Embed and upsert chunks, skipping those whose content_hash is unchanged.

    Returns {"indexed": N, "skipped": M}.
    """
    if not chunks:
        return {"indexed": 0, "skipped": 0}

    client = get_client()
    to_embed: list["Chunk"] = []
    skipped = 0
    existing_hashes: dict[str, str] = {}
    retrieve_batch_size = max(settings.qdrant_retrieve_batch_size, 1)

    point_ids = [chunk_uuid(chunk) for chunk in chunks]
    for i in range(0, len(point_ids), retrieve_batch_size):
        batch_ids = point_ids[i : i + retrieve_batch_size]
        existing = _retry_qdrant(
            lambda batch_ids=batch_ids: client.retrieve(
                collection_name,
                ids=batch_ids,
                with_payload=["content_hash"],
            ),
            action=f"content hash lookup for '{collection_name}'",
        )
        for point in existing:
            payload = point.payload or {}
            content_hash = payload.get("content_hash")
            if content_hash:
                existing_hashes[str(point.id)] = content_hash

    for chunk in chunks:
        point_id = chunk_uuid(chunk)
        if existing_hashes.get(point_id) == chunk.content_hash:
            skipped += 1
            continue
        to_embed.append(chunk)

    if to_embed:
        texts = [f"{c.chunk_heading}\n\n{c.content}" for c in to_embed]
        embeddings = embedder.embed_documents(texts)
        now = datetime.now(UTC).isoformat()
        points = [
            PointStruct(
                id=chunk_uuid(chunk),
                vector=embedding,
                payload={**chunk.to_payload(), "indexed_at": now},
            )
            for chunk, embedding in zip(to_embed, embeddings)
        ]
        upsert_batch_size = max(settings.qdrant_upsert_batch_size, 1)
        for i in range(0, len(points), upsert_batch_size):
            batch = points[i : i + upsert_batch_size]
            _retry_qdrant(
                lambda batch=batch: client.upsert(collection_name=collection_name, points=batch),
                action=f"point upsert for '{collection_name}'",
            )

    return {"indexed": len(to_embed), "skipped": skipped}


# ---------------------------------------------------------------------------
# Delete file chunks
# ---------------------------------------------------------------------------

def delete_file_chunks(file_path: str, collection_name: str) -> int:
    """Remove all chunks for a given file path. Returns number of points deleted."""
    client = get_client()
    result = _retry_qdrant(
        lambda: client.delete(
            collection_name=collection_name,
            points_selector=Filter(
                must=[FieldCondition(key="file_path", match=MatchValue(value=file_path))]
            ),
        ),
        action=f"file chunk deletion for '{file_path}' in '{collection_name}'",
    )
    return getattr(result, "deleted_count", 0)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search(
    query_vector: list[float],
    collection_name: str,
    top_k: int = 5,
    artifact_type: str | None = None,
    language: str | None = None,
) -> list[ScoredPoint]:
    client = get_client()

    must_conditions = []
    if artifact_type:
        must_conditions.append(
            FieldCondition(key="artifact_type", match=MatchValue(value=artifact_type))
        )
    if language:
        must_conditions.append(
            FieldCondition(key="language", match=MatchValue(value=language))
        )

    query_filter = Filter(must=must_conditions) if must_conditions else None

    return _retry_qdrant(
        lambda: client.query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        ).points,
        action=f"search in '{collection_name}'",
    )


# ---------------------------------------------------------------------------
# List indexed files
# ---------------------------------------------------------------------------

def list_files(collection_name: str) -> list[dict]:
    """Return a deduplicated list of indexed files with metadata."""
    client = get_client()
    file_map: dict[str, dict] = {}
    offset = None

    while True:
        result, next_offset = _retry_qdrant(
            lambda offset=offset: client.scroll(
                collection_name=collection_name,
                with_payload=True,
                limit=256,
                offset=offset,
            ),
            action=f"file listing in '{collection_name}'",
        )
        for point in result:
            p = point.payload or {}
            fp = p.get("file_path", "")
            if fp not in file_map:
                file_map[fp] = {
                    "file_path": fp,
                    "artifact_type": p.get("artifact_type"),
                    "language": p.get("language", ""),
                    "chunk_count": 0,
                    "indexed_at": p.get("indexed_at"),
                    "last_modified": p.get("last_modified", ""),
                }
            file_map[fp]["chunk_count"] += 1

        if next_offset is None:
            break
        offset = next_offset

    return sorted(file_map.values(), key=lambda x: x["file_path"])


# ---------------------------------------------------------------------------
# Get specific chunk
# ---------------------------------------------------------------------------

def get_chunk(file_path: str, chunk_index: int, collection_name: str) -> dict | None:
    client = get_client()
    results, _ = _retry_qdrant(
        lambda: client.scroll(
            collection_name=collection_name,
            scroll_filter=Filter(
                must=[
                    FieldCondition(key="file_path", match=MatchValue(value=file_path)),
                    FieldCondition(key="chunk_index", match=MatchValue(value=chunk_index)),
                ]
            ),
            limit=1,
            with_payload=True,
        ),
        action=f"chunk lookup for '{file_path}#{chunk_index}' in '{collection_name}'",
    )
    return results[0].payload if results else None
