# Video Image and Media Processing

## Description

Handle requests about video search, image metadata, thumbnails, media conversion, streaming links, channel information, or visual content utilities. This skill targets StableToolBench categories such as Video_Images, Media, Entertainment, and Tools.

## Use Cases

- Search videos and retrieve video or channel details
- Generate or inspect thumbnails, previews, or media metadata
- Retrieve streaming links or video availability
- Use image, URL, and content utility APIs for media workflows

## Workflow

### Step 1: Extract media targets
- **Tool**: `get_current_task`
- **Example**: `get_current_task({})`
- **Purpose**: Identify video IDs, channel names, media keywords, image URLs, formats, or requested metadata.

### Step 2: Search media APIs
- **Tool**: `search_candidate_apis` × 1-n times
- **Example**: `search_candidate_apis({"query": "video details channel streaming thumbnail image", "top_k": 8})`
- **Purpose**: Locate APIs that match the media object and output type.

### Step 3: Inspect schemas
- **Tool**: `get_api_schema` × 1-n times
- **Example**: `get_api_schema({"api_key": "Video_Images::YTStream::Video Details"})`
- **Purpose**: Check whether the endpoint requires a video ID, URL, search query, or channel identifier.

### Step 4: Call media APIs
- **Tool**: `call_api` × 1-n times
- **Example**: `call_api({"api_key": "Video_Images::Vimeo::Search Videos", "arguments": {"query": "documentary"}})`
- **Purpose**: Retrieve media evidence using grounded identifiers and keywords.

### Step 5: Review call trace
- **Tool**: `get_call_trace`
- **Example**: `get_call_trace({})`
- **Purpose**: Confirm the media API calls succeeded and were relevant.

## Tools Involved

`get_current_task`, `search_candidate_apis`, `get_api_schema`, `call_api`, `get_call_trace`

## Tips

- Keep video IDs and URLs exact; small changes can route to a different endpoint behavior
- Use search APIs for keywords and details APIs for known IDs
- For media pipelines, one call may find an item while a second call fetches details
- Inspect response templates to know whether the API returns a link, metadata, or nested object
