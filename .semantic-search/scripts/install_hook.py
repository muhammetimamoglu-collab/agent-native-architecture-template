#!/usr/bin/env python3
"""
Cross-platform installer for the semantic-search git hooks.
Installs both post-commit and post-merge hooks.
Works on Windows, Linux, and macOS without requiring bash.

Usage (from anywhere):
    python .semantic-search/scripts/install_hook.py
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_DIR = SCRIPT_DIR.parent


def _repo_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, cwd=str(PLUGIN_DIR),
    )
    if result.returncode == 0:
        return Path(result.stdout.strip())
    print("Error: not inside a git repository.", file=sys.stderr)
    sys.exit(1)


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


def main() -> None:
    repo_root = _repo_root()
    for hook in ("post-commit", "post-merge"):
        _install_hook(repo_root, hook)
    print("All hooks installed. They will run on commits and merges to the main branch.")


if __name__ == "__main__":
    main()
