# Time and Unit Arithmetic

## Description

Perform precise timestamp and unit conversion computations. Get the current Unix timestamp, convert between timestamps and human-readable datetime components, shift timestamps forward or backward by days/hours/minutes/seconds, compute time differences between two timestamps, format durations as hours:minutes:seconds, and convert between measurement units.

## Use Cases

- Calculate what time it will be in N hours or N days
- Convert a calendar date like "May 3, 2026 at 9:00 AM" to a Unix timestamp
- Convert a Unix timestamp back to year/month/day/hour/minute/second for verification
- Compute the time difference between two events
- Convert between units (e.g., kilometers to miles, Celsius to Fahrenheit)

## Workflow

### Step 1: Get the current timestamp
- **Tool**: `get_current_timestamp`
- **Example**: `get_current_timestamp({})`
- **Purpose**: Obtain the current Unix timestamp as the reference point for all relative calculations.

### Step 2: Convert timestamp to human-readable datetime
- **Tool**: `timestamp_to_datetime_info`
- **Example**: `timestamp_to_datetime_info({"timestamp": 1715000000})`
- **Purpose**: Decompose a Unix timestamp into year, month, day, hour, minute, second. Essential for verifying computed timestamps represent the intended date and time.

### Step 3: Convert datetime components to timestamp
- **Tool**: `datetime_info_to_timestamp`
- **Example**: `datetime_info_to_timestamp({"year": 2026, "month": 5, "day": 3, "hour": 9, "minute": 0, "second": 0})`
- **Purpose**: Build a Unix timestamp from calendar components. Hour, minute, and second default to 0 if omitted.

### Step 4: Shift a timestamp forward or backward
- **Tool**: `shift_timestamp`
- **Example**: `shift_timestamp({"timestamp": 1715000000, "days": 3, "hours": 0, "minutes": 0, "seconds": 0})`
- **Purpose**: Add or subtract time from a timestamp. All shift parameters are optional and default to 0. Use positive values to move forward, negative to move backward.

### Step 5: Verify the shifted result
- **Tool**: `timestamp_to_datetime_info`
- **Example**: `timestamp_to_datetime_info({"timestamp": 1715259200})`
- **Purpose**: Convert the shifted timestamp back to datetime components to confirm it's 3 days later than the original.

### Step 6: Compute the difference between two timestamps
- **Tool**: `timestamp_diff`
- **Example**: `timestamp_diff({"timestamp1": 1715259200, "timestamp2": 1715000000})`
- **Purpose**: Calculate the number of seconds between two timestamps (timestamp1 - timestamp2).

### Step 7: Format a duration
- **Tool**: `seconds_to_hours_minutes_seconds`
- **Example**: `seconds_to_hours_minutes_seconds({"seconds": 259200})`
- **Purpose**: Convert a raw seconds count into a human-readable "Xh Ym Zs" format string.

### Step 8: Convert between measurement units
- **Tool**: `unit_conversion`
- **Example**: `unit_conversion({"value": 100, "from_unit": "km", "to_unit": "miles"})`
- **Purpose**: Convert a numerical value from one unit to another. Supported units include length (km, miles, m, ft), temperature (celsius, fahrenheit), and weight (kg, lbs).

## Tools Involved

`get_current_timestamp`, `timestamp_to_datetime_info`, `datetime_info_to_timestamp`, `shift_timestamp`, `timestamp_diff`, `seconds_to_hours_minutes_seconds`, `unit_conversion`

## Tips

- All time arithmetic tools are read-only — they don't change world state, only perform computations
- `shift_timestamp` is the primary tool for "what time will it be in X hours/days" — use positive values for future, negative for past
- Always use `timestamp_to_datetime_info` to verify computed timestamps before using them in other operations (e.g., before creating a reminder)
- `datetime_info_to_timestamp` treats the input as local time — be aware when coordinating across time zones
- Chain operations: get current time → shift → convert to datetime → use the result for another shift or diff
- When computing "9am in a timezone 8 hours ahead," shift the current timestamp by 8 hours, then use `timestamp_to_datetime_info` to check the result
