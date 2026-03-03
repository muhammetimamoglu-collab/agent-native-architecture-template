from __future__ import annotations

import asyncio
import json
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from semantic_search import mcp_server


class RefreshDocsIndexTests(unittest.TestCase):
    def test_refresh_docs_index_returns_errors_instead_of_crashing(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        changed_file = "docs/flows/cancel.sample.md"
        fake_chunk = object()

        with (
            mock.patch("semantic_search.mcp_server.get_embedder", return_value=mock.Mock(vector_size=1024)),
            mock.patch("semantic_search.mcp_server.ensure_collection"),
            mock.patch("semantic_search.chunker.chunk_file", return_value=[fake_chunk]),
            mock.patch("semantic_search.mcp_server.upsert_chunks_smart", side_effect=RuntimeError("boom")),
            mock.patch("subprocess.run", return_value=SimpleNamespace(returncode=0, stdout=str(repo_root))),
        ):
            response = asyncio.run(
                mcp_server._refresh_docs_index({"changed_files": [changed_file]})
            )

        payload = json.loads(response[0].text)
        self.assertEqual(payload["indexed"], 0)
        self.assertEqual(payload["skipped"], 0)
        self.assertEqual(payload["errors"][0]["file_path"], changed_file)
        self.assertIn("boom", payload["errors"][0]["error"])
        self.assertIn("elapsed_seconds", payload)

    def test_refresh_docs_index_resolves_repo_root_without_inheriting_stdio(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        changed_file = "docs/adr/0001-outbox-pattern.sample.md"

        with (
            mock.patch("semantic_search.mcp_server.get_embedder", return_value=mock.Mock(vector_size=1024)),
            mock.patch("semantic_search.mcp_server.ensure_collection"),
            mock.patch("semantic_search.chunker.chunk_file", return_value=[]),
            mock.patch("subprocess.run", return_value=SimpleNamespace(returncode=0, stdout=str(repo_root))) as run_mock,
        ):
            response = asyncio.run(
                mcp_server._refresh_docs_index({"changed_files": [changed_file]})
            )

        payload = json.loads(response[0].text)
        self.assertEqual(payload["indexed"], 0)
        self.assertEqual(payload["skipped"], 0)
        self.assertIn("elapsed_seconds", payload)
        run_mock.assert_called_once_with(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=5,
        )


if __name__ == "__main__":
    unittest.main()
