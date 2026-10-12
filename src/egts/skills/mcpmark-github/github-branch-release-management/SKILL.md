# GitHub Branch Release Management

## Description

Manage branch, release, and multi-branch workflows by inspecting branches, commits, PRs, and releases before creating branches, PRs, merges, or releases.

## Use Cases

- Create release branches or support branches from the correct base
- Aggregate commits across multiple branches
- Create PRs for release or branch management work
- Publish release objects or release notes after verifying history
- Merge or close PRs as part of a controlled release workflow

## Workflow

### Step 1: List branches
- **Tool**: `list_branches` × 1-n times
- **Example**: `list_branches({})`
- **Purpose**: Understand available base, feature, and release branches.

### Step 2: Inspect branch details
- **Tool**: `get_branch` × 1-n times
- **Example**: `get_branch({"branch": "release/v1"})`
- **Purpose**: Verify branch head SHA before branching or merging.

### Step 3: Collect commits
- **Tool**: `list_commits` × 1-n times
- **Example**: `list_commits({"sha": "release/v1"})`
- **Purpose**: Build evidence for branch contents or release notes.

### Step 4: Read important commit
- **Tool**: `get_commit` × 1-n times
- **Example**: `get_commit({"sha": "abc123"})`
- **Purpose**: Confirm changed files and metadata for release decisions.

### Step 5: Inspect PRs
- **Tool**: `list_pull_requests` × 1-n times
- **Example**: `list_pull_requests({"state": "open"})`
- **Purpose**: Check pending release, branch, or hotfix PRs.

### Step 6: Create branch or PR
- **Tool**: `create_branch`
- **Example**: `create_branch({"branch": "release/v2", "from_branch": "main"})`
- **Purpose**: Prepare branch state for release work.

### Step 7: Create release if needed
- **Tool**: `create_release`
- **Example**: `create_release({"tag_name": "v1.2.0", "name": "v1.2.0", "body": "..."})`
- **Purpose**: Publish release metadata after evidence is collected.

### Step 8: Verify release state
- **Tool**: `list_releases` × 1-n times
- **Example**: `list_releases({})`
- **Purpose**: Confirm release or branch-management action took effect.

## Tools Involved

`list_branches`, `get_branch`, `list_commits`, `get_commit`, `create_branch`, `list_pull_requests`, `create_pull_request`, `merge_pull_request`, `list_releases`, `get_latest_release`, `create_release`

## Tips

- Never create a branch without confirming the intended base branch.
- For release notes, cite commit or PR evidence.
- Read existing latest release before creating a new one.
- After merge or release mutation, verify repository state with a read tool.
