#!/usr/bin/env python3
"""
Full installer for the semantic-search plugin.

Steps performed:
  1. Creates .semantic-search/.venv (if absent)
  2. Installs the plugin package into the venv  (pip install -e .)
  3. Installs post-commit and post-merge git hooks
  4. (--claude) Removes any legacy user-scoped "semantic-search" MCP entry
  5. (--claude) Registers the MCP server in repo_root/.mcp.json
  6. (--claude) Enables the project MCP server in repo_root/.claude/settings.local.json
  7. (--claude) Auto-allows only the 3 read-only tools in Claude settings
  8. (--claude) Removes refresh_docs_index from allow-lists so Claude asks for approval
  9. (--codex) Registers the MCP server in repo_root/.codex/config.toml

Works on Windows, Linux, and macOS without requiring bash.

Usage (from repo root or anywhere inside the repo):
    python .semantic-search/scripts/install_hook.py                   # venv + hooks only
    python .semantic-search/scripts/install_hook.py --claude          # + project-scoped Claude Code setup
    python .semantic-search/scripts/install_hook.py --codex           # + Codex project MCP setup
    python .semantic-search/scripts/install_hook.py --claude --codex  # + both
"""

from __future__ import annotations

import json
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_DIR = SCRIPT_DIR.parent
_MCP_SERVER_NAME = "semantic-search"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _json_path(path: Path) -> str:
    return path.resolve().as_posix()


def _repo_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, cwd=str(PLUGIN_DIR),
    )
    if result.returncode == 0:
        return Path(result.stdout.strip())
    print("Error: not inside a git repository.", file=sys.stderr)
    sys.exit(1)


def _venv_python(venv: Path) -> Path:
    """Return the Python executable inside the venv (cross-platform)."""
    win = venv / "Scripts" / "python.exe"
    unix = venv / "bin" / "python"
    return win if win.exists() else unix


# ---------------------------------------------------------------------------
# Step 1 + 2 — venv + package
# ---------------------------------------------------------------------------

def _setup_venv(plugin_dir: Path) -> Path:
    """Create .venv and install the package. Returns the venv Python path."""
    venv = plugin_dir / ".venv"

    if not venv.exists():
        print(f"Creating virtual environment at {venv} ...")
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
        print("Virtual environment created.")
    else:
        print(f"Virtual environment already exists at {venv} — skipping creation.")

    python = _venv_python(venv)
    if not python.exists():
        print(f"Error: expected Python at {python} but not found.", file=sys.stderr)
        sys.exit(1)

    print("Installing semantic-search package into venv (pip install -e .) ...")
    subprocess.run(
        [str(python), "-m", "pip", "install", "--quiet", "-e", str(plugin_dir)],
        check=True,
    )
    print("Package installed.")
    return python


# ---------------------------------------------------------------------------
# Step 3 — git hooks
# ---------------------------------------------------------------------------

def _install_hook(repo_root: Path, hook_name: str) -> None:
    """Install a single hook by name (e.g. 'post-commit', 'post-merge')."""
    src = repo_root / ".semantic-search" / "hooks" / hook_name
    dst = repo_root / ".git" / "hooks" / hook_name

    if not src.exists():
        print(f"Error: hook source not found at {src}", file=sys.stderr)
        sys.exit(1)

    if dst.exists() and not dst.is_symlink():
        bak = dst.with_suffix(".bak")
        print(f"Warning: {dst} already exists and is not a symlink.")
        print(f"Backing it up to {bak}")
        shutil.move(str(dst), str(bak))

    try:
        if dst.is_symlink():
            dst.unlink()
        dst.symlink_to(src)
        print(f"Symlinked: {src} -> {dst}")
    except (OSError, NotImplementedError):
        shutil.copy2(str(src), str(dst))
        print(f"Copied (symlink unavailable): {src} -> {dst}")

    dst.chmod(dst.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    print(f"Hook '{hook_name}' installed.")


# ---------------------------------------------------------------------------
# Step 4 + 5 + 6 — Claude MCP registration (project-scoped .mcp.json)
# ---------------------------------------------------------------------------

def _remove_legacy_user_mcp_server() -> None:
    claude_dir = Path.home() / ".claude"
    mcp_json = claude_dir / "mcp.json"
    config = _read_json(mcp_json)
    servers = config.get("mcpServers")

    if not isinstance(servers, dict) or _MCP_SERVER_NAME not in servers:
        print("No legacy user-scoped MCP server 'semantic-search' found in ~/.claude/mcp.json.")
        return

    del servers[_MCP_SERVER_NAME]
    config["mcpServers"] = servers
    _write_json(mcp_json, config)
    print("Removed legacy user-scoped MCP server 'semantic-search' from ~/.claude/mcp.json.")


def _register_project_mcp_server(repo_root: Path, plugin_dir: Path, venv_python: Path) -> None:
    """Add the semantic-search MCP server entry to repo_root/.mcp.json."""
    mcp_json = repo_root / ".mcp.json"
    config = _read_json(mcp_json)
    config.setdefault("mcpServers", {})

    entry = {
        "type": "stdio",
        "command": _json_path(venv_python),
        "args": ["-m", "semantic_search.mcp_server"],
        "env": {
            "SEMANTIC_SEARCH_ENV_FILE": _json_path(plugin_dir / ".env"),
        },
    }

    if _MCP_SERVER_NAME in config["mcpServers"]:
        config["mcpServers"][_MCP_SERVER_NAME] = entry
        print("Project MCP server 'semantic-search' already registered — updated repo .mcp.json.")
    else:
        config["mcpServers"][_MCP_SERVER_NAME] = entry
        print("Registered project MCP server 'semantic-search' in .mcp.json.")

    _write_json(mcp_json, config)


def _enable_project_mcp_server(repo_root: Path) -> None:
    """Enable the repo .mcp.json server in repo_root/.claude/settings.local.json."""
    project_claude_dir = repo_root / ".claude"
    project_claude_dir.mkdir(exist_ok=True)
    settings_local_json = project_claude_dir / "settings.local.json"

    settings = _read_json(settings_local_json)
    enabled = settings.setdefault("enabledMcpjsonServers", [])
    if _MCP_SERVER_NAME not in enabled:
        enabled.append(_MCP_SERVER_NAME)
        _write_json(settings_local_json, settings)
        print("Enabled project MCP server 'semantic-search' in .claude/settings.local.json.")
    else:
        print("Project MCP server 'semantic-search' already enabled in .claude/settings.local.json.")


# ---------------------------------------------------------------------------
# Step 7 + 8 — Claude tool permissions
# ---------------------------------------------------------------------------

_AUTO_ALLOW_MCP_PERMISSIONS = [
    "mcp__semantic-search__search_codebase",
    "mcp__semantic-search__get_file_chunk",
    "mcp__semantic-search__list_indexed_files",
]
_APPROVAL_REQUIRED_MCP_PERMISSIONS = [
    "mcp__semantic-search__refresh_docs_index",
]


def _reconcile_permissions(settings_path: Path, label: str) -> None:
    settings_path.parent.mkdir(exist_ok=True)
    settings = _read_json(settings_path)
    allow = settings.setdefault("permissions", {}).setdefault("allow", [])

    added = [permission for permission in _AUTO_ALLOW_MCP_PERMISSIONS if permission not in allow]
    for permission in added:
        allow.append(permission)

    removed = [permission for permission in allow if permission in _APPROVAL_REQUIRED_MCP_PERMISSIONS]
    if removed:
        allow[:] = [permission for permission in allow if permission not in _APPROVAL_REQUIRED_MCP_PERMISSIONS]

    if added or removed:
        _write_json(settings_path, settings)

    if added:
        print(f"Added {len(added)} auto-allow permission(s) to {label}:")
        for permission in added:
            print(f"  + {permission}")
    else:
        print(f"All auto-allow semantic-search permissions already present in {label}.")

    if removed:
        print(f"Removed {len(removed)} approval-required permission(s) from {label}:")
        for permission in removed:
            print(f"  - {permission}")
    else:
        print(f"No approval-required semantic-search permissions found in {label}.")


def _reconcile_claude_permissions(repo_root: Path) -> None:
    """Keep read-only tools auto-allowed and refresh_docs_index promptable."""
    _reconcile_permissions(Path.home() / ".claude" / "settings.json", "~/.claude/settings.json")
    _reconcile_permissions(repo_root / ".claude" / "settings.local.json", ".claude/settings.local.json")


# ---------------------------------------------------------------------------
# Step 9 — Codex project MCP registration (<repo>/.codex/config.toml)
# ---------------------------------------------------------------------------

_TOML_TABLE_RE = re.compile(r"^\[(?P<name>[^\]]+)\]\s*$")


def _strip_toml_table(text: str, table_prefix: str) -> str:
    """Remove a TOML table and any nested subtables while preserving other content."""
    kept_lines: list[str] = []
    skipping = False

    for line in text.splitlines():
        match = _TOML_TABLE_RE.match(line.strip())
        if match:
            table_name = match.group("name").strip()
            skipping = table_name == table_prefix or table_name.startswith(f"{table_prefix}.")
        if not skipping:
            kept_lines.append(line)

    return "\n".join(kept_lines).strip()


def _build_codex_mcp_block(repo_root: Path, plugin_dir: Path, venv_python: Path) -> str:
    env_file = plugin_dir / ".env"
    return "\n".join(
        [
            f"[mcp_servers.{_MCP_SERVER_NAME}]",
            f"command = {json.dumps(str(venv_python))}",
            'args = ["-m", "semantic_search.mcp_server"]',
            f"cwd = {json.dumps(str(repo_root))}",
            "startup_timeout_sec = 20",
            "tool_timeout_sec = 180",
            "",
            f"[mcp_servers.{_MCP_SERVER_NAME}.env]",
            f"SEMANTIC_SEARCH_ENV_FILE = {json.dumps(str(env_file))}",
        ]
    )


def _register_codex_mcp_server(repo_root: Path, plugin_dir: Path, venv_python: Path) -> None:
    """Add the semantic-search MCP server entry to repo_root/.codex/config.toml."""
    codex_dir = repo_root / ".codex"
    codex_dir.mkdir(exist_ok=True)
    config_toml = codex_dir / "config.toml"

    existing = config_toml.read_text(encoding="utf-8") if config_toml.exists() else ""
    cleaned = _strip_toml_table(existing, f"mcp_servers.{_MCP_SERVER_NAME}")
    block = _build_codex_mcp_block(repo_root, plugin_dir, venv_python)

    new_text = f"{cleaned}\n\n{block}\n" if cleaned else f"{block}\n"
    config_toml.write_text(new_text, encoding="utf-8")
    print("Registered MCP server 'semantic-search' in .codex/config.toml.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    configure_claude = "--claude" in sys.argv
    configure_codex = "--codex" in sys.argv

    repo_root = _repo_root()
    plugin_dir = repo_root / ".semantic-search"

    print("=" * 60)
    print("semantic-search installer")
    print("=" * 60)

    venv_python = _setup_venv(plugin_dir)

    print("\nInstalling git hooks ...")
    for hook in ("post-commit", "post-merge"):
        _install_hook(repo_root, hook)

    if configure_claude:
        print("\nRemoving legacy user-scoped Claude MCP server ...")
        _remove_legacy_user_mcp_server()

        print("\nConfiguring project-scoped Claude MCP server ...")
        _register_project_mcp_server(repo_root, plugin_dir, venv_python)

        print("\nEnabling project MCP server in Claude local settings ...")
        _enable_project_mcp_server(repo_root)

        print("\nReconciling Claude tool permissions ...")
        _reconcile_claude_permissions(repo_root)

    if configure_codex:
        print("\nConfiguring Codex project MCP server ...")
        _register_codex_mcp_server(repo_root, plugin_dir, venv_python)

    print("\n" + "=" * 60)
    print("Installation complete!")
    print("Hooks will auto-index on commits and merges to the main branch.")
    if configure_claude:
        print("Restart Claude Code to load the project-scoped semantic-search MCP server.")
    if configure_codex:
        print("Trust or reopen the project in Codex to load the project MCP server.")
    print("=" * 60)


if __name__ == "__main__":
    main()
