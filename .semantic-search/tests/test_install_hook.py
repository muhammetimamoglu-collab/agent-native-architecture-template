from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


def _load_install_hook_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "install_hook.py"
    spec = importlib.util.spec_from_file_location("semantic_search_install_hook", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


install_hook = _load_install_hook_module()


class InstallHookTests(unittest.TestCase):
    def test_register_project_mcp_server_writes_repo_mcp_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            plugin_dir = repo_root / ".semantic-search"
            plugin_dir.mkdir()
            venv_python = plugin_dir / ".venv" / "Scripts" / "python.exe"
            venv_python.parent.mkdir(parents=True)
            venv_python.write_text("", encoding="utf-8")

            install_hook._register_project_mcp_server(repo_root, plugin_dir, venv_python)

            payload = json.loads((repo_root / ".mcp.json").read_text(encoding="utf-8"))

        self.assertEqual(payload["mcpServers"]["semantic-search"]["type"], "stdio")
        self.assertEqual(
            payload["mcpServers"]["semantic-search"]["command"],
            venv_python.resolve().as_posix(),
        )
        self.assertEqual(
            payload["mcpServers"]["semantic-search"]["env"]["SEMANTIC_SEARCH_ENV_FILE"],
            (plugin_dir / ".env").resolve().as_posix(),
        )

    def test_reconcile_permissions_keeps_refresh_promptable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "settings.json"
            settings_path.write_text(
                json.dumps(
                    {
                        "permissions": {
                            "allow": [
                                "mcp__semantic-search__refresh_docs_index",
                                "existing.permission",
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )

            install_hook._reconcile_permissions(settings_path, "temp/settings.json")

            payload = json.loads(settings_path.read_text(encoding="utf-8"))

        allow = payload["permissions"]["allow"]
        self.assertNotIn("mcp__semantic-search__refresh_docs_index", allow)
        self.assertIn("mcp__semantic-search__search_codebase", allow)
        self.assertIn("mcp__semantic-search__get_file_chunk", allow)
        self.assertIn("mcp__semantic-search__list_indexed_files", allow)
        self.assertIn("existing.permission", allow)

    def test_strip_toml_table_removes_existing_server_and_env_tables(self) -> None:
        original = """
model = "gpt-5"

[mcp_servers.semantic-search]
command = "old"

[mcp_servers.semantic-search.env]
SEMANTIC_SEARCH_ENV_FILE = "old.env"

[mcp_servers.other]
command = "keep"
""".strip()

        cleaned = install_hook._strip_toml_table(original, "mcp_servers.semantic-search")

        self.assertNotIn("[mcp_servers.semantic-search]", cleaned)
        self.assertNotIn("[mcp_servers.semantic-search.env]", cleaned)
        self.assertIn("[mcp_servers.other]", cleaned)

    def test_register_codex_mcp_server_writes_project_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            plugin_dir = repo_root / ".semantic-search"
            plugin_dir.mkdir()
            venv_python = plugin_dir / ".venv" / "Scripts" / "python.exe"
            venv_python.parent.mkdir(parents=True)
            venv_python.write_text("", encoding="utf-8")

            install_hook._register_codex_mcp_server(repo_root, plugin_dir, venv_python)

            config_text = (repo_root / ".codex" / "config.toml").read_text(encoding="utf-8")

        self.assertIn("[mcp_servers.semantic-search]", config_text)
        self.assertIn('args = ["-m", "semantic_search.mcp_server"]', config_text)
        self.assertIn(f"command = {json.dumps(str(venv_python))}", config_text)
        self.assertIn(f"cwd = {json.dumps(str(repo_root))}", config_text)
        self.assertIn("tool_timeout_sec = 180", config_text)
        self.assertIn("[mcp_servers.semantic-search.env]", config_text)


if __name__ == "__main__":
    unittest.main()
