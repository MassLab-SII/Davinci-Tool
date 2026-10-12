# Data Validation And Error Recovery

## Description

Perform validate-before-mutate workflows across API-Bank domains. This skill encourages agents to query current state, check tokens and parameters, handle failures, then retry or correct the operation.

## Use Cases

- Check token validity before protected operations
- Query a record before modifying or deleting it
- Recover after missing or mismatched parameters
- Use ToolSearcher to find the correct query or mutation API
- Verify final state after retrying

## Workflow

### Step 1: Search or identify the target API
- **Tool**: `ToolSearcher`
- **Example**: `ToolSearcher({"keywords": "modify reminder query reminder token"})`
- **Purpose**: Determine the query/mutation pair and required parameters.

### Step 2: Validate token
- **Tool**: `GetUserToken` then `CheckToken`
- **Examples**:
  - `GetUserToken({"username": "John", "password": "123456"})`
  - `CheckToken({"token": "returned_token"})`
- **Purpose**: Avoid protected API failures caused by missing or invalid tokens.

### Step 3: Query current state
- **Tool**: `QueryAgenda`, `QueryReminder`, `QueryMeeting`, or `QueryRegistration` × 1-n times
- **Example**: `QueryReminder({"token": "returned_token", "content": "call doctor", "time": "2023-04-01 09:00:00"})`
- **Purpose**: Confirm whether the target record exists and collect exact fields.

### Step 4: Apply corrected mutation
- **Tool**: `ModifyAgenda`, `ModifyReminder`, `ModifyRegistration`, or another mutation API
- **Example**: `ModifyReminder({"token": "returned_token", "content": "call doctor", "time": "2023-04-01 09:30:00"})`
- **Purpose**: Use validated fields to make a targeted state change.

### Step 5: Retry with corrected parameters if needed
- **Tool**: same mutation API × 1-n times
- **Example**: `ModifyRegistration({"appointment_id": "appointment_id_from_query", "new_appointment_date": "2023-04-03"})`
- **Purpose**: Recover from missing IDs, incorrect timestamps, or wrong field values.

### Step 6: Verify final state
- **Tool**: matching query API × 1-n times
- **Example**: `QueryReminder({"token": "returned_token", "content": "call doctor", "time": "2023-04-01 09:30:00"})`
- **Purpose**: Confirm the corrected mutation took effect.

## Tools Involved

`ToolSearcher`, `GetUserToken`, `CheckToken`, `QueryAgenda`, `ModifyAgenda`, `QueryReminder`, `ModifyReminder`, `QueryMeeting`, `QueryRegistration`, `ModifyRegistration`

## Tips

- A failed tool call can still be useful if it leads to a corrected follow-up call.
- Prefer exact query results over guessed IDs or timestamps.
- Always close validation workflows with a query after mutation.
