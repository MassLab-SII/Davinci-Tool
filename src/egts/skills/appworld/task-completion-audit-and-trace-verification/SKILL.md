# Task Completion Audit And Trace Verification

## Description

Audit trajectories with follow-up reads, call-trace inspection, and task-grounded evidence before stopping.

## Use Cases

- Explore AppWorld through the stable EGTS meta-tools rather than exposing hundreds of raw app APIs.
- Build grounded trajectories that include task/context reading, API discovery, schema inspection, execution, and verification.
- Capture both retrieval and mutation evidence while keeping AppWorld state resettable and observable.

## Workflow

### Step 1: Read the active AppWorld context
- **Tool**: `get_current_task`
- **Example**: `get_current_task({})`
- **Purpose**: Read the active task, available apps, datetime, and app descriptions before choosing APIs.

### Step 2: Survey or search candidate APIs
- **Tool**: `search_appworld_apis` × 1-n times
- **Example**: `search_appworld_apis({"query": "login create update verify", "limit": 10})`
- **Purpose**: Locate AppWorld APIs whose names, descriptions, or schemas match the intended workflow.

### Step 3: Inspect exact schemas
- **Tool**: `get_appworld_api_schema` × 1-n times
- **Example**: `get_appworld_api_schema({"api_name": "spotify__search_songs"})`
- **Purpose**: Read required parameters, optional filters, access-token requirements, and response shape before calling.

### Step 4: Execute a grounded AppWorld API call
- **Tool**: `call_appworld_api` × 1-n times
- **Example**: `call_appworld_api({"api_name": "spotify__search_songs", "arguments": {"query": "jazz"}})`
- **Purpose**: Call the selected benchmark API with arguments grounded in the task, schema, or previous response.

### Step 5: Verify with follow-up evidence
- **Tool**: `call_appworld_api` or `get_call_trace` × 1-n times
- **Example**: `get_call_trace({"limit": 10})`
- **Purpose**: Confirm successful calls, inspect response previews, and verify whether state changed when mutation was intended.

### Step 6: Repair or deepen the trajectory
- **Tool**: `search_appworld_apis`, `get_appworld_api_schema`, or `call_appworld_api` × 1-n times
- **Example**: `search_appworld_apis({"query": "show verify created record"})`
- **Purpose**: If the first call is insufficient or fails, find a safer API, repair arguments, or add a read-back call.

## Tools Involved

`get_current_task`, `search_appworld_apis`, `get_appworld_api_schema`, `call_appworld_api`, `get_call_trace`

## Tips

- Prefer schema inspection before any unfamiliar `call_appworld_api` invocation.
- Use `get_call_trace` to audit whether calls succeeded and whether a mutation actually changed AppWorld state.
- For deeper exploration, repeat search/schema/call steps with related APIs rather than stopping after one read.
- Keep API names exact; if a name is uncertain, search or list APIs again instead of hallucinating it.
