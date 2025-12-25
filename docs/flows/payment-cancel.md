```yaml
flowId: PAY-CANCEL-V1
userStory:
  as: customer
  iWant: cancel a payment before completion
  soThat: I am not charged for an unwanted order
trigger: client
endpoint:
  method: POST
  path: /payments/{id}/cancel
preconditions:
  allowedStates: [AUTHORIZED]
idempotency:
  key: Idempotency-Key header
sideEffects:
  - state: payment -> CANCELLED
  - dbWrite: payments.updated
  - dbWrite: outbox.inserted(payment.cancelled.v1)
  - event: payment.cancelled.v1
failures:
  - payment not found
  - invalid state transition
observability:
  log:
    - payment.cancel.requested
    - payment.cancel.completed
  metrics:
    - payment_cancel_total
```

```mermaid
flowchart LR
  C[Client]
  P["Payment API [REF:C4:PAYMENT-COMPONENTS] 🔍"]
  B["Event Bus [REF:CONTRACT:ASYNCAPI-PAYMENTS] 🔍"]

  C --> P --> B
```

🔍 **References**
- [REF:C4:PAYMENT-COMPONENTS] [Payment API Components](../c4/payment-components.md)
- [REF:CONTRACT:ASYNCAPI-PAYMENTS] [AsyncAPI – Payment Events](../contracts/asyncapi.payments.yaml)

```mermaid
sequenceDiagram
  autonumber
  participant C as Client
  participant P as Payment API
  participant D as Payment DB
  participant O as Outbox
  participant B as Event Bus

  C->>P: POST /payments/{id}/cancel (Idempotency-Key)
  P->>D: Validate state (AUTHORIZED)
  P->>D: Update payment state -> CANCELLED
  P->>O: Insert outbox(payment.cancelled.v1)
  O->>B: Publish payment.cancelled.v1
  P-->>C: 200 OK
```
