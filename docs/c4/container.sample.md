```yaml
view: c4-container
system: sample
```

```mermaid
flowchart LR
  Client[Client]
  Pay["Sample API [REF:C4:SAMPLE-COMPONENTS] 🔍"]
  DB[(Sample DB)]
  Bus["Event Bus [REF:CONTRACT:ASYNCAPI-SAMPLE] 🔍"]
  PSP["PSP [REF:CONTRACT:ASYNCAPI-SAMPLE] 🔍"]

  Client --> Pay --> DB
  Pay --> Bus
  PSP --> Pay
```

🔍 **References**
- [REF:C4:SAMPLE-COMPONENTS] [Sample API Components](components.sample.md)
- [REF:CONTRACT:ASYNCAPI-SAMPLE] [AsyncAPI – Sample Events](../contracts/asyncapi.sample.yaml)
