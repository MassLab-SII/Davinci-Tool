# Sports Events and Statistics Query

## Description

Query sports teams, players, careers, schedules, transfers, statistics, standings, and event facts. This skill helps agents map sports-language requests to APIs whose schemas may use team IDs, player names, seasons, leagues, or event identifiers.

## Use Cases

- Retrieve player career, club, manager, teammate, or transfer information
- Query match schedules, standings, scores, or event details
- Compare sports APIs when several endpoints mention the same team or player
- Verify multi-part sports requests with multiple calls

## Workflow

### Step 1: Parse sports entities
- **Tool**: `get_current_task`
- **Example**: `get_current_task({})`
- **Purpose**: Extract player names, teams, leagues, seasons, event names, and requested statistics.

### Step 2: Search sports APIs
- **Tool**: `search_candidate_apis` × 1-n times
- **Example**: `search_candidate_apis({"query": "sports player club transfer teammate statistics", "top_k": 8})`
- **Purpose**: Find candidate sports APIs for each requested entity or statistic.

### Step 3: Inspect candidate schemas
- **Tool**: `get_api_schema` × 1-n times
- **Example**: `get_api_schema({"api_key": "Sports::Football API::Player Transfers"})`
- **Purpose**: Determine whether the call requires a player name, ID, season, team, or league.

### Step 4: Call sports endpoints
- **Tool**: `call_api` × 1-n times
- **Example**: `call_api({"api_key": "Sports::Football API::Player Details", "arguments": {"player": "Lionel Messi"}})`
- **Purpose**: Retrieve sports evidence relevant to the user request.

### Step 5: Validate sports coverage
- **Tool**: `get_call_trace`
- **Example**: `get_call_trace({})`
- **Purpose**: Check that all requested sports facts were covered by successful calls.

## Tools Involved

`get_current_task`, `search_candidate_apis`, `get_api_schema`, `call_api`, `get_call_trace`

## Tips

- Use the exact player/team names from the request
- For career-style tasks, expect more than one API call
- Inspect whether "manager", "teammate", and "transfer" are separate endpoints
- Prefer schema-grounded season or league defaults over invented values
