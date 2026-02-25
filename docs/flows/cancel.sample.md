```yaml
flowId: SAMPLE-CANCEL-V1
userStory:
  as: customer
  iWant: cancel a sample before completion
  soThat: I am not charged for an unwanted order
trigger: client
endpoint:
  method: POST
  path: /samples/{id}/cancel
preconditions:
  allowedStates: [AUTHORIZED]
idempotency:
  key: Idempotency-Key header
sideEffects:
  - state: sample -> CANCELLED
  - dbWrite: samples.updated
  - dbWrite: outbox.inserted(sample.cancelled.v1)
  - event: sample.cancelled.v1
failures:
  - sample not found
  - invalid state transition
observability:
  log:
    - sample.cancel.requested
    - sample.cancel.completed
  metrics:
    - sample_cancel_total
```

```mermaid
flowchart LR
  C[Client]
  P["Sample API [REF:C4:SAMPLE-COMPONENTS] 🔍"]
  B["Event Bus [REF:CONTRACT:ASYNCAPI-SAMPLE] 🔍"]

  C --> P --> B
```

🔍 **References**
- [REF:C4:SAMPLE-COMPONENTS] [Sample API Components](../c4/components.sample.md)
- [REF:CONTRACT:ASYNCAPI-SAMPLE] [AsyncAPI – Sample Events](../contracts/asyncapi.sample.yaml)

```mermaid
sequenceDiagram
  autonumber
  participant C as Client
  participant P as Sample API
  participant D as Sample DB
  participant O as Outbox
  participant B as Event Bus

  C->>P: POST /samples/{id}/cancel (Idempotency-Key)
  P->>D: Validate state (AUTHORIZED)
  P->>D: Update sample state -> CANCELLED
  P->>O: Insert outbox(sample.cancelled.v1)
  O->>B: Publish sample.cancelled.v1
  P-->>C: 200 OK
```
