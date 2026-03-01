# Semantic Search Layer

An optional plugin that gives AI agents fast, token-efficient access to codebase context.
Instead of blindly scanning every file, agents call `search_codebase` and get back only the
most relevant chunks — ADRs, flows, contracts, domain rules, and source code.

---

## How It Works

1. **Indexer** — chunks all docs and code files, embeds them, stores vectors in Qdrant
2. **MCP Server** — exposes four tools agents can call before making changes
3. **Git hook** — automatically re-indexes changed files on every `main` branch commit

Two separate Qdrant collections keep concerns clean:

| Collection | Contains | Updated by |
|---|---|---|
| `docs_index` | `docs/**` Markdown, YAML, Mermaid | Hook (main) + `refresh_docs_index` MCP tool |
| `code_index` | Source code under `src/` | Hook (main) only |

---

## Requirements

- Python 3.11+
- Docker (for Qdrant) — or use `QDRANT_URL=:memory:` for ephemeral in-process storage
- VoyageAI API key — or Ollama for local offline embedding

---

## Installation

```bash
# 1. Start Qdrant
cd .semantic-search
docker compose up -d

# 2. Install Python package (from .semantic-search/ directory)
pip install -e .

# 3. Configure environment
cp .env.example .env
# Open .env and set VOYAGE_API_KEY (or switch to EMBEDDER_TYPE=local)

# 4. Run the first full index
index-docs full
index-code full   # only if src/ exists

# 5. Install the git hook
bash scripts/install_hook.sh
```

---

## MCP Server Registration

Add this to `.claude/mcp.json` (Claude Code) or `claude_desktop_config.json` (Claude Desktop):

```json
{
  "mcpServers": {
    "semantic-search": {
      "command": "python",
      "args": ["-m", "semantic_search.mcp_server"],
      "cwd": "/absolute/path/to/repo/.semantic-search",
      "env": {
        "VOYAGE_API_KEY": "${VOYAGE_API_KEY}",
        "QDRANT_URL": "http://localhost:6333"
      }
    }
  }
}
```

On Windows, replace `python` with the absolute path to the venv interpreter:
`C:/path/to/.semantic-search/.venv/Scripts/python.exe`

---

## Available MCP Tools

| Tool | When to use |
|---|---|
| `search_codebase` | Before any change — find relevant architecture context |
| `get_file_chunk` | After `search_codebase` — retrieve the full text of a specific result |
| `list_indexed_files` | Audit what is indexed, verify recent re-indexing |
| `refresh_docs_index` | After updating docs — call only with explicit human approval |

---

## Switching Embedding Models

### Voyage (default)

```
EMBEDDER_TYPE=voyage
VOYAGE_API_KEY=your_key_here
```

Optimized for code + structured text. Uses asymmetric retrieval (`input_type=document/query`).

### Local via Ollama (offline, no API key)

```
EMBEDDER_TYPE=local
LOCAL_MODEL_NAME=nomic-embed-text    # 768-dim, fast
# or
LOCAL_MODEL_NAME=mxbai-embed-large  # 1024-dim, higher quality
```

Pull the model first:

```bash
ollama pull nomic-embed-text
# or
ollama pull mxbai-embed-large
```

> **Warning — dimension mismatch**: If you switch between models with different vector sizes
> (e.g. `nomic-embed-text` at 768 vs `mxbai-embed-large` at 1024), you must recreate the
> Qdrant collection and run a full re-index:
>
> ```bash
> # Drop and recreate the collection
> curl -X DELETE http://localhost:6333/collections/docs_index
> curl -X DELETE http://localhost:6333/collections/code_index
>
> # Re-index everything with the new model
> index-docs full --force
> index-code full --force
> ```

---

## Docs Update Workflow (Agent Usage)

Docs changes represent architectural knowledge changes — agents must not silently update
the semantic index. The required workflow:

1. Agent updates documentation files.
2. Agent notifies user: _"I updated `docs/flows/cancel.md`. Should I refresh the semantic index?"_
3. User approves.
4. Agent calls `refresh_docs_index(changed_files=["docs/flows/cancel.md"])`.

This is enforced by the `refresh_docs_index` tool description. The tool applies
hash-based deduplication — if content is unchanged, no API call is made.

On `main` branch commits, the git hook automatically handles docs re-indexing as well,
so docs changed on a feature branch (via `refresh_docs_index`) and then merged to main
will not be double-indexed.

---

## Post-Rename Cleanup

When a doc or code file is renamed, the git hook automatically handles it on `main`:
old-path chunks are deleted, new-path chunks are indexed.

For manual cleanup (e.g. after a rename outside of git, or on a feature branch):

```bash
index-docs delete docs/old/path.md
index-docs files docs/new/path.md
```

---

## Periodic Full Re-index

For large repos or after significant restructuring, a periodic full re-index ensures
the index stays clean (removes orphaned chunks, refreshes all hashes):

```bash
index-docs full --force
index-code full --force
```

The `--force` flag bypasses hash-check and rewrites all chunks unconditionally.

---

## Verification

```bash
# Check Qdrant is running
curl http://localhost:6333/readyz

# Check collection stats
curl http://localhost:6333/collections/docs_index

# Smoke test: search for outbox pattern
python -c "
from semantic_search.embedders import get_embedder
from semantic_search.store import search
from semantic_search.config import settings
e = get_embedder()
for r in search(e.embed_query('outbox pattern event publishing'), settings.docs_collection, top_k=3):
    print(r.payload['file_path'], r.score)
"

# Verify hash-skip works (re-index an already-indexed file)
index-docs files docs/adr/0001-outbox-pattern.sample.md
# Expected: "0 chunks indexed, N skipped (unchanged)"
```
