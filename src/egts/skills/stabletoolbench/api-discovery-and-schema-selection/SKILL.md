# API Discovery and Schema Selection

## Description

Discover the active StableToolBench user request, search the current candidate API pool, inspect schemas, and select the API that best matches the information need before making a call. This skill is the default workflow for StableToolBench because every episode exposes a different candidate API set.

## Use Cases

- Find the right API for a package, movie, finance, sports, or utility query
- Compare several similarly named APIs before selecting one
- Ground API selection in schema descriptions instead of guessing from tool names
- Produce a trace that shows why a chosen API was relevant

## Workflow

### Step 1: Read the active task
- **Tool**: `get_current_task`
- **Example**: `get_current_task({})`
- **Purpose**: Get the user request, task group, query ID, and candidate API count before searching.

### Step 2: Search candidate APIs
- **Tool**: `search_candidate_apis` × 1-n times
- **Example**: `search_candidate_apis({"query": "package latest status localization", "top_k": 5})`
- **Purpose**: Retrieve candidate APIs that match the task terms. Repeat with alternative keywords when the first search is broad or ambiguous.

### Step 3: Inspect likely schemas
- **Tool**: `get_api_schema` × 1-n times
- **Example**: `get_api_schema({"api_key": "Logistics::suivi-colis::Latest"})`
- **Purpose**: Check descriptions, required parameters, defaults, and response templates before selecting the final API.

### Step 4: Call the selected API
- **Tool**: `call_api`
- **Example**: `call_api({"api_key": "Logistics::suivi-colis::Latest", "arguments": {"colisId": "CA107308006SI"}})`
- **Purpose**: Execute the API with arguments grounded in the user request or schema defaults.

### Step 5: Verify the trace
- **Tool**: `get_call_trace`
- **Example**: `get_call_trace({})`
- **Purpose**: Confirm the called API succeeded and that the trace records a relevant, parameter-complete call.

## Tools Involved

`get_current_task`, `search_candidate_apis`, `get_api_schema`, `call_api`, `get_call_trace`

## Tips

- Search by user intent first, then by category or entity name if needed
- Prefer the API whose required parameters can be grounded directly from the request
- Use `api_key` from search or list results to avoid ambiguous API matches
- StableToolBench is retrieval-only; quality comes from relevance and parameter completeness, not state mutation
