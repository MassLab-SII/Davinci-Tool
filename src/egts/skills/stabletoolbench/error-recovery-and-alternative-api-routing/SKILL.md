# Error Recovery and Alternative API Routing

## Description

Recover from missing parameters, ambiguous API matches, failed calls, or weak API relevance by returning to candidate listing and schema inspection. This skill is important because StableToolBench tasks often include several plausible APIs and compact schemas.

## Use Cases

- Fix a failed call caused by missing required parameters
- Route to another API when the first candidate does not match the user request
- Compare full candidate lists after search returns poor matches
- Produce a trace that demonstrates deliberate recovery rather than blind retries

## Workflow

### Step 1: Read the task and candidate pool
- **Tool**: `get_current_task` and `list_candidate_apis`
- **Examples**:
  - `get_current_task({})`
  - `list_candidate_apis({})`
- **Purpose**: Understand the request and inspect the full available API pool when search results are uncertain.

### Step 2: Search with alternative keywords
- **Tool**: `search_candidate_apis` × 1-n times
- **Examples**:
  - `search_candidate_apis({"query": "latest package status", "top_k": 5})`
  - `search_candidate_apis({"query": "tracking events localization country", "top_k": 5})`
- **Purpose**: Try multiple keyword views of the same request before selecting APIs.

### Step 3: Inspect competing schemas
- **Tool**: `get_api_schema` × 2-n times
- **Example**: `get_api_schema({"api_key": "Logistics::suivi-colis::All"})`
- **Purpose**: Compare parameters and response templates for alternative APIs.

### Step 4: Retry with corrected arguments or route to another API
- **Tool**: `call_api` × 1-n times
- **Example**: `call_api({"api_key": "Logistics::suivi-colis::All", "arguments": {"colisId": "CA107308006SI"}})`
- **Purpose**: Execute the corrected call or use a better-matched API after inspecting schemas.

### Step 5: Verify recovery quality
- **Tool**: `get_call_trace`
- **Example**: `get_call_trace({})`
- **Purpose**: Confirm the final trace has successful calls and does not consist only of invalid attempts.

## Tools Involved

`get_current_task`, `list_candidate_apis`, `search_candidate_apis`, `get_api_schema`, `call_api`, `get_call_trace`

## Tips

- Use `list_candidate_apis` when search misses an obvious domain-specific endpoint
- A missing-parameter error should trigger schema inspection before retrying
- Do not repeatedly call the same API with the same invalid arguments
- Prefer a final trace with at least one successful relevant call and a clear recovery path
