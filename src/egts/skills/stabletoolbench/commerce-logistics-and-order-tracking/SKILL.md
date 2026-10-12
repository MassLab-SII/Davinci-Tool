# Commerce Logistics and Order Tracking

## Description

Track packages, retrieve order or product status, and compare commerce or logistics endpoints. This skill targets StableToolBench logistics and eCommerce tasks that often include exact tracking numbers or product identifiers.

## Use Cases

- Track package status by carrier, package ID, reference number, or colis ID
- Retrieve latest event, localization, country, or full tracking history
- Query product, commerce, or marketplace status information
- Compare carrier-specific APIs for multi-carrier tracking tasks

## Workflow

### Step 1: Read identifiers
- **Tool**: `get_current_task`
- **Example**: `get_current_task({})`
- **Purpose**: Extract tracking numbers, order IDs, product names, references, carriers, and requested status fields.

### Step 2: Search logistics or commerce APIs
- **Tool**: `search_candidate_apis` × 1-n times
- **Example**: `search_candidate_apis({"query": "package tracking latest status localization order", "top_k": 8})`
- **Purpose**: Locate APIs for latest tracking status, all events, order lookup, or product data.

### Step 3: Inspect endpoint schemas
- **Tool**: `get_api_schema` × 1-n times
- **Example**: `get_api_schema({"api_key": "Logistics::suivi-colis::Latest"})`
- **Purpose**: Confirm the required tracking ID, reference field, or product parameter.

### Step 4: Call logistics APIs
- **Tool**: `call_api` × 1-n times
- **Example**: `call_api({"api_key": "Logistics::suivi-colis::Latest", "arguments": {"colisId": "CA107308006SI"}})`
- **Purpose**: Retrieve delivery or commerce evidence.

### Step 5: Verify trace relevance
- **Tool**: `get_call_trace`
- **Example**: `get_call_trace({})`
- **Purpose**: Check that the call succeeded and used the correct identifier.

## Tools Involved

`get_current_task`, `search_candidate_apis`, `get_api_schema`, `call_api`, `get_call_trace`

## Tips

- Tracking IDs are usually exact strings; do not normalize or shorten them
- If the task asks latest and all events, inspect and call both endpoint types
- Carrier-specific APIs may use different parameter names for the same package ID
- Use schema defaults only when they match the ID in the user request
