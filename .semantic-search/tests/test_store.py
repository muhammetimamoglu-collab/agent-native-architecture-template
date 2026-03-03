from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from qdrant_client.models import PayloadSchemaType

from semantic_search import store


class DummyChunk:
    def __init__(self, file_path: str, chunk_index: int, content: str) -> None:
        self.file_path = file_path
        self.chunk_index = chunk_index
        self.chunk_heading = f"Chunk {chunk_index}"
        self.content = content
        self.artifact_type = "flow"
        self.language = ""
        self.line_start = 1
        self.line_end = 2
        self.last_modified = ""

    @property
    def content_hash(self) -> str:
        return f"hash:{self.content}"

    def to_payload(self) -> dict:
        return {
            "file_path": self.file_path,
            "artifact_type": self.artifact_type,
            "language": self.language,
            "chunk_index": self.chunk_index,
            "chunk_heading": self.chunk_heading,
            "content": self.content,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "content_hash": self.content_hash,
            "last_modified": self.last_modified,
        }


class StoreTests(unittest.TestCase):
    def test_get_client_uses_configured_request_timeout(self) -> None:
        with (
            mock.patch.object(store, "_client", None),
            mock.patch.object(store.settings, "qdrant_url", "https://example.qdrant.io"),
            mock.patch.object(store.settings, "qdrant_api_key", "secret"),
            mock.patch.object(store.settings, "qdrant_request_timeout_seconds", 17),
            mock.patch("semantic_search.store.QdrantClient") as client_cls,
        ):
            store.get_client()

        client_cls.assert_called_once_with(
            url="https://example.qdrant.io",
            api_key="secret",
            timeout=17,
        )

    def test_ensure_collection_migrates_missing_chunk_index(self) -> None:
        client = mock.Mock()
        client.get_collections.return_value = SimpleNamespace(
            collections=[SimpleNamespace(name="demo_docs")]
        )
        client.get_collection.return_value = SimpleNamespace(
            payload_schema={
                "artifact_type": object(),
                "language": object(),
                "file_path": object(),
            }
        )

        with (
            mock.patch("semantic_search.store.get_client", return_value=client),
            mock.patch.object(store.settings, "qdrant_request_timeout_seconds", 11),
        ):
            store.ensure_collection("demo_docs", 1024)

        client.create_collection.assert_not_called()
        client.create_payload_index.assert_called_once_with(
            collection_name="demo_docs",
            field_name="chunk_index",
            field_schema=PayloadSchemaType.INTEGER,
            timeout=11,
        )

    def test_upsert_chunks_smart_batches_retrieve_and_upsert(self) -> None:
        chunks = [
            DummyChunk("docs/a.md", 0, "same"),
            DummyChunk("docs/a.md", 1, "new-1"),
            DummyChunk("docs/b.md", 0, "new-2"),
        ]
        existing = SimpleNamespace(
            id=store.chunk_uuid(chunks[0]),
            payload={"content_hash": chunks[0].content_hash},
        )
        client = mock.Mock()
        client.retrieve.side_effect = [[existing], []]
        embedder = mock.Mock()
        embedder.embed_documents.return_value = [[0.1], [0.2]]

        with (
            mock.patch("semantic_search.store.get_client", return_value=client),
            mock.patch.object(store.settings, "qdrant_retrieve_batch_size", 2),
            mock.patch.object(store.settings, "qdrant_upsert_batch_size", 1),
            mock.patch.object(store.settings, "qdrant_request_timeout_seconds", 9),
        ):
            result = store.upsert_chunks_smart(chunks, embedder, "demo_docs")

        self.assertEqual(result, {"indexed": 2, "skipped": 1})
        self.assertEqual(client.retrieve.call_count, 2)
        self.assertEqual(client.upsert.call_count, 2)
        embedder.embed_documents.assert_called_once()
        self.assertTrue(all(call.kwargs["timeout"] == 9 for call in client.retrieve.call_args_list))
        self.assertTrue(all(call.kwargs["timeout"] == 9 for call in client.upsert.call_args_list))


if __name__ == "__main__":
    unittest.main()
