# Reminder Scheduling

## Description

Create reminders for future events with precise timestamp computation. Get the current time, compute future timestamps using time arithmetic (shift by days, hours, minutes), convert human-readable dates to Unix timestamps, schedule reminders, and verify they appear correctly in the reminder list.

## Use Cases

- Schedule a reminder for a specific date and time (e.g., "tomorrow at 9am")
- Schedule a reminder relative to now (e.g., "in 2 hours")
- Create multiple reminders for a sequence of events
- Verify a scheduled reminder has the correct content and timestamp
- Use datetime components to schedule reminders on specific calendar dates

## Workflow

### Step 1: Get the current timestamp
- **Tool**: `get_current_timestamp`
- **Example**: `get_current_timestamp({})`
- **Purpose**: Obtain the current Unix timestamp as the baseline for relative time calculations.

### Step 2: Compute a future timestamp using shift
- **Tool**: `shift_timestamp`
- **Example**: `shift_timestamp({"timestamp": 1715000000, "days": 1, "hours": 9})`
- **Purpose**: Calculate a future timestamp by adding days/hours/minutes/seconds to the current time. Use this for reminders like "tomorrow at 9am" or "in 2 hours."

### Step 3: Convert a calendar date to timestamp
- **Tool**: `datetime_info_to_timestamp`
- **Example**: `datetime_info_to_timestamp({"year": 2026, "month": 5, "day": 3, "hour": 9, "minute": 0})`
- **Purpose**: Convert a specific calendar date and time (year, month, day, hour, minute, second) into a Unix timestamp. Use this for reminders on specific dates.

### Step 4: Verify the computed time is human-readable
- **Tool**: `timestamp_to_datetime_info`
- **Example**: `timestamp_to_datetime_info({"timestamp": 1715086400})`
- **Purpose**: Convert a timestamp back to datetime components to verify it represents the intended date and time.

### Step 5: Add the reminder
- **Tool**: `add_reminder`
- **Example**: `add_reminder({"content": "Call Alice Johnson", "timestamp": 1715086400})`
- **Purpose**: Create the reminder with the computed timestamp. Returns a reminder object with a unique reminder_id.

### Step 6: Verify the reminder was created
- **Tool**: `search_reminder`
- **Example**: `search_reminder({"query": "Call Alice"})`
- **Purpose**: Search for the newly created reminder to confirm it exists with the correct content and scheduled timestamp.

## Tools Involved

`get_current_timestamp`, `shift_timestamp`, `datetime_info_to_timestamp`, `timestamp_to_datetime_info`, `add_reminder`, `search_reminder`

## Tips

- Always start with `get_current_timestamp` — relative reminders depend on the current time
- `shift_timestamp` is best for relative times ("in N hours/days"); `datetime_info_to_timestamp` is best for absolute dates ("May 3 at 9am")
- When computing "tomorrow at 9am," shift by `{"days": 1}` first, then use `timestamp_to_datetime_info` to check the hour component and adjust if needed
- The `timestamp` parameter for `add_reminder` must be a Unix timestamp (integer), not a datetime string
- Verify the computed timestamp with `timestamp_to_datetime_info` before creating the reminder — it's easy to miscalculate time zone offsets
