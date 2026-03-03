#!/usr/bin/env python3
"""
Shared semantic-search auto-indexer for git hooks.

Called by post-commit and post-merge with a mode argument:
    python _auto_index.py commit   # diff source: HEAD
    python _auto_index.py merge    # diff source: ORIG_HEAD..HEAD

Fires only on the main branch.
Detects changed docs and code files, applies hash-based deduplication.
Handles renames: old-path chunks are deleted, new-path chunks are indexed.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=5,
    ).stdout.strip()


def _diff(mode: str) -> str:
    """Return raw diff --name-status output for the given hook mode."""
    if mode == "merge":
        # All files changed between the pre-merge state and the result
        return subprocess.run(
            ["git", "diff", "--diff-filter=AMDCR", "--name-status", "ORIG_HEAD", "HEAD"],
            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=5,
        ).stdout
    else:
        # Single commit: what changed in HEAD
        return subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "-r", "--diff-filter=AMDCR", "--name-status", "HEAD"],
            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=5,
        ).stdout


def main(mode: str) -> None:
    if _git("branch", "--show-current") != "main":
        sys.exit(0)

    repo_root = Path(_git("rev-parse", "--show-toplevel"))
    plugin_dir = repo_root / ".semantic-search"

    # Resolve venv Python (prefer venv over system Python)
    venv = plugin_dir / ".venv"
    if (venv / "Scripts" / "python.exe").exists():
        python = str(venv / "Scripts" / "python.exe")
    elif (venv / "bin" / "python").exists():
        python = str(venv / "bin" / "python")
    else:
        print("[semantic-search] Warning: .venv not found — skipping auto-index.", file=sys.stderr)
        sys.exit(0)

    # Read extensions from settings; fall back to safe default
    try:
        sys.path.insert(0, str(plugin_dir))
        from semantic_search.config import settings  # type: ignore[import]
        code_exts = {e.lower() for e in settings.index_extensions_code}
        docs_exts = {e.lower() for e in settings.index_extensions_docs}
    except Exception:
        code_exts = {".py", ".ts", ".go", ".js", ".cs", ".rs"}
        docs_exts = {".md", ".yaml", ".yml", ".mmd"}

    deleted_docs: list[str] = []
    changed_docs: list[str] = []
    deleted_code: list[str] = []
    changed_code: list[str] = []

    for line in _diff(mode).splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0]
        old = parts[1]
        new = parts[2] if len(parts) > 2 else None
        target = new if new else old
        ext = Path(target).suffix.lower()

        if ext in docs_exts:
            if status.startswith("D"):
                deleted_docs.append(old)
            elif status.startswith("R"):
                deleted_docs.append(old)
                if new:
                    changed_docs.append(new)
            else:
                changed_docs.append(target)

        if ext in code_exts:
            if status.startswith("D"):
                deleted_code.append(old)
            elif status.startswith("R"):
                deleted_code.append(old)
                if new:
                    changed_code.append(new)
            else:
                changed_code.append(target)

    if not any([deleted_docs, changed_docs, deleted_code, changed_code]):
        sys.exit(0)

    label = "merge changes" if mode == "merge" else "changes"
    print(f"[semantic-search] Indexing {label} on main...")

    def index(args: list[str]) -> None:
        subprocess.run(
            [python, "-m", "semantic_search.indexer"] + args,
            cwd=str(plugin_dir),
            stdout=sys.stdout,
            stderr=sys.stderr,
        )

    if deleted_docs:
        index(["docs", "delete"] + deleted_docs)
    if changed_docs:
        index(["docs", "files"] + changed_docs)
    if deleted_code:
        index(["code", "delete"] + deleted_code)
    if changed_code:
        index(["code", "files"] + changed_code)

    print("[semantic-search] Done.")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("commit", "merge"):
        print("Usage: _auto_index.py <commit|merge>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1])
