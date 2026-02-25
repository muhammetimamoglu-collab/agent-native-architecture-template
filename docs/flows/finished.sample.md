```yaml
flowId: SAMPLE-FINISHED-V1
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
  - state: sample -> FINISHED
  - dbWrite: samples.updated
  - dbWrite: outbox.inserted(sample.finished.v1)
  - event: sample.finished.v1
failures:
  - sample not found
  - duplicate webhook event
raceConditions:
  - capture vs cancel arriving simultaneously
```

```mermaid
flowchart LR
  PSP["PSP [REF:CONTRACT:ASYNCAPI-SAMPLE] 🔍"]
  P["Sample API [REF:C4:SAMPLE-COMPONENTS] 🔍"]
  B["Event Bus [REF:CONTRACT:ASYNCAPI-SAMPLE] 🔍"]
  PSP --> P --> B
```

🔍 **References**
- [REF:CONTRACT:ASYNCAPI-SAMPLE] [AsyncAPI – Sample Events](../contracts/asyncapi.sample.yaml)
- [REF:C4:SAMPLE-COMPONENTS] [Sample API Components](../c4/components.sample.md)

```mermaid
sequenceDiagram
  autonumber
  participant PSP as PSP
  participant P as Sample API
  participant D as Sample DB
  participant O as Outbox
  participant B as Event Bus

  PSP->>P: webhook sample.captured (pspReference, eventId)
  P->>D: Find sample by pspReference
  alt sample not found
    P-->>PSP: 202 Accepted
  else found
    P->>D: Update state -> FINISHED
    P->>O: Insert outbox(sample.finished.v1)
    O->>B: Publish sample.finished.v1
    P-->>PSP: 200 OK
  end
```
