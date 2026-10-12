# Connectivity Control

## Description

Manage device radio connectivity: cellular service and wifi. Check current status of each radio, toggle them on or off, verify state changes, and understand how connectivity settings interact with other device functions (messaging requires cellular, location services may depend on connectivity).

## Use Cases

- Check whether cellular and wifi are currently enabled
- Turn cellular on before sending messages or making calls
- Toggle wifi on/off and verify the state change
- Audit all connectivity settings in a single sweep
- Handle the cellular-off error when attempting to send messages

## Workflow

### Step 1: Check cellular status
- **Tool**: `get_cellular_service_status`
- **Example**: `get_cellular_service_status({})`
- **Purpose**: Query whether cellular service is currently on or off. Messages cannot be sent when cellular is off.

### Step 2: Check wifi status
- **Tool**: `get_wifi_status`
- **Example**: `get_wifi_status({})`
- **Purpose**: Query whether wifi is currently on or off.

### Step 3: Enable cellular service
- **Tool**: `set_cellular_service_status`
- **Example**: `set_cellular_service_status({"status": "on"})`
- **Purpose**: Turn cellular on. Required before sending messages. The `status` parameter must be either `"on"` or `"off"`.

### Step 4: Verify cellular state change
- **Tool**: `get_cellular_service_status`
- **Example**: `get_cellular_service_status({})`
- **Purpose**: Confirm the cellular status is now "on" after the set operation.

### Step 5: Toggle wifi
- **Tool**: `set_wifi_status`
- **Example**: `set_wifi_status({"status": "off"})`
- **Purpose**: Turn wifi on or off. The `status` parameter must be either `"on"` or `"off"`.

### Step 6: Verify wifi state change
- **Tool**: `get_wifi_status`
- **Example**: `get_wifi_status({})`
- **Purpose**: Confirm the wifi status reflects the intended change.

### Step 7: Full connectivity audit
- **Tool**: `get_cellular_service_status` + `get_wifi_status`
- **Example**: `get_cellular_service_status({})` then `get_wifi_status({})`
- **Purpose**: Report the complete connectivity state — both cellular and wifi statuses — in a single summary.

## Tools Involved

`get_cellular_service_status`, `set_cellular_service_status`, `get_wifi_status`, `set_wifi_status`

## Tips

- Always check status with `get_*` before calling `set_*` — don't assume the current state
- Set operations return the updated status — use the return value as confirmation
- If `set_cellular_service_status` or `set_wifi_status` fail, check whether low battery mode is active (it blocks settings changes)
- Toggle operations are cheap — if a task requires restoring original state, record the initial status and set it back at the end
- Both `get_*` tools take no parameters (call with `{}`); both `set_*` tools require a `status` parameter of `"on"` or `"off"`
