# Multi-API Comparison and Ranking

## Description

Compare multiple APIs for multi-part StableToolBench requests. This skill is useful for G2 and G3 tasks where the user asks for several facts, related entities, or outputs that may require more than one relevant API.

## Use Cases

- Answer a task requiring two or more APIs from the same category
- Compare overlapping APIs and select the strongest evidence source
- Chain API calls for movie, media, logistics, finance, or utility workflows
- Verify that the final trace includes more than one successful API call

## Workflow

### Step 1: Read the user request
- **Tool**: `get_current_task`
- **Example**: `get_current_task({})`
- **Purpose**: Split the request into distinct information needs.

### Step 2: Search for each subgoal
- **Tool**: `search_candidate_apis` × 1-n times
- **Examples**:
  - `search_candidate_apis({"query": "latest package status", "top_k": 5})`
  - `search_candidate_apis({"query": "all package events", "top_k": 5})`
- **Purpose**: Find candidate APIs for each part of the user request.

### Step 3: Inspect schemas before ranking
- **Tool**: `get_api_schema` × 2-n times
- **Example**: `get_api_schema({"api_key": "Movies::Watchmode::Search"})`
- **Purpose**: Compare required parameters, response fields, and API descriptions.

### Step 4: Call the best APIs
- **Tool**: `call_api` × 2-n times
- **Example**: `call_api({"api_key": "Movies::Watchmode::Title Details", "arguments": {"id": "12345"}})`
- **Purpose**: Execute the APIs that cover different subgoals or provide complementary evidence.

### Step 5: Review the chain
- **Tool**: `get_call_trace`
- **Example**: `get_call_trace({})`
- **Purpose**: Check that multiple successful calls were made and avoid relying on only one partial result.

## Tools Involved

`get_current_task`, `search_candidate_apis`, `get_api_schema`, `call_api`, `get_call_trace`

## Tips

- For G2/G3 tasks, assume there may be multiple relevant APIs until schemas prove otherwise
- Prefer complementary APIs over repeated calls to the same endpoint
- Use call trace evidence to explain which API covered which subgoal
- Do not call every candidate; inspect and choose deliberately
