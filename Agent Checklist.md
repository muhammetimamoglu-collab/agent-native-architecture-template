# Agent Checklist

Use this checklist before generating or reviewing changes.

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