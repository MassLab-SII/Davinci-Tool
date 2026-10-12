# GitHub Changelog And Release Notes Generation

## Description

Generate changelogs or release notes from commit, branch, PR, and release evidence, then write or publish the summarized artifact.

## Use Cases

- Generate changelog files from recent commits
- Prepare release notes from PR and commit history
- Aggregate multi-branch commits into a summary
- Publish or update GitHub releases
- Create answer artifacts that summarize repository evolution

## Workflow

### Step 1: Inspect releases
- **Tool**: `list_releases` × 1-n times
- **Example**: `list_releases({})`
- **Purpose**: Understand existing release history and note style.

### Step 2: Read latest release
- **Tool**: `get_latest_release` × 1-n times
- **Example**: `get_latest_release({})`
- **Purpose**: Establish baseline for new release notes.

### Step 3: Collect commits
- **Tool**: `list_commits` × 1-n times
- **Example**: `list_commits({"sha": "main"})`
- **Purpose**: Gather candidate changes for the changelog.

### Step 4: Inspect important commits
- **Tool**: `get_commit` × 1-n times
- **Example**: `get_commit({"sha": "abc123"})`
- **Purpose**: Verify details before summarizing.

### Step 5: Cross-check PR context
- **Tool**: `list_pull_requests` × 1-n times
- **Example**: `list_pull_requests({"state": "closed"})`
- **Purpose**: Connect commits to reviewed features or fixes.

### Step 6: Write changelog file
- **Tool**: `create_or_update_file` × 1-n times
- **Example**: `create_or_update_file({"path": "CHANGELOG.md", "content": "..."})`
- **Purpose**: Persist the generated changelog or notes.

### Step 7: Create release if required
- **Tool**: `create_release`
- **Example**: `create_release({"tag_name": "v1.2.0", "name": "v1.2.0", "body": "..."})`
- **Purpose**: Publish release metadata when the task requires it.

### Step 8: Verify artifact
- **Tool**: `get_file_contents` × 1-n times
- **Example**: `get_file_contents({"path": "CHANGELOG.md"})`
- **Purpose**: Confirm final notes contain evidence-backed entries.

## Tools Involved

`list_commits`, `get_commit`, `list_pull_requests`, `get_pull_request`, `list_releases`, `get_latest_release`, `create_release`, `get_file_contents`, `create_or_update_file`

## Tips

- Group entries by feature, fix, docs, or infrastructure when the repository history supports it.
- Use commit SHAs or PR numbers for traceability.
- Read existing changelog/release style before writing.
- Do not include commits outside the requested branch or date range.
