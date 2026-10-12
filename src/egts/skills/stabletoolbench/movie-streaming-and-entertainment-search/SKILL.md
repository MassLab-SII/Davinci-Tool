# Movie Streaming and Entertainment Search

## Description

Resolve movie, streaming availability, entertainment metadata, person lookup, recommendation, and related content requests. StableToolBench has many movie and entertainment APIs, so this skill focuses on separating title search, details lookup, related people, and streaming-link tasks.

## Use Cases

- Find movie or TV details by title, ID, or keyword
- Retrieve streaming availability or watch provider information
- Search related people, recommendations, or similar titles
- Combine movie metadata with media or entertainment APIs in G3 tasks

## Workflow

### Step 1: Read entertainment intent
- **Tool**: `get_current_task`
- **Example**: `get_current_task({})`
- **Purpose**: Identify titles, categories, people, keywords, video IDs, or requested entertainment attributes.

### Step 2: Search movie and streaming APIs
- **Tool**: `search_candidate_apis` × 1-n times
- **Example**: `search_candidate_apis({"query": "movie streaming availability title search recommendation", "top_k": 8})`
- **Purpose**: Find endpoints for search, details, providers, similar titles, or people.

### Step 3: Inspect endpoint schemas
- **Tool**: `get_api_schema` × 1-n times
- **Example**: `get_api_schema({"api_key": "Movies::Streaming Availability::Search"})`
- **Purpose**: Determine whether the API expects a title, ID, category, country, or keyword.

### Step 4: Call relevant endpoints
- **Tool**: `call_api` × 1-n times
- **Example**: `call_api({"api_key": "Movies::Watchmode::Title Search", "arguments": {"search_value": "documentary"}})`
- **Purpose**: Retrieve the requested title, streaming, person, or recommendation information.

### Step 5: Check coverage
- **Tool**: `get_call_trace`
- **Example**: `get_call_trace({})`
- **Purpose**: Confirm that the trace covers each entertainment subrequest.

## Tools Involved

`get_current_task`, `search_candidate_apis`, `get_api_schema`, `call_api`, `get_call_trace`

## Tips

- Use title-search endpoints before details endpoints when only a title or keyword is provided
- For streaming requests, inspect whether country or service parameters are required
- For G3 festival-style tasks, call separate APIs for videos, people, and streaming links
- Do not assume movie APIs share the same ID format
