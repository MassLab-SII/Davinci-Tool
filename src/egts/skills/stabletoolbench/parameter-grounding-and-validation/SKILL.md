# Parameter Grounding and Validation

## Description

Ground API arguments from the active user request and candidate schema. This skill focuses on reading required and optional parameter definitions, filling arguments with request evidence or schema defaults, and validating the call trace after execution.

## Use Cases

- Fill IDs, names, ZIP codes, dates, video IDs, symbols, or keywords correctly
- Avoid failed calls caused by missing required parameters
- Use default values from StableToolBench schemas when the query matches them
- Validate parameter completeness after one or more calls

## Workflow

### Step 1: Read the active task
- **Tool**: `get_current_task`
- **Example**: `get_current_task({})`
- **Purpose**: Extract entities, constraints, identifiers, and requested attributes from the task query.

### Step 2: Inspect the API schema
- **Tool**: `get_api_schema` × 1-n times
- **Example**: `get_api_schema({"tool_name": "suivi-colis", "api_name": "Latest"})`
- **Purpose**: Read required parameters, optional parameters, types, defaults, and response shape.

### Step 3: Construct grounded arguments
- **Tool**: `call_api`
- **Example**: `call_api({"tool_name": "suivi-colis", "api_name": "Latest", "arguments": {"colisId": "CA107308006SI"}})`
- **Purpose**: Call the API only after mapping each required parameter to a value from the user request or schema default.

### Step 4: Recover from missing parameters
- **Tool**: `get_api_schema` and `call_api` × 1-n times
- **Example**: `get_api_schema({"api_key": "Finance::Yahoo Finance_v2::Stock History"})`
- **Purpose**: If a call reports missing parameters, re-read the schema and retry with complete arguments.

### Step 5: Verify parameter quality
- **Tool**: `get_call_trace`
- **Example**: `get_call_trace({})`
- **Purpose**: Confirm calls succeeded and the required parameter fill rate is high.

## Tools Involved

`get_current_task`, `get_api_schema`, `call_api`, `get_call_trace`

## Tips

- Treat `required_parameters` as mandatory even when the template response looks simple
- Preserve exact casing for IDs, symbols, and names from the user request
- Optional defaults are useful, but do not invent required values when the request clearly provides them
- A failed first call can still be useful if the retry demonstrates schema-grounded recovery
