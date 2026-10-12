# Travel Location Weather Planning

## Description

Answer travel, location, weather, restaurant, route, and local-service questions through schema-grounded API calls. This skill is designed for multi-part planning requests where one API may provide location or weather context and another provides travel or service details.

## Use Cases

- Retrieve weather or coordinates for a destination
- Search restaurants, hotels, attractions, or nearby services
- Combine travel status, location, and weather calls
- Handle route, country, or logistics information requests

## Workflow

### Step 1: Extract travel constraints
- **Tool**: `get_current_task`
- **Example**: `get_current_task({})`
- **Purpose**: Identify destination, coordinates, dates, weather needs, restaurant preferences, or travel status details.

### Step 2: Search location and travel APIs
- **Tool**: `search_candidate_apis` × 1-n times
- **Examples**:
  - `search_candidate_apis({"query": "weather coordinates destination", "top_k": 6})`
  - `search_candidate_apis({"query": "nearby restaurants travel hotel location", "top_k": 6})`
- **Purpose**: Find APIs for each planning subgoal.

### Step 3: Inspect required parameters
- **Tool**: `get_api_schema` × 2-n times
- **Example**: `get_api_schema({"api_key": "Weather::Weather API::Current Weather"})`
- **Purpose**: Check whether calls require coordinates, city names, country codes, dates, or radius values.

### Step 4: Call planning APIs
- **Tool**: `call_api` × 2-n times
- **Example**: `call_api({"api_key": "Location::Geocoding::Forward", "arguments": {"address": "Paris"}})`
- **Purpose**: Execute complementary APIs to cover weather, location, travel, or local-service parts.

### Step 5: Verify multi-part completion
- **Tool**: `get_call_trace`
- **Example**: `get_call_trace({})`
- **Purpose**: Confirm that the trace includes all requested travel or location evidence.

## Tools Involved

`get_current_task`, `search_candidate_apis`, `get_api_schema`, `call_api`, `get_call_trace`

## Tips

- For location + weather tasks, call both geocoding and weather APIs when available
- Preserve coordinates, dates, city names, and country codes exactly
- Search restaurant and hotel terms separately if the user asks for both
- G2/G3 tasks often require at least two calls to cover all travel constraints
