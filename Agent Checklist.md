# Agent Checklist

Use this checklist before generating or reviewing changes.

## Documentation Alignment / Approval
- [ ] Requested change checked against authoritative docs and artifact rules (`contracts`, `domain`, `domain-visual`, `flows`, `ui`, `c4`, `adr`)
- [ ] Determined whether the task requires docs additions/updates and/or conflicts with existing docs
- [ ] If docs additions/updates are required or a conflict exists, user was informed with specific doc references (and proposed docs changes when applicable)
- [ ] Explicit user approval obtained before adding docs changes to the task scope/plan and before any architecture-divergent implementation
- [ ] If approved, required docs updates (e.g., flow/domain/C4/ADR/diagram/reference changes) were added to the task plan
- [ ] Approved docs updates and implementation were applied together and are consistent

## Contracts
- [ ] OpenAPI endpoints referenced match implementation
- [ ] AsyncAPI event names and schemas are used exactly

## Domain
- [ ] Invariants reviewed and enforced
- [ ] State transitions match domain rules and state machine

## Flows
- [ ] Flow YAML parsed successfully
- [ ] Preconditions implemented
- [ ] Idempotency key and strategy implemented (if specified)
- [ ] Side effects implemented as declared (state/db/event/calls/audit)
- [ ] Failures handled as declared
- [ ] Drill-down nodes use `REF:` markers
- [ ] References section exists and all `REF:` ids resolve via Markdown links

## UI
- [ ] UI flows used only for navigation/screen intent
- [ ] uiNotes treated as non-binding suggestions
- [ ] UI diagrams use `REF:` markers 

## C4
- [ ] Service boundaries and dependencies respected
- [ ] No behavior inferred from C4 diagrams
- [ ] C4 diagrams use `REF:` markers

## ADR
- [ ] Relevant ADR constraints applied
- [ ] Superseded ADRs not treated as active decisions
