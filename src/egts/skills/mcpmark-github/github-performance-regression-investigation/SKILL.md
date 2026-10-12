# GitHub Performance Regression Investigation

## Description

Investigate performance regressions by correlating issues, commits, branches, configuration files, and PR changes before filing or patching an evidence-backed fix.

## Use Cases

- Investigate reported slowdowns or regressions
- Trace a regression to recent commits or PR files
- Audit benchmark or configuration changes
- Create a regression issue with exact evidence
- Patch an obvious configuration or code-path regression

## Workflow

### Step 1: Read regression report
- **Tool**: `list_issues` × 1-n times
- **Example**: `list_issues({"state": "open"})`
- **Purpose**: Find issues describing slowdown, failure, or performance drift.

### Step 2: Inspect issue detail
- **Tool**: `get_issue` × 1-n times
- **Example**: `get_issue({"issue_number": 9})`
- **Purpose**: Extract component, metric, branch, and reproduction context.

### Step 3: Read comments
- **Tool**: `list_issue_comments` × 1-n times
- **Example**: `list_issue_comments({"issue_number": 9})`
- **Purpose**: Gather additional observations or maintainer hints.

### Step 4: Inspect recent commits
- **Tool**: `list_commits` × 1-n times
- **Example**: `list_commits({"sha": "main"})`
- **Purpose**: Identify candidate changes near the regression window.

### Step 5: Read suspect commit
- **Tool**: `get_commit` × 1-n times
- **Example**: `get_commit({"sha": "abc123"})`
- **Purpose**: Verify changed files and commit rationale.

### Step 6: Search affected code
- **Tool**: `search_code` × 1-n times
- **Example**: `search_code({"query": "batch_size"})`
- **Purpose**: Locate performance-sensitive code or config.

### Step 7: Inspect PR files
- **Tool**: `get_pull_request_files` × 1-n times
- **Example**: `get_pull_request_files({"pull_number": 4})`
- **Purpose**: Connect the regression hypothesis to PR-level changes.

### Step 8: Create fix or report
- **Tool**: `create_issue`
- **Example**: `create_issue({"title": "Performance regression investigation", "body": "..."})`
- **Purpose**: Persist the evidence-backed conclusion or next action.

## Tools Involved

`list_issues`, `get_issue`, `list_issue_comments`, `list_commits`, `get_commit`, `search_code`, `get_file_contents`, `list_pull_requests`, `get_pull_request_files`, `create_issue`, `create_or_update_file`

## Tips

- Keep hypotheses tied to commit, file, or issue evidence.
- Do not patch performance-sensitive code without reading context.
- When comparing commits, record exact SHAs and files.
- If the result is a report, include reproduction clues and suspected cause.
