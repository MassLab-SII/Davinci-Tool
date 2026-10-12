# Data Conversion and Developer Utilities

## Description

Use developer, conversion, generator, validation, URL, code, color, and utility APIs. StableToolBench has many utility-style APIs under Tools and Data, making schema inspection especially important because endpoints often have compact or unusual parameter names.

## Use Cases

- Convert units, formats, colors, URLs, IDs, or structured data
- Generate GUIDs, shorten links, validate inputs, or run code utilities
- Query developer tools such as execution, conversion, or formatter APIs
- Compare several utility APIs with similar descriptions

## Workflow

### Step 1: Identify the utility operation
- **Tool**: `get_current_task`
- **Example**: `get_current_task({})`
- **Purpose**: Determine the exact transformation, generation, validation, or developer utility requested.

### Step 2: Search utility candidates
- **Tool**: `search_candidate_apis` × 1-n times
- **Example**: `search_candidate_apis({"query": "convert generator validator url code utility", "top_k": 8})`
- **Purpose**: Find candidate Tools or Data APIs that perform the requested operation.

### Step 3: Inspect exact parameter names
- **Tool**: `get_api_schema` × 1-n times
- **Example**: `get_api_schema({"api_key": "Tools::GUID generator::Generate"})`
- **Purpose**: Read required input names and output templates before calling.

### Step 4: Execute the utility API
- **Tool**: `call_api` × 1-n times
- **Example**: `call_api({"api_key": "Tools::URL Link Shortener::Shorten", "arguments": {"url": "https://example.com"}})`
- **Purpose**: Produce deterministic utility output with grounded inputs.

### Step 5: Review results
- **Tool**: `get_call_trace`
- **Example**: `get_call_trace({})`
- **Purpose**: Confirm the call was successful and the correct utility endpoint was selected.

## Tools Involved

`get_current_task`, `search_candidate_apis`, `get_api_schema`, `call_api`, `get_call_trace`

## Tips

- Utility APIs often differ by one word; inspect schemas instead of relying on names
- Preserve input strings exactly for validators, URL tools, and code tools
- If the first utility call fails, use the missing-parameter error to retry correctly
- For conversion tasks, check whether source and target units are separate parameters
