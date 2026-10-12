# Meeting Scheduling Coordination

## Description

Coordinate meetings with topic, start/end time, location, attendees, and optional email notification. This skill targets API-Bank meeting management workflows.

## Use Cases

- Schedule a meeting with multiple attendees
- Query an existing meeting before modifying it
- Change meeting details after a conflict or update
- Delete an obsolete meeting
- Send a meeting-related email notification

## Workflow

### Step 1: Retrieve token
- **Tool**: `GetUserToken`
- **Example**: `GetUserToken({"username": "John", "password": "123456"})`
- **Purpose**: Meeting tools require authenticated user context.

### Step 2: Create meeting
- **Tool**: `AddMeeting` × 1-n times
- **Example**: `AddMeeting({"token": "returned_token", "meeting_topic": "project sync", "start_time": "2023-04-03 14:00:00", "end_time": "2023-04-03 15:00:00", "location": "Room 301", "attendees": ["alice@example.com", "bob@example.com"]})`
- **Purpose**: Add one or more meetings with structured attendee lists.

### Step 3: Query meeting evidence
- **Tool**: `QueryMeeting` × 1-n times
- **Example**: `QueryMeeting({"token": "returned_token", "meeting_topic": "project sync", "start_time": "2023-04-03 14:00:00", "end_time": "2023-04-03 15:00:00", "location": "Room 301", "attendees": ["alice@example.com", "bob@example.com"]})`
- **Purpose**: Verify meeting existence and capture exact state.

### Step 4: Send notification if useful
- **Tool**: `SendEmail`
- **Example**: `SendEmail({"receiver": "alice@example.com", "subject": "Project sync", "content": "The meeting is scheduled for 2023-04-03 14:00 in Room 301."})`
- **Purpose**: Connect meeting state with communication actions.

### Step 5: Modify meeting details
- **Tool**: `ModifyMeeting`
- **Example**: `ModifyMeeting({"token": "returned_token", "meeting_topic": "project sync", "start_time": "2023-04-03 15:00:00", "end_time": "2023-04-03 16:00:00", "location": "Room 401", "attendees": ["alice@example.com", "bob@example.com"]})`
- **Purpose**: Exercise rescheduling and location-change workflows.

### Step 6: Delete canceled meetings
- **Tool**: `DeleteMeeting`
- **Example**: `DeleteMeeting({"token": "returned_token", "meeting_topic": "project sync", "start_time": "2023-04-03 15:00:00", "end_time": "2023-04-03 16:00:00", "location": "Room 401", "attendees": ["alice@example.com", "bob@example.com"]})`
- **Purpose**: Remove meeting records when the task requires cancellation.

### Step 7: Verify final meeting state
- **Tool**: `QueryMeeting` × 1-n times
- **Example**: `QueryMeeting({"token": "returned_token", "meeting_topic": "project sync", "start_time": "2023-04-03 15:00:00", "end_time": "2023-04-03 16:00:00", "location": "Room 401", "attendees": ["alice@example.com", "bob@example.com"]})`
- **Purpose**: Confirm the meeting has been created, updated, or deleted.

## Tools Involved

`GetUserToken`, `AddMeeting`, `QueryMeeting`, `ModifyMeeting`, `DeleteMeeting`, `SendEmail`

## Tips

- The `attendees` parameter must be an array of strings.
- Keep topic/time/location/attendees aligned across add/query/delete calls.
- Send email only after the meeting state is known; it is a side-effect action, not a source of meeting truth.
