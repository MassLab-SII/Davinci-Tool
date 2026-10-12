# News Social and Public Information Monitoring

## Description

Collect news, public profile, social media, trend, post, media, or public-information evidence using StableToolBench candidate APIs. This skill focuses on source selection and traceable evidence for broad information requests.

## Use Cases

- Search news, posts, social profiles, or public media information
- Retrieve follower, like, engagement, or public content metrics
- Combine news and social APIs for trend-oriented requests
- Verify that selected APIs align with the requested public information source

## Workflow

### Step 1: Identify information source and entity
- **Tool**: `get_current_task`
- **Example**: `get_current_task({})`
- **Purpose**: Extract people, organizations, accounts, keywords, locations, or requested public metrics.

### Step 2: Search news and social candidates
- **Tool**: `search_candidate_apis` × 1-n times
- **Example**: `search_candidate_apis({"query": "news social profile posts trend engagement", "top_k": 8})`
- **Purpose**: Find APIs that retrieve the right kind of public information.

### Step 3: Inspect source-specific schemas
- **Tool**: `get_api_schema` × 1-n times
- **Example**: `get_api_schema({"api_key": "Social::Instagram_v2::User Info"})`
- **Purpose**: Check whether the endpoint expects a username, ID, keyword, or category.

### Step 4: Call the selected API
- **Tool**: `call_api` × 1-n times
- **Example**: `call_api({"api_key": "News_Media::News API::Search", "arguments": {"q": "technology"}})`
- **Purpose**: Retrieve public-information evidence with complete parameters.

### Step 5: Verify source relevance
- **Tool**: `get_call_trace`
- **Example**: `get_call_trace({})`
- **Purpose**: Confirm the API source and response align with the task.

## Tools Involved

`get_current_task`, `search_candidate_apis`, `get_api_schema`, `call_api`, `get_call_trace`

## Tips

- Search both the source type and the target entity
- Distinguish user/profile APIs from content/search APIs
- For trend tasks, compare at least two likely endpoints when available
- Do not use a social API for a news request unless the query explicitly asks for social evidence
