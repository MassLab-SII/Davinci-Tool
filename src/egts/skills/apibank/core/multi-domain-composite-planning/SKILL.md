# Multi Domain Composite Planning

## Description

Compose multiple API-Bank domains into a realistic assistant workflow. This skill combines tool discovery, authentication, search, finance or health evidence, travel or schedule actions, reminders, and final verification.

## Use Cases

- Plan a day involving health data, appointments, reminders, and agenda
- Combine finance checks with shopping or travel planning
- Use search results to decide what calendar/reminder actions to create
- Build a multi-step assistant plan from several API families

## Workflow

### Step 1: Discover APIs for the composite task
- **Tool**: `ToolSearcher` × 1-n times
- **Example**: `ToolSearcher({"keywords": "health reminder calendar budget hotel"})`
- **Purpose**: Identify relevant tool families before acting.

### Step 2: Authenticate user
- **Tool**: `GetUserToken`
- **Example**: `GetUserToken({"username": "John", "password": "123456"})`
- **Purpose**: Unlock protected planning, finance, calendar, and reminder tools.

### Step 3: Gather domain evidence
- **Tool**: `SearchEngine`, `QueryBalance`, `QueryHealthData`, `SymptomSearch`, or `QueryStock` × 1-n times
- **Example**: `QueryBalance({"token": "returned_token"})`
- **Purpose**: Collect facts that justify later actions.

### Step 4: Perform core domain action
- **Tool**: `BookHotel`, `RecordHealthData`, `AppointmentRegistration`, or another domain API
- **Example**: `RecordHealthData({"user_id": "user_001", "time": "2023-04-01 08:00:00", "health_data": [{"name": "steps", "value": "6500"}]})`
- **Purpose**: Execute the central task-specific action.

### Step 5: Create assistant follow-up
- **Tool**: `AddAgenda` or `AddReminder` × 1-n times
- **Examples**:
  - `AddAgenda({"token": "returned_token", "content": "review health report", "time": "2023-04-02 09:00:00", "location": "home"})`
  - `AddReminder({"token": "returned_token", "content": "pack for hotel trip", "time": "2023-04-09 20:00:00"})`
- **Purpose**: Translate domain evidence into user-facing action items.

### Step 6: Calculate derived values when useful
- **Tool**: `Calculator` × 1-n times
- **Example**: `Calculator({"formula": "6500 + 2000"})`
- **Purpose**: Compute totals, durations, budgets, or progress values.

### Step 7: Verify final state across domains
- **Tool**: `QueryAgenda`, `QueryReminder`, `QueryHealthData`, or relevant query API × 1-n times
- **Example**: `QueryReminder({"token": "returned_token", "content": "pack for hotel trip", "time": "2023-04-09 20:00:00"})`
- **Purpose**: Confirm that the composite workflow produced durable state.

## Tools Involved

`ToolSearcher`, `GetUserToken`, `SearchEngine`, `QueryBalance`, `QueryHealthData`, `SymptomSearch`, `QueryStock`, `BookHotel`, `RecordHealthData`, `AppointmentRegistration`, `AddAgenda`, `AddReminder`, `QueryAgenda`, `QueryReminder`, `Calculator`

## Tips

- Composite trajectories should include at least one evidence-gathering step and one durable state mutation.
- Keep cross-domain actions causally connected; do not call unrelated APIs just for diversity.
- Use follow-up query tools to verify each important mutation.
