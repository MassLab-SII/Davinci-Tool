# Reminder Lifecycle Management

## Description

Manage the full lifecycle of reminders: create, search, modify, and delete. Create multiple reminders for different times, search and filter the reminder list, modify reminder content or scheduled time, remove completed or obsolete reminders, and verify the final reminder state after each operation.

## Use Cases

- Create multiple reminders and verify all appear in the list
- Update a reminder's time or content (e.g., reschedule a meeting prep)
- Remove reminders that are no longer needed
- Batch cleanup: add several, search all, remove specific ones, verify final state
- Audit reminder list for duplicates or conflicts

## Workflow

### Step 1: Survey existing reminders
- **Tool**: `search_reminder`
- **Example**: `search_reminder({})`
- **Purpose**: Get the baseline list of all reminders with their reminder_id, content, scheduled_timestamp, and created_timestamp.

### Step 2: Create one or more reminders
- **Tool**: `add_reminder`
- **Example**: `add_reminder({"content": "Team standup", "timestamp": 1715100000})`
- **Purpose**: Create new reminders. Each call returns a reminder object with a unique reminder_id — record these IDs for later steps.

### Step 3: Verify creation
- **Tool**: `search_reminder`
- **Example**: `search_reminder({"query": "standup"})`
- **Purpose**: Confirm each new reminder appears in the search results with the correct content and timestamp.

### Step 4: Search by ID
- **Tool**: `search_reminder`
- **Example**: `search_reminder({"reminder_id": "<id>"})`
- **Purpose**: Retrieve a specific reminder by its unique reminder_id to inspect full details before modifying or removing.

### Step 5: Modify a reminder
- **Tool**: `modify_reminder`
- **Example**: `modify_reminder({"reminder_id": "<id>", "content": "Team standup - updated agenda", "timestamp": 1715103600})`
- **Purpose**: Update a reminder's content or scheduled time. At least one of `content` or `timestamp` must be provided.

### Step 6: Verify modification
- **Tool**: `search_reminder`
- **Example**: `search_reminder({"reminder_id": "<id>"})`
- **Purpose**: Confirm the reminder's fields were updated correctly.

### Step 7: Remove a reminder
- **Tool**: `remove_reminder`
- **Example**: `remove_reminder({"reminder_id": "<id>"})`
- **Purpose**: Delete a reminder by its reminder_id. This is irreversible — verify the ID before calling.

### Step 8: Final verification
- **Tool**: `search_reminder`
- **Example**: `search_reminder({})`
- **Purpose**: Confirm the final reminder list — added reminders present, removed ones absent, modified ones updated. Compare counts with the baseline.

## Tools Involved

`search_reminder`, `add_reminder`, `modify_reminder`, `remove_reminder`

## Tips

- Always record the `reminder_id` returned by `add_reminder` — you need it for `modify_reminder` and `remove_reminder`
- `search_reminder({})` with an empty object returns all reminders; use `query` for content substring search or `reminder_id` for exact ID lookup
- When modifying a reminder, you only need to provide the fields that should change
- After removing a reminder, searching by its ID should return empty results — use this as confirmation
- For batch operations, verify the count change: N old + M added - K removed = expected total
