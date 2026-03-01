from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from qdrant_client import QdrantClient
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


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

def get_client() -> QdrantClient:
    global _client
    if _client is None:
        if settings.qdrant_url == ":memory:":
            _client = QdrantClient(":memory:")
        else:
            _client = QdrantClient(url=settings.qdrant_url)
    return _client


# ---------------------------------------------------------------------------
# Collection management
# ---------------------------------------------------------------------------

def ensure_collection(collection_name: str, vector_size: int) -> None:
    """Create collection and payload indexes if they do not exist."""
    client = get_client()
    existing = {c.name for c in client.get_collections().collections}

    if collection_name not in existing:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
        for field, schema in [
            ("artifact_type", PayloadSchemaType.KEYWORD),
            ("language", PayloadSchemaType.KEYWORD),
            ("file_path", PayloadSchemaType.KEYWORD),
        ]:
            client.create_payload_index(
                collection_name=collection_name,
                field_name=field,
                field_schema=schema,
            )


def delete_collection(collection_name: str) -> None:
    """Drop a collection entirely (use before full re-index with new model)."""
    client = get_client()
    client.delete_collection(collection_name)


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
    client = get_client()
    to_embed: list["Chunk"] = []
    skipped = 0

    for chunk in chunks:
        point_id = chunk_uuid(chunk)
        existing = client.retrieve(
            collection_name,
            ids=[point_id],
            with_payload=["content_hash"],
        )
        if existing and existing[0].payload.get("content_hash") == chunk.content_hash:
            skipped += 1
        else:
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
        client.upsert(collection_name=collection_name, points=points)

    return {"indexed": len(to_embed), "skipped": skipped}


# ---------------------------------------------------------------------------
# Delete file chunks
# ---------------------------------------------------------------------------

def delete_file_chunks(file_path: str, collection_name: str) -> int:
    """Remove all chunks for a given file path. Returns number of points deleted."""
    client = get_client()
    result = client.delete(
        collection_name=collection_name,
        points_selector=Filter(
            must=[FieldCondition(key="file_path", match=MatchValue(value=file_path))]
        ),
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

    return client.query_points(
        collection_name=collection_name,
        query=query_vector,
        limit=top_k,
        query_filter=query_filter,
        with_payload=True,
    ).points


# ---------------------------------------------------------------------------
# List indexed files
# ---------------------------------------------------------------------------

def list_files(collection_name: str) -> list[dict]:
    """Return a deduplicated list of indexed files with metadata."""
    client = get_client()
    file_map: dict[str, dict] = {}
    offset = None

    while True:
        result, next_offset = client.scroll(
            collection_name=collection_name,
            with_payload=True,
            limit=256,
            offset=offset,
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
    results, _ = client.scroll(
        collection_name=collection_name,
        scroll_filter=Filter(
            must=[
                FieldCondition(key="file_path", match=MatchValue(value=file_path)),
                FieldCondition(key="chunk_index", match=MatchValue(value=chunk_index)),
            ]
        ),
        limit=1,
        with_payload=True,
    )
    return results[0].payload if results else None
