from __future__ import annotations

import unittest
from unittest import mock

from semantic_search.embedders import voyage


class VoyageEmbedderTests(unittest.TestCase):
    def test_voyage_client_uses_configured_request_timeout(self) -> None:
        fake_client = mock.Mock()

        with (
            mock.patch.object(voyage.settings, "voyage_api_key", "demo-key"),
            mock.patch.object(voyage.settings, "voyage_request_timeout_seconds", 12.5),
            mock.patch("semantic_search.embedders.voyage.voyageai.Client", return_value=fake_client) as client_cls,
        ):
            embedder = voyage.VoyageEmbedder()

        client_cls.assert_called_once_with(api_key="demo-key", timeout=12.5)
        self.assertIs(embedder._client, fake_client)


if __name__ == "__main__":
    unittest.main()
