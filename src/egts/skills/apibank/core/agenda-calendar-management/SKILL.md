# Agenda Calendar Management

## Description

Create, query, update, and delete agenda items using authenticated API-Bank account tokens. This skill covers calendar planning workflows with content, time, and location fields.

## Use Cases

- Add a calendar entry for a meeting, appointment, trip, or personal task
- Query an agenda item before editing or deleting it
- Modify time, location, or content for an existing agenda entry
- Delete an obsolete agenda item and verify it is gone

## Workflow

### Step 1: Retrieve a token
- **Tool**: `GetUserToken`
- **Example**: `GetUserToken({"username": "John", "password": "123456"})`
- **Purpose**: Agenda APIs are token-protected, so a valid token is required before mutation or lookup.

### Step 2: Ground the current date if needed
- **Tool**: `GetToday`
- **Example**: `GetToday({})`
- **Purpose**: Use the benchmark date as an anchor when constructing agenda timestamps.

### Step 3: Add agenda entries
- **Tool**: `AddAgenda` × 1-n times
- **Example**: `AddAgenda({"token": "returned_token", "content": "doctor appointment", "time": "2023-04-02 09:00:00", "location": "City Hospital"})`
- **Purpose**: Create one or more concrete calendar records in the episode state.

### Step 4: Query agenda evidence
- **Tool**: `QueryAgenda` × 1-n times
- **Example**: `QueryAgenda({"token": "returned_token", "content": "doctor appointment", "time": "2023-04-02 09:00:00", "location": "City Hospital"})`
- **Purpose**: Verify that an added or existing agenda entry is visible before further action.

### Step 5: Modify agenda entries
- **Tool**: `ModifyAgenda`
- **Example**: `ModifyAgenda({"token": "returned_token", "content": "doctor appointment", "time": "2023-04-02 10:00:00", "location": "City Hospital"})`
- **Purpose**: Update an agenda record to exercise mutation beyond simple creation.

### Step 6: Delete obsolete entries
- **Tool**: `DeleteAgenda`
- **Example**: `DeleteAgenda({"token": "returned_token", "content": "doctor appointment", "time": "2023-04-02 10:00:00", "location": "City Hospital"})`
- **Purpose**: Remove a calendar item when the task requires cleanup or conflict resolution.

### Step 7: Verify final state
- **Tool**: `QueryAgenda` × 1-n times
- **Example**: `QueryAgenda({"token": "returned_token", "content": "doctor appointment", "time": "2023-04-02 10:00:00", "location": "City Hospital"})`
- **Purpose**: Confirm the agenda item is present, updated, or absent according to the workflow.

## Tools Involved

`GetUserToken`, `GetToday`, `AddAgenda`, `QueryAgenda`, `ModifyAgenda`, `DeleteAgenda`

## Tips

- Keep `content`, `time`, and `location` consistent across add/query/delete calls.
- Use exact timestamp format `%Y-%m-%d %H:%M:%S`.
- Query both before and after mutation when possible; this creates stronger state-grounded trajectories.
