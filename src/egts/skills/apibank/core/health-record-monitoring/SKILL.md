# Health Record Monitoring

## Description

Record and query health data, then create reminders or alarms based on observed health-management needs. This skill is grounded in API-Bank health management and Level-3 health scenes.

## Use Cases

- Record health measurements for a user
- Query health data over a time range
- Add medication, exercise, or checkup reminders
- Set alarms for repeated health routines
- Combine symptom search with record monitoring

## Workflow

### Step 1: Search symptom context when useful
- **Tool**: `SymptomSearch` or `EmergencyKnowledge`
- **Example**: `SymptomSearch({"symptom": "high blood pressure"})`
- **Purpose**: Ground the health-management reason before recording or scheduling follow-up.

### Step 2: Record health data
- **Tool**: `RecordHealthData` × 1-n times
- **Example**: `RecordHealthData({"user_id": "user_001", "time": "2023-04-01 08:00:00", "health_data": [{"name": "blood_pressure", "value": "135/88"}]})`
- **Purpose**: Add one or more health observations to the API-Bank state.

### Step 3: Query health range
- **Tool**: `QueryHealthData` × 1-n times
- **Example**: `QueryHealthData({"user_id": "user_001", "start_time": "2023-04-01 00:00:00", "end_time": "2023-04-07 23:59:59"})`
- **Purpose**: Verify recorded data and collect evidence for trends or follow-up.

### Step 4: Retrieve token for planning tools
- **Tool**: `GetUserToken`
- **Example**: `GetUserToken({"username": "John", "password": "123456"})`
- **Purpose**: Obtain token before creating reminders or alarms.

### Step 5: Create health reminders
- **Tool**: `AddReminder` × 1-n times
- **Example**: `AddReminder({"token": "returned_token", "content": "measure blood pressure", "time": "2023-04-02 08:00:00"})`
- **Purpose**: Store actionable follow-up based on health data.

### Step 6: Create alarms
- **Tool**: `AddAlarm` × 1-n times
- **Example**: `AddAlarm({"token": "returned_token", "time": "2023-04-02 07:50:00"})`
- **Purpose**: Add time-only alerts for recurring health routines.

### Step 7: Verify health and reminder state
- **Tool**: `QueryHealthData` or `QueryReminder` × 1-n times
- **Example**: `QueryReminder({"token": "returned_token", "content": "measure blood pressure", "time": "2023-04-02 08:00:00"})`
- **Purpose**: Confirm both recorded health evidence and planned follow-up.

## Tools Involved

`SymptomSearch`, `EmergencyKnowledge`, `RecordHealthData`, `QueryHealthData`, `GetUserToken`, `AddReminder`, `AddAlarm`, `QueryReminder`

## Tips

- `health_data` must be an array; include structured measurement names and values.
- Query a range that includes the recorded timestamp.
- Follow health mutations with reminders or alarms to create richer multi-tool trajectories.
