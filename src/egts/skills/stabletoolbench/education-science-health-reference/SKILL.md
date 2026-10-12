# Education Science Health Reference

## Description

Resolve education, science, health, word, factual reference, and knowledge lookup requests through high-precision API selection. This skill favors careful schema reading because reference APIs often encode the requested concept in a keyword, term, symptom, topic, or identifier parameter.

## Use Cases

- Find definitions, word information, science facts, or educational references
- Query health, symptom, medicine, or fitness-related APIs
- Retrieve ZIP, demographic, or knowledge-base reference data
- Compare educational or scientific APIs with overlapping descriptions

## Workflow

### Step 1: Extract reference topic
- **Tool**: `get_current_task`
- **Example**: `get_current_task({})`
- **Purpose**: Identify the term, symptom, topic, concept, location, or reference object.

### Step 2: Search reference APIs
- **Tool**: `search_candidate_apis` × 1-n times
- **Example**: `search_candidate_apis({"query": "education science health word reference", "top_k": 8})`
- **Purpose**: Locate APIs that return factual or reference-style evidence.

### Step 3: Inspect schema and response type
- **Tool**: `get_api_schema` × 1-n times
- **Example**: `get_api_schema({"api_key": "Education::Words API::Definition"})`
- **Purpose**: Check required query terms and ensure the response template includes the requested evidence.

### Step 4: Call the reference API
- **Tool**: `call_api` × 1-n times
- **Example**: `call_api({"api_key": "Health_and_Fitness::Symptom Checker::Search", "arguments": {"symptom": "headache"}})`
- **Purpose**: Retrieve deterministic educational, scientific, or health reference data.

### Step 5: Verify completeness
- **Tool**: `get_call_trace`
- **Example**: `get_call_trace({})`
- **Purpose**: Confirm that the chosen API matches the reference domain and succeeded.

## Tools Involved

`get_current_task`, `search_candidate_apis`, `get_api_schema`, `call_api`, `get_call_trace`

## Tips

- Keep medical or educational terms exactly as written in the task
- Search both broad domain terms and the specific concept
- Prefer APIs whose response template exposes the requested fact directly
- For multi-part reference tasks, call one API per concept when necessary
