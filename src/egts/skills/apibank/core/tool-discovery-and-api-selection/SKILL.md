# Tool Discovery And API Selection

## Description

Use API-Bank's tool discovery pattern: search for relevant APIs, inspect returned input requirements, call prerequisite tools such as `GetUserToken`, then execute the selected API and verify the result.

## Use Cases

- Find the right API for an unfamiliar request
- Discover whether a target API requires token authentication
- Chain `ToolSearcher` with the discovered API
- Compare multiple candidate tools before acting

## Workflow

### Step 1: Search for candidate tools
- **Tool**: `ToolSearcher` × 1-n times
- **Example**: `ToolSearcher({"keywords": "schedule reminder for medicine"})`
- **Purpose**: Retrieve relevant API metadata and input requirements.

### Step 2: Inspect input parameters
- **Tool**: `ToolSearcher`
- **Example**: `ToolSearcher({"keywords": "query balance token"})`
- **Purpose**: Determine whether the selected API needs `token`, arrays, timestamps, or numeric parameters.

### Step 3: Acquire prerequisites
- **Tool**: `GetUserToken` or `GetToday`
- **Examples**:
  - `GetUserToken({"username": "John", "password": "123456"})`
  - `GetToday({})`
- **Purpose**: Prepare required authentication or date values before calling the target API.

### Step 4: Call the selected API
- **Tool**: any discovered target API
- **Example**: `AddReminder({"token": "returned_token", "content": "take medicine", "time": "2023-04-01 08:00:00"})`
- **Purpose**: Execute the task using the tool chosen from search evidence.

### Step 5: Verify with a matching query
- **Tool**: matching query API × 1-n times
- **Example**: `QueryReminder({"token": "returned_token", "content": "take medicine", "time": "2023-04-01 08:00:00"})`
- **Purpose**: Confirm whether the discovered and executed API produced the intended state.

### Step 6: Recover from wrong tool selection
- **Tool**: `ToolSearcher` × 1-n times
- **Example**: `ToolSearcher({"keywords": "alarm time only alert"})`
- **Purpose**: If the first tool is too broad or fails, search again with more specific capability keywords.

## Tools Involved

`ToolSearcher`, `GetUserToken`, `GetToday`, `AddReminder`, `QueryReminder`, `AddAgenda`, `QueryAgenda`, `SearchEngine`, `Calculator`

## Tips

- Treat `ToolSearcher` output as planning evidence, not as the final answer.
- If the returned API has a `token` input, call `GetUserToken` before it.
- Use a matching query API after mutation to improve state-grounding.
