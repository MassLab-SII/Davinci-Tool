# Meeting Email Coordination

## Description

Coordinate meetings by creating meeting records, reading user meeting context, looking up organization members, and sending reminder emails. This skill covers Level-3 workplace scheduling and communication workflows.

## Use Cases

- Create a meeting with attendees and location
- Retrieve a user's existing meetings
- Look up organization members to choose attendees
- Send an email reminder for a scheduled meeting

## Workflow

### Step 1: Discover meeting coordination APIs
- **Tool**: `Lv3ToolSearcher`
- **Example**: `Lv3ToolSearcher({"keywords": "meeting schedule query email reminder organization"})`
- **Purpose**: Identify meeting, organization, and email tools.

### Step 2: Get organization members
- **Tool**: `OrganizationMembers`
- **Example**: `OrganizationMembers({"organization": "Alibaba"})`
- **Purpose**: Select grounded attendee names from an organization.

### Step 3: Create a meeting
- **Tool**: `Lv3AddMeeting`
- **Example**: `Lv3AddMeeting({"meeting_topic": "Travel planning sync", "start_time": "2022-01-01 10:00:00", "end_time": "2022-01-01 11:00:00", "location": "Room 1", "attendees": ["John", "Mary"]})`
- **Purpose**: Mutate the Level-3 meeting state by adding a new meeting record.

### Step 4: Query existing meetings
- **Tool**: `Lv3QueryMeeting` × 1-n times
- **Examples**:
  - `Lv3QueryMeeting({"user_name": "John"})`
  - `Lv3QueryMeeting({"user_name": "Mary"})`
- **Purpose**: Gather meeting context for attendees or verify meeting-related information.

### Step 5: Send an email reminder
- **Tool**: `EmailReminder`
- **Example**: `EmailReminder({"content": "Travel planning sync", "time": "2022-01-01 10:00:00", "location": "Room 1", "recipient": "john@example.com"})`
- **Purpose**: Notify a participant about the meeting.

### Step 6: Repeat with another attendee or meeting
- **Tool**: `Lv3AddMeeting`, `Lv3QueryMeeting`, or `EmailReminder` × 1-n times
- **Example**: `Lv3QueryMeeting({"user_name": "Tom"})`
- **Purpose**: Explore additional meeting coordination paths and broaden state coverage.

## Tools Involved

`Lv3ToolSearcher`, `Lv3AddMeeting`, `Lv3QueryMeeting`, `OrganizationMembers`, `EmailReminder`

## Tips

- Use `%Y-%m-%d %H:%M:%S` timestamps for meeting and email reminder times.
- `attendees` must be an array of strings.
- `Lv3AddMeeting` changes local meeting state, while `EmailReminder` records a communication side effect.

