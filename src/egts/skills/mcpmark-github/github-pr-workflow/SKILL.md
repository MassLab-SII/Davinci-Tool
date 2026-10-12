# GitHub Pull Request Workflow

## Description

Handle pull request workflows by inspecting PR metadata, changed files, comments, and issue links before reviewing, updating, merging, or closing PRs.

## Use Cases

- Thank or respond to PR authors based on actual submitted changes
- Audit PR files before adding review comments or updates
- Close or merge PRs only after verifying target branch and requested outcome
- Connect PR decisions to issues, labels, or release management tasks
- Create maintainer comments that cite specific changed files or review context

## Workflow

### Step 1: List candidate pull requests
- **Tool**: `list_pull_requests` × 1-n times
- **Example**: `list_pull_requests({"state": "open"})`
- **Purpose**: Find relevant PRs and avoid acting on the wrong request.

### Step 2: Read PR metadata
- **Tool**: `get_pull_request` × 1-n times
- **Example**: `get_pull_request({"pull_number": 5})`
- **Purpose**: Inspect title, body, author, branch, mergeability, and linked issue context.

### Step 3: Inspect changed files
- **Tool**: `get_pull_request_files` × 1-n times
- **Example**: `get_pull_request_files({"pull_number": 5})`
- **Purpose**: Understand exactly what the PR modifies before commenting or merging.

### Step 4: Read existing discussion
- **Tool**: `get_pull_request_comments` × 1-n times
- **Example**: `get_pull_request_comments({"pull_number": 5})`
- **Purpose**: Avoid duplicate comments and identify unresolved review threads.

### Step 5: Add targeted review feedback
- **Tool**: `add_pull_request_review_comment`
- **Example**: `add_pull_request_review_comment({"pull_number": 5, "body": "Thanks for updating the Docker docs."})`
- **Purpose**: Leave review or acknowledgement tied to verified PR evidence.

### Step 6: Update or merge PR
- **Tool**: `update_pull_request`
- **Example**: `update_pull_request({"pull_number": 5, "state": "closed"})`
- **Purpose**: Change PR state only after evidence supports the requested action.

### Step 7: Verify PR outcome
- **Tool**: `get_pull_request` × 1-n times
- **Example**: `get_pull_request({"pull_number": 5})`
- **Purpose**: Confirm state, merge status, or comment presence after mutation.

## Tools Involved

`list_pull_requests`, `get_pull_request`, `get_pull_request_files`, `get_pull_request_comments`, `add_pull_request_review_comment`, `update_pull_request`, `merge_pull_request`, `add_issue_comment`

## Tips

- Always inspect changed files before making a review or merge decision.
- Use issue comments only when the workflow is issue-centered; otherwise prefer PR comments.
- If mergeability or target branch matters, inspect branch/PR metadata before mutating.
- After closing or merging, re-read the PR to verify the final state.
