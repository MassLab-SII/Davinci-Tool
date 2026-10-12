# Power and Location Management

## Description

Manage device power state (low battery mode) and location services. Toggle low battery mode, enable or disable location services, query the current device location, and handle the cascade effect where low battery mode blocks all other settings changes (cellular, wifi, location). Understand and navigate the state dependency chain: low battery → blocks setting changes → must disable low battery first.

## Use Cases

- Enable low battery mode to conserve power and verify other settings are blocked
- Disable low battery mode to allow settings changes
- Turn location service on to get the current GPS location
- Check whether low battery mode is active before attempting settings changes
- Handle the cascade: low battery on → can't change cellular/wifi/location → disable low battery → retry

## Workflow

### Step 1: Check low battery mode status
- **Tool**: `get_low_battery_mode_status`
- **Example**: `get_low_battery_mode_status({})`
- **Purpose**: Determine whether low battery mode is active. When on, all settings mutations (cellular, wifi, location) will be blocked.

### Step 2: Check location service status
- **Tool**: `get_location_service_status`
- **Example**: `get_location_service_status({})`
- **Purpose**: Query whether location service is currently enabled. Location cannot be retrieved if this is off.

### Step 3: Disable low battery mode if needed
- **Tool**: `set_low_battery_mode_status`
- **Example**: `set_low_battery_mode_status({"status": "off"})`
- **Purpose**: Turn off low battery mode to unblock settings changes. Required if you need to toggle cellular, wifi, or location service while low battery mode is active.

### Step 4: Enable location service
- **Tool**: `set_location_service_status`
- **Example**: `set_location_service_status({"status": "on"})`
- **Purpose**: Turn on location service to allow GPS location retrieval. The `status` parameter must be `"on"` or `"off"`.

### Step 5: Get current location
- **Tool**: `get_current_location`
- **Example**: `get_current_location({})`
- **Purpose**: Retrieve the current device location (city name). This only works if location service is enabled.

### Step 6: Verify location service state
- **Tool**: `get_location_service_status`
- **Example**: `get_location_service_status({})`
- **Purpose**: Confirm the location service status reflects the intended state after set operations.

### Step 7: Enable low battery mode and verify blocking
- **Tool**: `set_low_battery_mode_status` then `set_cellular_service_status`
- **Example**: `set_low_battery_mode_status({"status": "on"})` then `set_cellular_service_status({"status": "on"})`
- **Purpose**: Test the state dependency: enable low battery mode, then attempt a settings change. Observe and report the blocking behavior.

## Tools Involved

`get_low_battery_mode_status`, `set_low_battery_mode_status`, `get_location_service_status`, `set_location_service_status`, `get_current_location`, `get_cellular_service_status`, `set_cellular_service_status`, `get_wifi_status`, `set_wifi_status`

## Tips

- **Critical dependency**: Low battery mode = "on" blocks ALL setting mutations. If a set operation fails unexpectedly, check `get_low_battery_mode_status` first
- To change any setting when low battery is on: disable low battery → change settings → optionally re-enable low battery
- `get_current_location` requires location_service to be "on" — if it fails, enable location service and retry
- Location service status uses `"on"`/`"off"` as string values (same as cellular and wifi)
- When auditing device state, check all four settings together: cellular, wifi, location service, and low battery mode
