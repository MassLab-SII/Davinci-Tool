# GitHub Contributor Collaboration Analytics

## Description

Analyze contributors, issue and PR participation, comments, commits, and labels to produce collaboration reports or contributor-focused repository updates.

## Use Cases

- Analyze contributor collaboration across commits and PRs
- Assign contributor labels based on verified activity
- Thank PR authors with context-specific comments
- Summarize maintainer or contributor participation
- Create reports that connect people, issues, PRs, and commits

## Workflow

### Step 1: Collect issue activity
- **Tool**: `list_issues` × 1-n times
- **Example**: `list_issues({"state": "all"})`
- **Purpose**: Identify issues with contributor interactions.

### Step 2: Collect PR activity
- **Tool**: `list_pull_requests` × 1-n times
- **Example**: `list_pull_requests({"state": "all"})`
- **Purpose**: Identify PR authors, reviewers, and merged work.

### Step 3: Read discussions
- **Tool**: `list_issue_comments` × 1-n times
- **Example**: `list_issue_comments({"issue_number": 12})`
- **Purpose**: Use comments to verify collaboration context.

### Step 4: Inspect PR comments
- **Tool**: `get_pull_request_comments` × 1-n times
- **Example**: `get_pull_request_comments({"pull_number": 5})`
- **Purpose**: Capture review and acknowledgement signals.

### Step 5: Inspect commit activity
- **Tool**: `list_commits` × 1-n times
- **Example**: `list_commits({"sha": "main"})`
- **Purpose**: Identify author and change history.

### Step 6: Apply contributor label if needed
- **Tool**: `update_issue` × 1-n times
- **Example**: `update_issue({"issue_number": 12, "labels": ["contributor"]})`
- **Purpose**: Mutate issue organization based on verified evidence.

### Step 7: Write collaboration report
- **Tool**: `create_or_update_file` × 1-n times
- **Example**: `create_or_update_file({"path": "reports/collaboration.md", "content": "..."})`
- **Purpose**: Persist analysis with contributor evidence.

### Step 8: Verify output
- **Tool**: `get_file_contents` × 1-n times
- **Example**: `get_file_contents({"path": "reports/collaboration.md"})`
- **Purpose**: Confirm report includes the required names, counts, and evidence.

## Tools Involved

`list_issues`, `get_issue`, `list_issue_comments`, `list_pull_requests`, `get_pull_request`, `get_pull_request_comments`, `list_commits`, `get_commit`, `list_labels`, `update_issue`, `create_or_update_file`, `add_issue_comment`

## Tips

- Do not infer contributor status from one signal when multiple sources exist.
- Use comments for social/context evidence and commits for code evidence.
- When reporting counts, specify whether they are commits, PRs, issues, or comments.
- Verify labels or reports after mutation.
