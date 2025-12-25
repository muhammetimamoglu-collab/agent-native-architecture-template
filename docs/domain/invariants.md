# Domain Invariants

- FINISHED payments cannot be cancelled.
- Payment amount is immutable after creation.
- Every state change must produce a domain event (via outbox).