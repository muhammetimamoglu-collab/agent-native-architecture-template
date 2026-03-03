from __future__ import annotations

import asyncio
import json

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from semantic_search.config import settings
from semantic_search.embedders import get_embedder
from semantic_search.store import (
    ensure_collection,
    get_chunk,
    list_files,
    search,
    upsert_chunks_smart,
)

server = Server("semantic-search")

_ARTIFACT_TYPES = ["adr", "flow", "c4", "contract", "domain", "domain-visual", "ui", "other"]
_LANGUAGES = [
    "python", "javascript", "typescript", "java", "kotlin", "scala", "groovy",
    "csharp", "fsharp", "vbnet", "go", "rust", "c", "cpp", "swift", "dart",
    "ruby", "php", "lua", "perl", "shell", "powershell",
    "r", "julia", "haskell", "elixir", "erlang", "clojure", "unknown",
]


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_codebase",
            description=(
                "Search the indexed codebase and documentation semantically using natural language.\n"
                "\n"
                "Use this tool BEFORE making any code or documentation changes to retrieve relevant "
                "architectural context — flows, domain rules, contracts, ADRs, C4 structure.\n"
                "Prefer this over reading raw files; it returns only the most relevant chunks, "
                "saving context window space.\n"
                "\n"
                "collection values:\n"
                '  "docs" — architecture and documentation (ADRs, flows, contracts, domain rules, C4, UI)\n'
                '  "code" — source code implementation (functions, classes, configs)\n'
                '  "all"  — both collections merged\n'
                "\n"
                "artifact_type filter (docs collection only):\n"
                '  "adr"           — Architecture Decision Records (why decisions were made)\n'
                '  "flow"          — Business flow definitions with preconditions and side effects\n'
                '  "contract"      — OpenAPI/AsyncAPI endpoint and event definitions\n'
                '  "domain"        — Business invariants and state transition rules\n'
                '  "domain-visual" — State machine diagrams\n'
                '  "c4"            — Component and container architecture\n'
                '  "ui"            — Screen flows and navigation intent\n'
                '  "other"         — Everything else\n'
                "\n"
                "language filter (code collection only):\n"
                '  "python" | "typescript" | "go" | "csharp" | "javascript"\n'
                "\n"
                "Returns a JSON array of results ordered by relevance score (highest first). "
                "Each result includes: file_path, artifact_type, chunk_index, chunk_heading, "
                "line_start, line_end, score (0–1), content (truncated to 800 chars)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Natural language description of what you need. "
                            "Be specific: 'cancel flow preconditions and side effects' "
                            "is better than 'cancel'."
                        ),
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return. Default: 5, max: 20.",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 20,
                    },
                    "collection": {
                        "type": "string",
                        "description": "Which index to search. Default: 'docs'.",
                        "enum": ["docs", "code", "all"],
                        "default": "docs",
                    },
                    "artifact_type": {
                        "type": "string",
                        "description": "Filter by artifact type (docs collection only). Omit for all types.",
                        "enum": _ARTIFACT_TYPES,
                    },
                    "language": {
                        "type": "string",
                        "description": "Filter by programming language (code collection only). Omit for all.",
                        "enum": _LANGUAGES,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_file_chunk",
            description=(
                "Retrieve the full content of a specific chunk from an indexed file.\n"
                "\n"
                "Use this after search_codebase when a result's truncated content is not enough "
                "and you need the complete text of that chunk.\n"
                "Do NOT use this to browse files randomly — use search_codebase first to find "
                "relevant results, then use this to expand a specific one.\n"
                "\n"
                "Returns the full ChunkResult payload including complete content, line range, "
                "content_hash, last_modified, and indexed_at timestamps.\n"
                'Returns {"error": "chunk not found"} if the path or index does not exist.'
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Relative POSIX path as returned by search_codebase. "
                            "Example: 'docs/flows/cancel.sample.md'"
                        ),
                    },
                    "chunk_index": {
                        "type": "integer",
                        "description": "Zero-based chunk index from the search result.",
                        "minimum": 0,
                    },
                    "collection": {
                        "type": "string",
                        "description": "Which collection to query. Default: 'docs'.",
                        "enum": ["docs", "code"],
                        "default": "docs",
                    },
                },
                "required": ["file_path", "chunk_index"],
            },
        ),
        Tool(
            name="list_indexed_files",
            description=(
                "List all files currently indexed in the vector store.\n"
                "\n"
                "Use this to understand what is indexed before searching, to verify that a recently "
                "changed file has been re-indexed, or to audit index coverage.\n"
                "Not intended for repeated calls — call once per session if needed.\n"
                "\n"
                "Returns a JSON array of FileRecord objects sorted by file_path. "
                "Each record contains: file_path, artifact_type, language (code only), "
                "chunk_count, indexed_at, last_modified."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "collection": {
                        "type": "string",
                        "description": "Which collection to list. Default: 'docs'.",
                        "enum": ["docs", "code", "all"],
                        "default": "docs",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="refresh_docs_index",
            description=(
                "Re-index specific documentation files into docs_index immediately.\n"
                "\n"
                "Call this ONLY after receiving explicit human approval to update the semantic index, "
                "following the approval workflow in AGENT.md.\n"
                "\n"
                "Workflow:\n"
                "  1. Agent updates docs files.\n"
                "  2. Agent informs user: 'The following docs were updated: [...]. "
                "Should I refresh the semantic index now?'\n"
                "  3. User approves.\n"
                "  4. Agent calls refresh_docs_index with the changed file paths.\n"
                "\n"
                "This tool applies hash-based deduplication: chunks whose content has not changed "
                "since the last index are silently skipped, so calling it is always safe and cheap.\n"
                "Only updates docs_index — never touches code_index.\n"
                "\n"
                "Do NOT call this without explicit user approval.\n"
                "Do NOT call this for code files — code indexing is handled automatically by "
                "the git post-commit hook on the main branch.\n"
                "\n"
                'Returns: {"indexed": N, "skipped": M, "updated_at": "<ISO8601>"}\n'
                '  "indexed" = chunks actually written (content changed)\n'
                '  "skipped" = chunks unchanged (hash matched, no API call made)'
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "changed_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Relative POSIX paths of changed docs files from the repo root. "
                            "Example: ['docs/flows/cancel.sample.md', 'docs/adr/0002-new.md']"
                        ),
                        "minItems": 1,
                    },
                },
                "required": ["changed_files"],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "search_codebase":
            return await _search_codebase(arguments)
        if name == "get_file_chunk":
            return await _get_file_chunk(arguments)
        if name == "list_indexed_files":
            return await _list_indexed_files(arguments)
        if name == "refresh_docs_index":
            return await _refresh_docs_index(arguments)
        return [TextContent(type="text", text=json.dumps({"error": f"unknown tool: {name}"}))]
    except Exception as exc:
        return [
            TextContent(
                type="text",
                text=json.dumps({"error": str(exc), "tool": name}, indent=2),
            )
        ]


async def _search_codebase(args: dict) -> list[TextContent]:
    query = args["query"]
    top_k = min(int(args.get("top_k", 5)), 20)
    collection = args.get("collection", "docs")
    artifact_type = args.get("artifact_type")
    language = args.get("language")

    embedder = get_embedder()
    query_vector = embedder.embed_query(query)

    collections_to_search = []
    if collection == "docs":
        collections_to_search = [(settings.docs_collection, False)]
    elif collection == "code":
        collections_to_search = [(settings.code_collection, True)]
    else:  # "all"
        collections_to_search = [
            (settings.docs_collection, False),
            (settings.code_collection, True),
        ]

    all_results = []
    for coll_name, is_code in collections_to_search:
        try:
            results = search(
                query_vector=query_vector,
                collection_name=coll_name,
                top_k=top_k,
                artifact_type=artifact_type if not is_code else None,
                language=language if is_code else None,
            )
            all_results.extend(results)
        except Exception:
            pass  # Collection may not exist yet

    # Sort by score descending and trim to top_k
    all_results.sort(key=lambda r: r.score, reverse=True)
    all_results = all_results[:top_k]

    output = [
        {
            "file_path": r.payload["file_path"],
            "artifact_type": r.payload.get("artifact_type", ""),
            "language": r.payload.get("language", ""),
            "chunk_index": r.payload["chunk_index"],
            "chunk_heading": r.payload["chunk_heading"],
            "line_start": r.payload["line_start"],
            "line_end": r.payload["line_end"],
            "score": round(r.score, 4),
            "content": r.payload["content"][:800],
        }
        for r in all_results
    ]
    return [TextContent(type="text", text=json.dumps(output, indent=2))]


async def _get_file_chunk(args: dict) -> list[TextContent]:
    file_path = args["file_path"]
    chunk_index = int(args["chunk_index"])
    collection = args.get("collection", "docs")
    coll_name = settings.docs_collection if collection == "docs" else settings.code_collection

    chunk = get_chunk(file_path, chunk_index, coll_name)
    if chunk is None:
        return [TextContent(type="text", text=json.dumps({"error": "chunk not found"}))]
    return [TextContent(type="text", text=json.dumps(chunk, indent=2))]


async def _list_indexed_files(args: dict) -> list[TextContent]:
    collection = args.get("collection", "docs")

    if collection == "all":
        docs = list_files(settings.docs_collection)
        code = list_files(settings.code_collection)
        combined = sorted(docs + code, key=lambda x: x["file_path"])
        return [TextContent(type="text", text=json.dumps(combined, indent=2))]

    coll_name = settings.docs_collection if collection == "docs" else settings.code_collection
    files = list_files(coll_name)
    return [TextContent(type="text", text=json.dumps(files, indent=2))]


async def _refresh_docs_index(args: dict) -> list[TextContent]:
    from datetime import UTC, datetime
    from pathlib import Path

    import subprocess

    total_indexed = 0
    total_skipped = 0
    errors: list[dict[str, str]] = []

    try:
        changed_files: list[str] = args["changed_files"]
        embedder = get_embedder()
        ensure_collection(settings.docs_collection, embedder.vector_size)

        # Resolve repo root
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True,
        )
        repo_root = Path(result.stdout.strip()) if result.returncode == 0 else Path.cwd().parent

        exts = {e.lower() for e in settings.index_extensions_docs}

        for fp in changed_files:
            path = repo_root / fp
            if not path.exists():
                continue
            if path.suffix.lower() not in exts:
                continue

            try:
                from semantic_search.chunker import chunk_file as _chunk_file

                chunks = _chunk_file(path, fp, is_code=False)
                if not chunks:
                    continue

                result = upsert_chunks_smart(chunks, embedder, settings.docs_collection)
                total_indexed += result["indexed"]
                total_skipped += result["skipped"]
            except Exception as exc:
                errors.append({"file_path": fp, "error": str(exc)})
    except Exception as exc:
        errors.append({"scope": "refresh_docs_index", "error": str(exc)})

    result_payload = {
        "indexed": total_indexed,
        "skipped": total_skipped,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    if errors:
        result_payload["errors"] = errors
    return [TextContent(type="text", text=json.dumps(result_payload, indent=2))]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    embedder = get_embedder()
    ensure_collection(settings.docs_collection, embedder.vector_size)
    ensure_collection(settings.code_collection, embedder.vector_size)
    asyncio.run(_run())


async def _run() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    main()
