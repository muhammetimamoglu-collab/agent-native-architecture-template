#!/usr/bin/env python3
"""
Convenience wrapper for the semantic-search indexer CLI.
Works on Windows, Linux, and macOS without requiring bash or an activated venv.

Usage (from the repo root or anywhere):
    python .semantic-search/scripts/index.py docs full
    python .semantic-search/scripts/index.py docs full --force
    python .semantic-search/scripts/index.py code full
    python .semantic-search/scripts/index.py docs files docs/some-file.md
    python .semantic-search/scripts/index.py docs delete docs/old-file.md
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_DIR = SCRIPT_DIR.parent
VENV = PLUGIN_DIR / ".venv"

# Platform-aware venv paths
_scripts = VENV / "Scripts"  # Windows
_bin = VENV / "bin"          # Linux / macOS
_base = _scripts if (_scripts).exists() else _bin

PIP = _base / "pip"
INDEX_DOCS = _base / "index-docs"
INDEX_CODE = _base / "index-code"


def _setup_venv() -> None:
    print("No .venv found — creating virtual environment...")
    subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)

    # Recalculate paths after venv creation
    global PIP, INDEX_DOCS, INDEX_CODE, _base
    _base = (VENV / "Scripts") if (VENV / "Scripts").exists() else (VENV / "bin")
    PIP = _base / "pip"
    INDEX_DOCS = _base / "index-docs"
    INDEX_CODE = _base / "index-code"

    print("Installing semantic-search package...")
    subprocess.run([str(PIP), "install", "-e", str(PLUGIN_DIR), "--quiet"], check=True)
    print("Done. Don't forget to copy .env.example → .env and fill in your API key.\n")


def main() -> None:
    if not VENV.exists():
        _setup_venv()

    args = sys.argv[1:]
    if not args:
        print(
            "Usage: python .semantic-search/scripts/index.py "
            "[docs|code] [full [--force] | files <paths...> | delete <paths...>]"
        )
        sys.exit(1)

    collection, *rest = args

    if collection == "docs":
        cmd = [str(INDEX_DOCS), *rest]
    elif collection == "code":
        cmd = [str(INDEX_CODE), *rest]
    else:
        print(f"Error: unknown collection '{collection}'. Use 'docs' or 'code'.")
        sys.exit(1)

    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
