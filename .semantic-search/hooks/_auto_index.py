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
import urllib.request
import urllib.error
from datetime import datetime, timezone
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


def _setup_log(plugin_dir: Path) -> Path:
    log_dir = plugin_dir / "logs"
    log_dir.mkdir(exist_ok=True)
    return log_dir / "auto-index.log"


def _log(log_path: Path, message: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"{ts}  {message}\n")
    except OSError:
        pass  # Never fail the hook because of logging


def _check_qdrant(qdrant_url: str, log_path: Path, api_key: str = "") -> bool:
    """Return True if Qdrant responds; print and log a clear error otherwise."""
    if qdrant_url == ":memory:":
        return True  # embedded mode — no external server needed
    check_url = qdrant_url.rstrip("/") + "/healthz"
    req = urllib.request.Request(check_url)
    if api_key:
        req.add_header("api-key", api_key)
    is_cloud = "cloud.qdrant.io" in qdrant_url
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status < 500:
                return True
            msg = f"Qdrant at {qdrant_url} returned HTTP {resp.status}"
    except urllib.error.URLError as exc:
        msg = f"Qdrant unreachable at {qdrant_url}: {exc.reason}"
    except Exception as exc:
        msg = f"Qdrant check failed ({qdrant_url}): {exc}"

    print(f"[semantic-search] WARNING: {msg}", file=sys.stderr)
    if is_cloud:
        print(
            "[semantic-search] Hint: check QDRANT_API_KEY in .semantic-search/.env",
            file=sys.stderr,
        )
    else:
        print(
            "[semantic-search] Hint: start Qdrant with  "
            "docker compose -f .semantic-search/docker-compose.yml up -d",
            file=sys.stderr,
        )
    _log(log_path, f"ERROR  {msg}")
    return False


def main(mode: str) -> None:
    if _git("branch", "--show-current") != "main":
        sys.exit(0)

    repo_root = Path(_git("rev-parse", "--show-toplevel"))
    plugin_dir = repo_root / ".semantic-search"
    log_path = _setup_log(plugin_dir)

    commit_sha = _git("rev-parse", "--short", "HEAD")
    _log(log_path, f"--- {mode.upper()} hook triggered (commit: {commit_sha}) ---")

    # Resolve venv Python (prefer venv over system Python)
    venv = plugin_dir / ".venv"
    if (venv / "Scripts" / "python.exe").exists():
        python = str(venv / "Scripts" / "python.exe")
    elif (venv / "bin" / "python").exists():
        python = str(venv / "bin" / "python")
    else:
        msg = ".venv not found — skipping auto-index."
        print(f"[semantic-search] Warning: {msg}", file=sys.stderr)
        _log(log_path, f"SKIP   {msg}")
        sys.exit(0)

    # Read extensions and Qdrant URL from settings; fall back to safe defaults
    qdrant_url = "http://localhost:6333"
    qdrant_api_key = ""
    try:
        sys.path.insert(0, str(plugin_dir))
        from semantic_search.config import settings  # type: ignore[import]
        code_exts = {e.lower() for e in settings.index_extensions_code}
        docs_exts = {e.lower() for e in settings.index_extensions_docs}
        qdrant_url = settings.qdrant_url
        qdrant_api_key = settings.qdrant_api_key
    except Exception as exc:
        code_exts = {".py", ".ts", ".go", ".js", ".cs", ".rs"}
        docs_exts = {".md", ".yaml", ".yml", ".mmd"}
        _log(log_path, f"WARN   Could not load settings ({exc}); using defaults")

    # Fail fast — no point running the indexer if Qdrant is down
    if not _check_qdrant(qdrant_url, log_path, qdrant_api_key):
        _log(log_path, "SKIP   Qdrant unreachable — auto-index skipped")
        sys.exit(0)

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
        _log(log_path, "SKIP   no relevant files changed")
        sys.exit(0)

    label = "merge changes" if mode == "merge" else "changes"
    print(f"[semantic-search] Indexing {label} on main...")

    def index(args: list[str]) -> tuple[bool, str]:
        result = subprocess.run(
            [python, "-m", "semantic_search.indexer"] + args,
            cwd=str(plugin_dir),
            capture_output=True,
            text=True,
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode != 0:
            print(
                f"[semantic-search] ERROR: indexer failed (exit {result.returncode})"
                f" — args: {args}",
                file=sys.stderr,
            )
            for line in output.splitlines():
                print(f"  {line}", file=sys.stderr)
        elif output:
            for line in output.splitlines():
                print(line)
        return result.returncode == 0, output

    errors: list[str] = []

    if deleted_docs:
        ok, out = index(["docs", "delete"] + deleted_docs)
        _log(log_path, f"{'OK  ' if ok else 'FAIL'}   docs delete {deleted_docs[:5]} | {out[:200]}")
        if not ok:
            errors.append(f"docs delete")
    if changed_docs:
        ok, out = index(["docs", "files"] + changed_docs)
        _log(log_path, f"{'OK  ' if ok else 'FAIL'}   docs files {changed_docs[:5]} | {out[:200]}")
        if not ok:
            errors.append(f"docs files")
    if deleted_code:
        ok, out = index(["code", "delete"] + deleted_code)
        _log(log_path, f"{'OK  ' if ok else 'FAIL'}   code delete {deleted_code[:5]} | {out[:200]}")
        if not ok:
            errors.append(f"code delete")
    if changed_code:
        ok, out = index(["code", "files"] + changed_code)
        _log(log_path, f"{'OK  ' if ok else 'FAIL'}   code files {changed_code[:5]} | {out[:200]}")
        if not ok:
            errors.append(f"code files")

    if errors:
        print(
            f"[semantic-search] WARNING: {len(errors)} indexer step(s) failed — "
            f"check .semantic-search/logs/auto-index.log",
            file=sys.stderr,
        )
        _log(log_path, f"DONE   with {len(errors)} error(s): {errors}")
    else:
        print("[semantic-search] Done.")
        _log(log_path, "DONE   OK")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("commit", "merge"):
        print("Usage: _auto_index.py <commit|merge>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1])
