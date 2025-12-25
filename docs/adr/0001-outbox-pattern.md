# ADR-0001: Outbox Pattern

## Status
Accepted

## Context
We need to publish domain events reliably without losing consistency between database state and emitted events.

## Decision
Publish domain events via an Outbox table and a separate publisher process.

## Rationale
Guarantees consistency between database state and emitted events. Avoids “DB commit succeeded but event publish failed” gaps.

## Consequences
- Additional Outbox table and publisher component
- Slight publish delay is possible
- Consumers must rely on event delivery semantics (at-least-once is common)
