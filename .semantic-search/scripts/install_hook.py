#!/usr/bin/env python3
"""
Full installer for the semantic-search plugin.

Steps performed:
  1. Creates .semantic-search/.venv (if absent)
  2. Installs the plugin package into the venv  (pip install -e .)
  3. Installs post-commit and post-merge git hooks
  4. (--claude) Registers the MCP server in ~/.claude/mcp.json
  5. (--claude) Adds all 4 tool permissions to ~/.claude/settings.json

Works on Windows, Linux, and macOS without requiring bash.

Usage (from repo root or anywhere inside the repo):
    python .semantic-search/scripts/install_hook.py            # venv + hooks only
    python .semantic-search/scripts/install_hook.py --claude   # + Claude Code setup
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_DIR = SCRIPT_DIR.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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

    # Back up an existing non-symlink hook
    if dst.exists() and not dst.is_symlink():
        bak = dst.with_suffix(".bak")
        print(f"Warning: {dst} already exists and is not a symlink.")
        print(f"Backing it up to {bak}")
        shutil.move(str(dst), str(bak))

    # Try symlink first, fall back to copy
    try:
        if dst.is_symlink():
            dst.unlink()
        dst.symlink_to(src)
        print(f"Symlinked: {src} -> {dst}")
    except (OSError, NotImplementedError):
        shutil.copy2(str(src), str(dst))
        print(f"Copied (symlink unavailable): {src} -> {dst}")

    # Make executable (no-op on Windows but harmless)
    dst.chmod(dst.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    print(f"Hook '{hook_name}' installed.")


# ---------------------------------------------------------------------------
# Step 4 — Claude MCP server registration (~/.claude/mcp.json)
# ---------------------------------------------------------------------------

def _register_mcp_server(plugin_dir: Path, venv_python: Path) -> None:
    """Add the semantic-search MCP server entry to ~/.claude/mcp.json."""
    claude_dir = Path.home() / ".claude"
    claude_dir.mkdir(exist_ok=True)
    mcp_json = claude_dir / "mcp.json"

    if mcp_json.exists():
        try:
            config = json.loads(mcp_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            config = {}
    else:
        config = {}

    config.setdefault("mcpServers", {})

    entry = {
        "command": str(venv_python),
        "args": ["-m", "semantic_search.mcp_server"],
        "cwd": str(plugin_dir),
    }

    if "semantic-search" in config["mcpServers"]:
        config["mcpServers"]["semantic-search"] = entry
        print("MCP server 'semantic-search' already registered — updated path.")
    else:
        config["mcpServers"]["semantic-search"] = entry
        print("Registered MCP server 'semantic-search' in ~/.claude/mcp.json.")

    mcp_json.write_text(json.dumps(config, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Step 5 — Claude tool permissions (~/.claude/settings.json)
# ---------------------------------------------------------------------------

_MCP_PERMISSIONS = [
    "mcp__semantic-search__search_codebase",
    "mcp__semantic-search__get_file_chunk",
    "mcp__semantic-search__list_indexed_files",
    "mcp__semantic-search__refresh_docs_index",
]


def _add_permissions(claude_dir: Path) -> None:
    """Merge MCP tool permissions into ~/.claude/settings.json."""
    settings_json = claude_dir / "settings.json"

    if settings_json.exists():
        try:
            settings = json.loads(settings_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            settings = {}
    else:
        settings = {}

    settings.setdefault("permissions", {}).setdefault("allow", [])
    existing = set(settings["permissions"]["allow"])

    added = [p for p in _MCP_PERMISSIONS if p not in existing]
    if added:
        settings["permissions"]["allow"].extend(added)
        settings_json.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        print(f"Added {len(added)} permission(s) to ~/.claude/settings.json:")
        for p in added:
            print(f"  + {p}")
    else:
        print("All MCP permissions already present in ~/.claude/settings.json.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    configure_claude = "--claude" in sys.argv

    repo_root = _repo_root()
    plugin_dir = repo_root / ".semantic-search"

    print("=" * 60)
    print("semantic-search installer")
    print("=" * 60)

    # Steps 1 & 2: venv + package
    venv_python = _setup_venv(plugin_dir)

    # Step 3: git hooks
    print("\nInstalling git hooks ...")
    for hook in ("post-commit", "post-merge"):
        _install_hook(repo_root, hook)

    if configure_claude:
        # Step 4: Claude MCP registration
        print("\nConfiguring Claude MCP server ...")
        _register_mcp_server(plugin_dir, venv_python)

        # Step 5: Claude permissions
        print("\nAdding Claude tool permissions ...")
        _add_permissions(Path.home() / ".claude")

    print("\n" + "=" * 60)
    print("Installation complete!")
    print("Hooks will auto-index on commits and merges to the main branch.")
    if configure_claude:
        print("Restart Claude Code to load the semantic-search MCP server.")
    print("=" * 60)


if __name__ == "__main__":
    main()
