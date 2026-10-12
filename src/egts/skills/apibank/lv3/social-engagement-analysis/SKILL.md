# Social Engagement Analysis

## Description

Analyze user social engagement by retrieving post IDs, checking like counts for each post, and calculating simple totals or averages. This skill covers lightweight social analytics workflows.

## Use Cases

- Retrieve a user's posts and inspect likes
- Calculate total likes for a user
- Compare engagement across several posts
- Identify highly liked posts for a simple social summary

## Workflow

### Step 1: Search social analytics tools
- **Tool**: `Lv3ToolSearcher`
- **Example**: `Lv3ToolSearcher({"keywords": "user posts like count engagement"})`
- **Purpose**: Discover post and like-count APIs.

### Step 2: Retrieve user post IDs
- **Tool**: `UserPosts`
- **Example**: `UserPosts({"user_id": 1})`
- **Purpose**: Get the list of post IDs for a user.

### Step 3: Retrieve like counts
- **Tool**: `LikeCount` × 1-n times
- **Examples**:
  - `LikeCount({"post_id": 1})`
  - `LikeCount({"post_id": 2})`
  - `LikeCount({"post_id": 3})`
- **Purpose**: Gather engagement evidence for each post. Repeat for every post ID being analyzed.

### Step 4: Calculate aggregate likes
- **Tool**: `Lv3Calculator`
- **Example**: `Lv3Calculator({"formula": "10 + 20 + 30"})`
- **Purpose**: Compute total or average likes from returned counts.

### Step 5: Compare another user if useful
- **Tool**: `UserPosts` or `LikeCount` × 1-n times
- **Example**: `UserPosts({"user_id": 2})`
- **Purpose**: Expand the analysis to another user or compare post sets.

## Tools Involved

`Lv3ToolSearcher`, `UserPosts`, `LikeCount`, `Lv3Calculator`

## Tips

- Seeded `user_id` values are integers such as `1`, `2`, `3`, `4`, and `5`.
- `LikeCount` requires a numeric `post_id`.
- Use `Lv3Calculator` only after collecting concrete like counts from tools.

