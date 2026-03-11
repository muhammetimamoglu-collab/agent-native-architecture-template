from __future__ import annotations

import unittest

from typer.testing import CliRunner

from semantic_search import indexer


class IndexerCliTests(unittest.TestCase):
    def test_root_app_exposes_docs_and_code_groups(self) -> None:
        runner = CliRunner()

        result = runner.invoke(indexer.app, ["--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("docs", result.stdout)
        self.assertIn("code", result.stdout)


if __name__ == "__main__":
    unittest.main()
