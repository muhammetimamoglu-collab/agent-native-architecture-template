```yaml
view: c4-container
system: payment
```

```mermaid
flowchart LR
  Client[Client]
  Pay["Payment API [REF:C4:PAYMENT-COMPONENTS] 🔍"]
  DB[(Payment DB)]
  Bus["Event Bus [REF:CONTRACT:ASYNCAPI-PAYMENTS] 🔍"]
  PSP["PSP [REF:CONTRACT:ASYNCAPI-PAYMENTS] 🔍"]

  Client --> Pay --> DB
  Pay --> Bus
  PSP --> Pay
```

🔍 **References**
- [REF:C4:PAYMENT-COMPONENTS] [Payment API Components](payment-components.md)
- [REF:CONTRACT:ASYNCAPI-PAYMENTS] [AsyncAPI – Payment Events](../contracts/asyncapi.payments.yaml)