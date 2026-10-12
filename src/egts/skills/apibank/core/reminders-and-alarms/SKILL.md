# Reminders And Alarms

## Description

Manage personal reminders and alarms with authenticated API-Bank tools. This skill covers scheduling, querying, modifying, deleting, and verifying reminder/alarm records.

## Use Cases

- Add reminders for tasks, medication, shopping, travel, or follow-up calls
- Set alarms for events with exact timestamps
- Query reminder and alarm state before making changes
- Modify or delete outdated reminders and alarms

## Workflow

### Step 1: Retrieve token
- **Tool**: `GetUserToken`
- **Example**: `GetUserToken({"username": "John", "password": "123456"})`
- **Purpose**: Reminder and alarm tools require authenticated user context.

### Step 2: Add reminders
- **Tool**: `AddReminder` × 1-n times
- **Example**: `AddReminder({"token": "returned_token", "content": "take blood pressure medicine", "time": "2023-04-01 08:00:00"})`
- **Purpose**: Store actionable reminder records for the selected scenario.

### Step 3: Add alarms
- **Tool**: `AddAlarm` × 1-n times
- **Example**: `AddAlarm({"token": "returned_token", "time": "2023-04-01 07:30:00"})`
- **Purpose**: Create time-only alert records that complement reminders.

### Step 4: Query current reminders and alarms
- **Tool**: `QueryReminder` or `QueryAlarm` × 1-n times
- **Examples**:
  - `QueryReminder({"token": "returned_token", "content": "take blood pressure medicine", "time": "2023-04-01 08:00:00"})`
  - `QueryAlarm({"token": "returned_token", "time": "2023-04-01 07:30:00"})`
- **Purpose**: Confirm created records and collect evidence for later synthesis.

### Step 5: Modify schedules
- **Tool**: `ModifyReminder` or `ModifyAlarm`
- **Examples**:
  - `ModifyReminder({"token": "returned_token", "content": "take blood pressure medicine", "time": "2023-04-01 08:30:00"})`
  - `ModifyAlarm({"token": "returned_token", "from_time": "2023-04-01 07:30:00", "to_time": "2023-04-01 07:45:00"})`
- **Purpose**: Exercise correction and rescheduling patterns.

### Step 6: Delete no-longer-needed records
- **Tool**: `DeleteReminder` or `DeleteAlarm`
- **Examples**:
  - `DeleteReminder({"token": "returned_token", "content": "take blood pressure medicine", "time": "2023-04-01 08:30:00"})`
  - `DeleteAlarm({"token": "returned_token", "time": "2023-04-01 07:45:00"})`
- **Purpose**: Remove obsolete reminders or alarms and trigger a verifiable state change.

### Step 7: Verify final status
- **Tool**: `QueryReminder` or `QueryAlarm` × 1-n times
- **Example**: `QueryReminder({"token": "returned_token", "content": "take blood pressure medicine", "time": "2023-04-01 08:30:00"})`
- **Purpose**: Confirm whether each target record remains, changed, or was deleted.

## Tools Involved

`GetUserToken`, `AddReminder`, `QueryReminder`, `ModifyReminder`, `DeleteReminder`, `AddAlarm`, `QueryAlarm`, `ModifyAlarm`, `DeleteAlarm`

## Tips

- Use reminders for content-rich tasks and alarms for time-only alerts.
- Query after each mutation when possible.
- For multi-step assistant tasks, create more than one reminder/alarm to encourage deeper exploration.
