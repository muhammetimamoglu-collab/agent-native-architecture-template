| From       | To         | Trigger      | Notes |
|------------|------------|--------------|-------|
| CREATED    | AUTHORIZED | authorize    | initial auth |
| AUTHORIZED | FINISHED   | psp-webhook  | capture succeeded |
| AUTHORIZED | CANCELLED  | client       | user requested |