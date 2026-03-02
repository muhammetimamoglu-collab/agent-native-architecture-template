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
| `{PROJECT_NAME}_docs` | `docs/**` Markdown, YAML, Mermaid | Hook (main) + `refresh_docs_index` MCP tool |
| `{PROJECT_NAME}_code` | Source code under the repo root | Hook (main) only |

Collection names are derived from `PROJECT_NAME` in `.env` (e.g. `my-project_docs`),
so multiple projects can share the same Qdrant instance without collision.

---

## Requirements

- **Python 3.11+** — [python.org/downloads](https://www.python.org/downloads/) (Windows: check "Add to PATH" during install)
- **Docker** (for Qdrant) — [docs.docker.com/get-started/get-docker](https://docs.docker.com/get-started/get-docker/) — or use `QDRANT_URL=:memory:` for ephemeral in-process storage
- **VoyageAI API key** — [dash.voyageai.com](https://dash.voyageai.com/) — or Ollama for local offline embedding

---

## Installation

```bash
# 1. Start Qdrant (from .semantic-search/ directory)
#    REQUIRED if you are running Qdrant locally via Docker.
#    SKIP if you are connecting to a remote Qdrant instance (Qdrant Cloud or self-hosted).
#    → In that case, set QDRANT_URL in .env to your instance URL instead.
cd .semantic-search
docker compose up -d
```

```
# 2. Configure environment
cp .env.example .env
# Open .env and fill in at minimum:
#   PROJECT_NAME=your-repo-name
#   VOYAGE_API_KEY=your-key   (or set EMBEDDER_TYPE=local for Ollama)

# 3. Run the first full index (creates .venv and installs the package automatically)
python .semantic-search/scripts/index.py docs full
python .semantic-search/scripts/index.py code full

# 4. Install the git hook (and optionally configure Claude Code in one step)
python .semantic-search/scripts/install_hook.py           # venv + hooks only
python .semantic-search/scripts/install_hook.py --claude  # + MCP registration + permissions
```

> **`scripts/index.py`** is a cross-platform convenience wrapper — it creates `.venv/`,
> installs the package, and forwards all arguments to the indexer CLI.
> Run it with the system `python` (3.11+); no bash, no venv activation needed.
>
> If you prefer to manage the venv yourself:
> ```
> python -m venv .semantic-search/.venv
> .semantic-search/.venv/Scripts/pip install -e .semantic-search   # Windows
> .semantic-search/.venv/Scripts/index-docs full                   # Windows
> # .semantic-search/.venv/bin/pip install ...                     # Linux / macOS
> ```

---

## MCP Server Registration

### Claude Code (CLI)

Run this command **from the repository root** — it creates `.mcp.json` at the repo root
and the server is only active when Claude Code is opened in this project:

```
# Windows — run from repo root
claude mcp add semantic-search -s project -- C:/path/to/repo/.semantic-search/.venv/Scripts/python.exe -m semantic_search.mcp_server

# Linux / macOS — run from repo root
claude mcp add semantic-search -s project -- /path/to/repo/.semantic-search/.venv/bin/python -m semantic_search.mcp_server
```

Replace `C:/path/to/repo` with the absolute path to your repository root.
`.mcp.json` is gitignored (contains machine-specific paths) — each developer runs this once.

Verify registration:
```
claude mcp list
```

Then reload the Claude Code window (`Ctrl+Shift+P` → **Developer: Reload Window**) and run `/mcp` to confirm the server and its 4 tools are active.

**Allow all 4 tools in `~/.claude/settings.json`** so Claude can call them without prompting:

```json
{
  "permissions": {
    "allow": [
      "mcp__semantic-search__search_codebase",
      "mcp__semantic-search__get_file_chunk",
      "mcp__semantic-search__list_indexed_files",
      "mcp__semantic-search__refresh_docs_index"
    ]
  }
}
```

Merge these into the existing `allow` array — do not replace the entire file.

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "semantic-search": {
      "command": "C:/path/to/repo/.semantic-search/.venv/Scripts/python.exe",
      "args": ["-m", "semantic_search.mcp_server"]
    }
  }
}
```

### Antigravity (Google)

Antigravity currently supports only the global MCP config file located at:

- **Windows:** `%USERPROFILE%\.gemini\antigravity\mcp_config.json`
- **macOS / Linux:** `~/.gemini/antigravity/mcp_config.json`

Add an entry per project using the `SEMANTIC_SEARCH_ENV_FILE` environment variable so each project's server reads its own `.env` (and therefore its own Qdrant collections):

```json
{
  "mcpServers": {
    "semantic-search-my-project": {
      "command": "C:/path/to/repo/.semantic-search/.venv/Scripts/python.exe",
      "args": ["-m", "semantic_search.mcp_server"],
      "env": {
        "SEMANTIC_SEARCH_ENV_FILE": "C:/path/to/repo/.semantic-search/.env"
      }
    }
  }
}
```

Replace `C:/path/to/repo` with the absolute path to your repository root.  
Use a distinct server name per project (e.g. `semantic-search-my-project`) to avoid collisions when multiple projects are registered simultaneously.

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

```
ollama pull nomic-embed-text
# or
ollama pull mxbai-embed-large
```

> **Warning — dimension mismatch**: If you switch between models with different vector sizes
> (e.g. `nomic-embed-text` at 768 vs `mxbai-embed-large` at 1024), you must delete the
> Qdrant collections and run a full re-index:
>
> ```
> # Drop the collections (replace with your actual PROJECT_NAME)
> curl -X DELETE http://localhost:6333/collections/my-project_docs
> curl -X DELETE http://localhost:6333/collections/my-project_code
>
> # Re-index everything with the new model
> python .semantic-search/scripts/index.py docs full --force
> python .semantic-search/scripts/index.py code full --force
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

```
python .semantic-search/scripts/index.py docs delete docs/old/path.md
python .semantic-search/scripts/index.py docs files docs/new/path.md
```

---

## Periodic Full Re-index

For large repos or after significant restructuring, a periodic full re-index ensures
the index stays clean (removes orphaned chunks, refreshes all hashes):

```
python .semantic-search/scripts/index.py docs full --force
python .semantic-search/scripts/index.py code full --force
```

The `--force` flag bypasses hash-check and rewrites all chunks unconditionally.

---

## Verification

```
# Check Qdrant is running
curl http://localhost:6333/readyz

# List collections (should show {PROJECT_NAME}_docs and {PROJECT_NAME}_code)
curl http://localhost:6333/collections

# Smoke test: search for a concept in your docs
python -c "
from semantic_search.embedders import get_embedder
from semantic_search.store import search
from semantic_search.config import settings
e = get_embedder()
print('Collection:', settings.docs_collection)
for r in search(e.embed_query('outbox pattern event publishing'), settings.docs_collection, top_k=3):
    print(r.payload['file_path'], r.score)
"

# Verify hash-skip works (re-index an already-indexed file)
python .semantic-search/scripts/index.py docs files docs/adr/0001-outbox-pattern.sample.md
# Expected: "0 chunks indexed, N skipped (unchanged)"
```
