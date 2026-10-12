# Organization Travel Status Briefing

## Description

Create an organization status briefing by listing members, checking each member's travel status, optionally retrieving meeting context, and sending an email reminder. This skill covers workplace coordination and team-status workflows.

## Use Cases

- List members of an organization and inspect who is traveling
- Check travel status for several team members
- Retrieve meeting context for a user before sending a reminder
- Send a travel or meeting reminder email after gathering evidence

## Workflow

### Step 1: Search organization tools
- **Tool**: `Lv3ToolSearcher`
- **Example**: `Lv3ToolSearcher({"keywords": "organization members travel status email meeting"})`
- **Purpose**: Discover member lookup, travel status, meeting, and email tools.

### Step 2: Retrieve organization members
- **Tool**: `OrganizationMembers`
- **Example**: `OrganizationMembers({"organization": "Alibaba"})`
- **Purpose**: Get a list of people to inspect.

### Step 3: Check member travel status
- **Tool**: `TravelStatus` × 1-n times
- **Examples**:
  - `TravelStatus({"member_name": "John"})`
  - `TravelStatus({"member_name": "Mary"})`
- **Purpose**: Build a status briefing across multiple members. Repeat for each relevant member.

### Step 4: Retrieve meeting context if needed
- **Tool**: `Lv3QueryMeeting`
- **Example**: `Lv3QueryMeeting({"user_name": "John"})`
- **Purpose**: Gather scheduled meeting evidence for a selected member.

### Step 5: Send reminder
- **Tool**: `EmailReminder`
- **Example**: `EmailReminder({"content": "Travel status briefing is ready", "time": "2022-01-01 09:00:00", "location": "online", "recipient": "john@example.com"})`
- **Purpose**: Create an outward notification based on the gathered briefing.

### Step 6: Validate another organization or member
- **Tool**: `OrganizationMembers` or `TravelStatus` × 1-n times
- **Example**: `OrganizationMembers({"organization": "Tencent"})`
- **Purpose**: Expand or cross-check the briefing across another team.

## Tools Involved

`Lv3ToolSearcher`, `OrganizationMembers`, `TravelStatus`, `Lv3QueryMeeting`, `EmailReminder`

## Tips

- Seeded organizations include `Alibaba`, `Tencent`, `Baidu`, `ByteDance`, and `JD`.
- Travel status is keyed by member name; use names returned by `OrganizationMembers`.
- `EmailReminder` is treated as a side-effect tool even though it does not change a shared database.

