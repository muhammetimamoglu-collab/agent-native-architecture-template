# AGENT.md

This repository is designed to be used by AI agents. The following rules are mandatory.

## Authority Order
If artifacts conflict, higher priority wins:

1. `docs/contracts/**`
2. `docs/domain/**`
3. `docs/domain-visual/**`
4. `docs/flows/**`
5. `docs/ui/**`
6. `docs/c4/**`
7. `docs/adr/**`

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
