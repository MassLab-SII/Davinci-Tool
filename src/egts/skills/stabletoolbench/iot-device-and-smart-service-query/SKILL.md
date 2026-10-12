# IoT Device and Smart Service Query

## Description

Query IoT, device, sensor, smart-service, and operational status APIs. This skill covers StableToolBench tasks where the API ecosystem includes device status, connected service, sensor, or automation-like data, but the world remains retrieval-only.

## Use Cases

- Retrieve IoT device, sensor, or smart-service status
- Query operational health, device values, or service metadata
- Compare device APIs with similar endpoint names
- Validate ID, label, or object parameters before calling

## Workflow

### Step 1: Identify device or service target
- **Tool**: `get_current_task`
- **Example**: `get_current_task({})`
- **Purpose**: Extract device names, sensor IDs, service labels, health checks, or requested status fields.

### Step 2: Search device candidates
- **Tool**: `search_candidate_apis` × 1-n times
- **Example**: `search_candidate_apis({"query": "iot device sensor service status health", "top_k": 8})`
- **Purpose**: Find APIs related to devices, IoT services, or operational status.

### Step 3: Inspect endpoint schema
- **Tool**: `get_api_schema` × 1-n times
- **Example**: `get_api_schema({"api_key": "Devices::IoTVAS::Get Device"})`
- **Purpose**: Determine required IDs, names, or status parameters.

### Step 4: Call the device API
- **Tool**: `call_api` × 1-n times
- **Example**: `call_api({"api_key": "Devices::IoTVAS::Get Device", "arguments": {"deviceId": "device-1"}})`
- **Purpose**: Retrieve deterministic device or service evidence.

### Step 5: Check call trace
- **Tool**: `get_call_trace`
- **Example**: `get_call_trace({})`
- **Purpose**: Confirm relevance and parameter completeness.

## Tools Involved

`get_current_task`, `search_candidate_apis`, `get_api_schema`, `call_api`, `get_call_trace`

## Tips

- Distinguish service health endpoints from device data endpoints
- Device APIs may use IDs rather than human-readable names
- Use schema defaults when the task uses a placeholder-like example ID
- Do not describe this as a mutation workflow; StableToolBench v1 only retrieves deterministic responses
