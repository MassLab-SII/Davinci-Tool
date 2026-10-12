# Cross-Domain Orchestration

## Description

Execute complex multi-domain workflows that span contacts, messaging, reminders, device settings, and time utilities. Typical patterns include: find a contact → check cellular → send a message → schedule a follow-up reminder. Or: audit all state → make changes in each domain → re-audit and report differences. These workflows test the agent's ability to maintain context across many state changes and coordinate operations across independent domains.

## Use Cases

- Find a contact, send them a message, and set a reminder for follow-up
- Audit all domains (contacts, messages, reminders, settings), make one change in each, and re-audit
- Coordinate a multi-person event: message each attendee and schedule reminders
- Timezone-aware planning: compute remote time, schedule reminder, notify contacts
- Full contact lifecycle with messaging: add contact → send welcome message → schedule check-in reminder

## Workflow

### Step 1: Survey all domain state
- **Tool**: `search_contacts`, `get_cellular_service_status`, `get_wifi_status`, `search_messages`, `search_reminder`
- **Examples**:
  - `search_contacts({})`
  - `get_cellular_service_status({})`
  - `search_messages({})`
  - `search_reminder({})`
- **Purpose**: Establish a baseline across all four domains before making changes. Record counts and key IDs.

### Step 2: Ensure prerequisites are met
- **Tool**: `get_cellular_service_status`, `set_cellular_service_status`, `get_low_battery_mode_status`
- **Examples**:
  - `get_cellular_service_status({})`
  - `set_cellular_service_status({"status": "on"})`
- **Purpose**: Check and fix any blocking conditions. Cellular must be on to send messages. If low battery mode is on, disable it before changing settings.

### Step 3: Look up target contacts
- **Tool**: `search_contacts`
- **Example**: `search_contacts({"query": "Carol"})`
- **Purpose**: Find the contacts involved in the workflow. Extract their phone numbers for messaging.

### Step 4: Send messages
- **Tool**: `send_message_with_phone_number`
- **Example**: `send_message_with_phone_number({"phone_number": "+1-555-0103", "content": "Family dinner this Sunday at 6pm"})`
- **Purpose**: Send messages to the target contacts. If sending to multiple contacts, repeat for each one.

### Step 5: Verify messages were sent
- **Tool**: `search_messages`
- **Example**: `search_messages({"phone_number": "+1-555-0103"})`
- **Purpose**: Confirm each message appears in the message history.

### Step 6: Compute future timestamps for reminders
- **Tool**: `get_current_timestamp`, `shift_timestamp`, `datetime_info_to_timestamp`
- **Examples**:
  - `get_current_timestamp({})`
  - `shift_timestamp({"timestamp": 1715000000, "days": 1})`
  - `datetime_info_to_timestamp({"year": 2026, "month": 5, "day": 4, "hour": 17})`
- **Purpose**: Calculate the correct Unix timestamps for follow-up reminders.

### Step 7: Schedule reminders
- **Tool**: `add_reminder`
- **Example**: `add_reminder({"content": "Prepare for family dinner", "timestamp": 1715259200})`
- **Purpose**: Create reminders linked to the messages sent. Use meaningful content that references the original task.

### Step 8: Verify reminders
- **Tool**: `search_reminder`
- **Example**: `search_reminder({"query": "dinner"})`
- **Purpose**: Confirm all reminders were created with correct content and timestamps.

### Step 9: Make additional domain changes as required
- **Tool**: `add_contact`, `set_wifi_status`, `get_current_location`, etc.
- **Examples**:
  - `add_contact({"name": "New Contact", "phone_number": "+1-555-0300"})`
  - `set_wifi_status({"status": "off"})`
- **Purpose**: Execute any additional domain-specific operations required by the task.

### Step 10: Final cross-domain re-audit
- **Tool**: `search_contacts`, `search_messages`, `search_reminder`, `get_cellular_service_status`, `get_wifi_status`
- **Examples**:
  - `search_contacts({})`
  - `search_messages({})`
  - `search_reminder({})`
  - `get_cellular_service_status({})`
- **Purpose**: Re-audit all domains to verify every change was applied correctly. Report before/after counts for each domain and summarize what changed.

## Tools Involved

`search_contacts`, `add_contact`, `modify_contact`, `remove_contact`, `get_cellular_service_status`, `set_cellular_service_status`, `get_wifi_status`, `set_wifi_status`, `get_location_service_status`, `set_location_service_status`, `get_low_battery_mode_status`, `set_low_battery_mode_status`, `get_current_location`, `send_message_with_phone_number`, `search_messages`, `add_reminder`, `modify_reminder`, `remove_reminder`, `search_reminder`, `get_current_timestamp`, `shift_timestamp`, `datetime_info_to_timestamp`, `timestamp_to_datetime_info`

## Tips

- **Audit first, act second, verify last**: Always survey state before changes and re-audit all touched domains after
- Track counts per domain: N contacts before → N±X after; M messages before → M±Y after
- Handle state dependencies proactively: check cellular before messaging, check low battery before changing settings
- When operating across 3+ domains, process them in dependency order: settings first (enable prerequisites) → contacts (look up) → messaging (send) → reminders (schedule)
- If a step fails partway through a cross-domain workflow, report which domains were modified and which were not
- Cross-domain tasks typically require 10-20 tool calls — plan the sequence before starting and track progress against the plan
