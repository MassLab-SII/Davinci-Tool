# Personal Assistant Daily Planning

## Description

Build multi-step assistant workflows that combine token retrieval, today's date, meetings, agenda items, reminders, and alarms. This skill reflects API-Bank's personal assistant scenes.

## Use Cases

- Plan a day with meetings, agenda items, reminders, and alarms
- Query existing schedule before adding new items
- Add multiple reminders for related tasks
- Verify that assistant-created items were stored correctly

## Workflow

### Step 1: Retrieve token and date
- **Tool**: `GetUserToken` and `GetToday`
- **Examples**:
  - `GetUserToken({"username": "John", "password": "123456"})`
  - `GetToday({})`
- **Purpose**: Establish authenticated context and a date anchor for planning.

### Step 2: Inspect current schedule
- **Tool**: `QueryAgenda`, `QueryMeeting`, or `QueryReminder` × 1-n times
- **Example**: `QueryAgenda({"token": "returned_token", "content": "team sync", "time": "2023-04-01 10:00:00", "location": "office"})`
- **Purpose**: Ground the plan in existing state before adding new commitments.

### Step 3: Add meeting
- **Tool**: `AddMeeting`
- **Example**: `AddMeeting({"token": "returned_token", "meeting_topic": "team sync", "start_time": "2023-04-01 10:00:00", "end_time": "2023-04-01 11:00:00", "location": "office", "attendees": ["alice@example.com"]})`
- **Purpose**: Create a structured meeting entry.

### Step 4: Add agenda items
- **Tool**: `AddAgenda` × 1-n times
- **Example**: `AddAgenda({"token": "returned_token", "content": "prepare team sync notes", "time": "2023-04-01 09:00:00", "location": "home"})`
- **Purpose**: Add supporting calendar items around the meeting or task.

### Step 5: Add reminders and alarms
- **Tool**: `AddReminder` or `AddAlarm` × 1-n times
- **Examples**:
  - `AddReminder({"token": "returned_token", "content": "send meeting notes", "time": "2023-04-01 11:15:00"})`
  - `AddAlarm({"token": "returned_token", "time": "2023-04-01 08:30:00"})`
- **Purpose**: Add action-oriented and time-only alerts for the day.

### Step 6: Verify all planned items
- **Tool**: `QueryMeeting`, `QueryAgenda`, or `QueryReminder` × 1-n times
- **Example**: `QueryMeeting({"token": "returned_token", "meeting_topic": "team sync", "start_time": "2023-04-01 10:00:00", "end_time": "2023-04-01 11:00:00", "location": "office", "attendees": ["alice@example.com"]})`
- **Purpose**: Confirm the final daily plan across domains.

## Tools Involved

`GetUserToken`, `GetToday`, `QueryAgenda`, `QueryMeeting`, `QueryReminder`, `AddMeeting`, `AddAgenda`, `AddReminder`, `AddAlarm`

## Tips

- Personal assistant tasks benefit from multiple related mutations rather than one isolated API call.
- Query before and after creation to improve trajectory quality.
- Keep timestamps coherent so the final plan reads like a real day.
