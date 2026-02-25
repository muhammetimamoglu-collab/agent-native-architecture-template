```yaml
uiFlowId: UI-SAMPLE-CREATE-V1
domain: sample
actors: [customer]
goal: create and complete sample
relatedFlows: [SAMPLE-FINISHED-V1, SAMPLE-CANCEL-V1]
uiNotes:
  amount:
    intent: guide valid input
    suggestion:
      placement: below-input
      visibility: on-focus
      style: helper-text
  payButton:
    intent: prevent premature submission
    suggestion:
      placement: inline
      visibility: until-form-valid
      style: disabled-primary
  cancelButton:
    intent: allow user to exit without charge
    suggestion:
      placement: inline
      visibility: always
      style: secondary
```

```mermaid
flowchart LR
  Create["Create Sample Screen [REF:FLOW:SAMPLE-CANCEL-V1] 🔍<br/><br/>Inputs:<br/>• Amount : number<br/>• Currency : select<br/><br/>Actions:<br/>• Pay<br/>• Cancel"]
  Processing["Processing Screen<br/>• Spinner"]
  Success["Success Screen<br/>• Done"]
  Failure["Failure Screen<br/>• Retry / Cancel"]

  Create -->|Pay| Processing -->|sample finished| Success
  Processing -->|sample failed| Failure
  Create -->|Cancel| Failure
```

🔍 **References**
- [REF:FLOW:SAMPLE-CANCEL-V1] [Flow – Sample Cancel](../flows/cancel.sample.md)
