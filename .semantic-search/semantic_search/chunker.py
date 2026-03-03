from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from semantic_search.hasher import content_hash

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

_DIR_TO_ARTIFACT: dict[str, str] = {
    "adr": "adr",
    "flows": "flow",
    "c4": "c4",
    "contracts": "contract",
    "domain": "domain",
    "domain-visual": "domain-visual",
    "ui": "ui",
}

_EXT_TO_LANGUAGE: dict[str, str] = {
    # JVM
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".groovy": "groovy",
    # .NET
    ".cs": "csharp",
    ".fs": "fsharp",
    ".vb": "vbnet",
    # Web / scripting
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".php": "php",
    ".rb": "ruby",
    ".lua": "lua",
    ".pl": "perl",
    # Systems
    ".py": "python",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".swift": "swift",
    # Mobile
    ".dart": "dart",
    # Shell
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".ps1": "powershell",
    # Data / config
    ".r": "r",
    ".jl": "julia",
    ".hs": "haskell",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".clj": "clojure",
}


@dataclass
class Chunk:
    file_path: str          # POSIX relative from repo root
    artifact_type: str      # docs: adr|flow|c4|... / code: "code"
    language: str           # code only; "" for docs
    chunk_index: int        # zero-based within file
    chunk_heading: str      # heading text or fallback descriptor
    content: str            # raw chunk text
    line_start: int         # 1-based, inclusive
    line_end: int           # 1-based, inclusive
    last_modified: str = field(default="")   # ISO8601 from git log

    @property
    def content_hash(self) -> str:
        return content_hash(self.content)

    def to_payload(self) -> dict:
        return {
            "file_path": self.file_path,
            "artifact_type": self.artifact_type,
            "language": self.language,
            "chunk_index": self.chunk_index,
            "chunk_heading": self.chunk_heading,
            "content": self.content,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "content_hash": self.content_hash,
            "last_modified": self.last_modified,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _infer_artifact_type(path: Path) -> str:
    for part in path.parts:
        if part in _DIR_TO_ARTIFACT:
            return _DIR_TO_ARTIFACT[part]
    return "other"


def _infer_language(path: Path) -> str:
    return _EXT_TO_LANGUAGE.get(path.suffix.lower(), "unknown")


def _git_last_modified(path: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cI", "--", str(path)],
            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Markdown chunker — split on ## / ### headings
# ---------------------------------------------------------------------------

_H2_H3 = re.compile(r"^#{2,3} ")


def _split_markdown(text: str) -> list[tuple[str, str, int, int]]:
    lines = text.splitlines(keepends=True)
    sections: list[tuple[str, str, int, int]] = []
    current_heading = "preamble"
    current_start = 1
    current_lines: list[str] = []

    for i, line in enumerate(lines, start=1):
        if _H2_H3.match(line) and current_lines:
            body = "".join(current_lines)
            if body.strip():
                sections.append((current_heading, body, current_start, i - 1))
            current_heading = line.strip().lstrip("#").strip()
            current_start = i
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        body = "".join(current_lines)
        if body.strip():
            sections.append((current_heading, body, current_start, len(lines)))

    return sections or [("whole file", text, 1, len(lines))]


# ---------------------------------------------------------------------------
# YAML chunker — split on top-level keys
# ---------------------------------------------------------------------------

_TOP_LEVEL_KEY = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_-]*\s*:")


def _split_yaml(text: str) -> list[tuple[str, str, int, int]]:
    lines = text.splitlines(keepends=True)
    blocks: list[tuple[str, str, int, int]] = []
    current_key = "header"
    current_start = 1
    current_lines: list[str] = []

    for i, line in enumerate(lines, start=1):
        if _TOP_LEVEL_KEY.match(line) and current_lines:
            body = "".join(current_lines)
            if body.strip():
                blocks.append((current_key, body, current_start, i - 1))
            current_key = line.split(":")[0].strip()
            current_start = i
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        body = "".join(current_lines)
        if body.strip():
            blocks.append((current_key, body, current_start, len(lines)))

    return blocks or [("whole file", text, 1, len(lines))]


# ---------------------------------------------------------------------------
# JSON / .csproj chunker — top-level key; fallback: 50-line blocks
# ---------------------------------------------------------------------------

_JSON_TOP_KEY = re.compile(r'^\s*"([^"]+)"\s*:')
_CSPROJ_TOP_KEY = re.compile(r"^\s*<([A-Za-z][A-Za-z0-9]+)[^/]*>")
_FALLBACK_BLOCK = 50


def _split_json_or_csproj(text: str, suffix: str) -> list[tuple[str, str, int, int]]:
    lines = text.splitlines(keepends=True)
    pattern = _JSON_TOP_KEY if suffix == ".json" else _CSPROJ_TOP_KEY
    blocks: list[tuple[str, str, int, int]] = []
    current_key = "header"
    current_start = 1
    current_lines: list[str] = []

    for i, line in enumerate(lines, start=1):
        m = pattern.match(line)
        if m and current_lines:
            body = "".join(current_lines)
            if body.strip():
                blocks.append((current_key, body, current_start, i - 1))
            current_key = m.group(1)
            current_start = i
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        body = "".join(current_lines)
        if body.strip():
            blocks.append((current_key, body, current_start, len(lines)))

    if not blocks:
        # Fallback: fixed-size blocks
        for start in range(0, len(lines), _FALLBACK_BLOCK):
            end = min(start + _FALLBACK_BLOCK, len(lines))
            body = "".join(lines[start:end])
            if body.strip():
                blocks.append((f"lines {start+1}-{end}", body, start + 1, end))

    return blocks


# ---------------------------------------------------------------------------
# Code chunker — function/class boundary; fallback: 80–100 line blocks
# ---------------------------------------------------------------------------

_CODE_BOUNDARY = re.compile(
    r"^(?:(?:async\s+)?def |class |func |public |private |protected |internal |"
    r"static |async function |function |export (?:default )?(?:function|class|async))"
)
_CODE_FALLBACK_MIN = 80
_CODE_FALLBACK_MAX = 100


def _split_code(text: str) -> list[tuple[str, str, int, int]]:
    lines = text.splitlines(keepends=True)
    blocks: list[tuple[str, str, int, int]] = []
    current_heading = "module"
    current_start = 1
    current_lines: list[str] = []

    for i, line in enumerate(lines, start=1):
        if _CODE_BOUNDARY.match(line) and current_lines:
            body = "".join(current_lines)
            if body.strip():
                blocks.append((current_heading, body, current_start, i - 1))
            current_heading = line.strip()[:80]
            current_start = i
            current_lines = [line]
        else:
            current_lines.append(line)

        # Flush at fallback max size even without a boundary
        if len(current_lines) >= _CODE_FALLBACK_MAX:
            body = "".join(current_lines)
            if body.strip():
                blocks.append((current_heading, body, current_start, i))
            current_heading = "continuation"
            current_start = i + 1
            current_lines = []

    if current_lines:
        body = "".join(current_lines)
        if body.strip():
            blocks.append((current_heading, body, current_start, len(lines)))

    return blocks or [("whole file", text, 1, len(lines))]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def chunk_file(path: Path, file_path_str: str, is_code: bool = False) -> list[Chunk]:
    """
    Chunk a file into semantically meaningful pieces.

    Args:
        path:           Absolute path to the file.
        file_path_str:  POSIX-relative path stored in payloads (from repo root).
        is_code:        True → use code collection metadata (language field).
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    suffix = path.suffix.lower()
    last_modified = _git_last_modified(path)

    if is_code:
        artifact_type = "code"
        language = _infer_language(path)
    else:
        artifact_type = _infer_artifact_type(path)
        language = ""

    if suffix == ".md":
        raw = _split_markdown(text)
    elif suffix in (".yaml", ".yml"):
        raw = _split_yaml(text)
    elif suffix == ".mmd":
        raw = [("whole file", text, 1, max(1, len(text.splitlines())))]
    elif suffix in (".json", ".csproj"):
        raw = _split_json_or_csproj(text, suffix)
    elif suffix in (".py", ".ts", ".go", ".cs", ".js", ".rs"):
        raw = _split_code(text)
    else:
        raw = [("whole file", text, 1, max(1, len(text.splitlines())))]

    return [
        Chunk(
            file_path=file_path_str,
            artifact_type=artifact_type,
            language=language,
            chunk_index=i,
            chunk_heading=heading,
            content=content,
            line_start=line_start,
            line_end=line_end,
            last_modified=last_modified,
        )
        for i, (heading, content, line_start, line_end) in enumerate(raw)
        if content.strip()
    ]
