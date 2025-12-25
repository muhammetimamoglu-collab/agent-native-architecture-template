```yaml
flowId: PAY-FINISHED-V1
userStory:
  as: psp
  iWant: notify capture result
  soThat: the merchant updates order status
trigger: psp-webhook
preconditions:
  allowedStates: [AUTHORIZED]
idempotency:
  key: PSP event id or (pspReference + eventType)
sideEffects:
  - state: payment -> FINISHED
  - dbWrite: payments.updated
  - dbWrite: outbox.inserted(payment.finished.v1)
  - event: payment.finished.v1
failures:
  - payment not found
  - duplicate webhook event
raceConditions:
  - capture vs cancel arriving simultaneously
```

```mermaid
flowchart LR
  PSP["PSP [REF:CONTRACT:ASYNCAPI-PAYMENTS] 🔍"]
  P["Payment API [REF:C4:PAYMENT-COMPONENTS] 🔍"]
  B["Event Bus [REF:CONTRACT:ASYNCAPI-PAYMENTS] 🔍"]
  PSP --> P --> B
```

🔍 **References**
- [REF:CONTRACT:ASYNCAPI-PAYMENTS] [AsyncAPI – Payment Events](../contracts/asyncapi.payments.yaml)
- [REF:C4:PAYMENT-COMPONENTS] [Payment API Components](../c4/payment-components.md)

```mermaid
sequenceDiagram
  autonumber
  participant PSP as PSP
  participant P as Payment API
  participant D as Payment DB
  participant O as Outbox
  participant B as Event Bus

  PSP->>P: webhook payment.captured (pspReference, eventId)
  P->>D: Find payment by pspReference
  alt payment not found
    P-->>PSP: 202 Accepted
  else found
    P->>D: Update state -> FINISHED
    P->>O: Insert outbox(payment.finished.v1)
    O->>B: Publish payment.finished.v1
    P-->>PSP: 200 OK
  end
```
