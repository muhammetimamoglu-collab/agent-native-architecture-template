# AGENT.md

This repository is designed to be used by AI agents. The following rules are mandatory.

## Sample Docs Convention

- Files under `docs/**` ending with `*.sample.*` are example/reference artifacts shipped with the template.
- Treat them as documentation examples unless the user explicitly asks to convert/create real project docs without the `.sample` suffix.

## Authority Order
If artifacts conflict, higher priority wins:

1. `docs/contracts/**`
2. `docs/domain/**`
3. `docs/domain-visual/**`
4. `docs/flows/**`
5. `docs/ui/**`
6. `docs/c4/**`
7. `docs/adr/**`

## Documentation Impact & Architecture Conflict Handling (Mandatory)

When working on a task, determine whether the requested change:

- requires additions or updates in relevant `docs/**` artifacts to stay aligned with their rules, and/or
- conflicts with the architecture or behavior already documented in `docs/**`

Use one combined workflow for both cases (do not duplicate notifications/approval requests if both apply):

- Do not silently skip required documentation updates and do not silently implement conflicting changes.
- Inform the user if the task requires `docs/**` additions/updates and/or if it conflicts with documented architecture, behavior, or boundaries.
- Cite the specific affected or conflicting artifact(s) and section(s) when possible (for example: `docs/domain/**`, `docs/domain-visual/**`, `docs/flows/**`, `docs/c4/**`, `docs/adr/**`).
- Ask for explicit user approval before adding required docs changes to the task scope/plan, and before proceeding with any architecture-divergent implementation.
- If the user approves, include the required documentation updates in the task plan before implementation (for example: flow YAML/diagram, domain/domain-visual, C4, ADR, references).
- Implement the approved documentation updates and code changes together so the repository remains internally consistent.
- If the user does not approve, stay within the currently documented architecture and current task scope, or ask for clarification.

## How to Use Each Artifact

### contracts (SOURCE OF TRUTH)
- Do not invent endpoints, event names, or schemas.
- Implement what contracts declare.

### domain (HARD RULES)
- Invariants must never be violated.
- Transition table defines allowed transitions with triggers.

### domain-visual (STATE MACHINE)
- Allowed transitions must match the state machine.
- Do not introduce new states without updating domain artifacts.

### flows (BEHAVIOR)
- YAML metadata is authoritative for flow intent and behavior boundaries.
- `sideEffects` must be implemented exactly (state changes, events, calls).
- `userStory` is intent only and never overrides domain rules.

### ui (INTENT)
- UI docs describe screens and navigation only.
- `uiNotes` are non-binding hints (placement/visibility/style).
- Never infer business rules from UI documents.

### c4 (STRUCTURE)
- Use C4 docs to understand service boundaries and dependencies.
- C4 does not define flow behavior.

### adr (WHY)
- ADRs explain rationale and constraints behind choices (e.g., Outbox Pattern).
- ADRs do not define new runtime behavior by themselves.

## Linking Convention (Mermaid & Markdown)

Due to GitHub and VS Code renderer limitations:

- Mermaid diagrams **must not contain file links or `click` statements**
- Drill-down nodes include a **reference id** in their label  
  Example: `[REF:ADR:0001] 🔍`
- Actual navigation links are provided **below the diagram as Markdown links**

Agents must:
- read `REF:` markers from Mermaid node labels
- resolve the actual target from the **References** section below the diagram
- never attempt to resolve links from Mermaid syntax itself

## Mermaid Constraints

- `click` is **not used** for navigation
- `sequenceDiagram` contains **no links**
- `flowchart` and C4 diagrams may contain **`REF:` markers only**
- All real links live in Markdown, not in Mermaid

## Semantic Search (MCP)

**If the MCP tool `search_codebase` is available in your session, all steps
in this section are mandatory — not optional. Skipping them is a rule violation.**

If `search_codebase` is not available (plugin not installed or Qdrant not running),
skip this section entirely and proceed with direct file reading.

### Pre-Task Context Retrieval

Before making any code or documentation changes:

1. Call `search_codebase` with a natural language query describing the task.
   - `collection="docs"` — flows, domain rules, contracts, ADRs, C4 (default)
   - `collection="code"` — implementation (functions, classes, configs)
   - `collection="all"` — both collections merged
2. Use `artifact_type` or `language` filters when the domain is already clear.
3. Treat the returned chunks as the primary source for those topics.

### No-Duplication Rule

Files and chunks returned by `search_codebase` must not be re-read or
re-searched manually for the same information. Exclude them from further
investigation. Only read files that were not surfaced by the search.

### Expanding a Result

Use `get_file_chunk` only to expand a specific truncated chunk from a prior
`search_codebase` result. Do not use it to browse files at random.

### Docs Index Refresh

After updating documentation files:

- Do not call `refresh_docs_index` automatically.
- Inform the user which files were updated and ask:
  "Should I refresh the semantic index now?"
- Call `refresh_docs_index` only after explicit user approval,
  passing the list of changed file paths.
