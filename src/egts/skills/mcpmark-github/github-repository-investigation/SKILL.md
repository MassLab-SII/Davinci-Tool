# GitHub Repository Investigation

## Description

Investigate repository source, branches, commits, issues, and PRs to answer evidence-backed questions or create precise repository updates.

## Use Cases

- Find identifiers, legacy names, tracking IDs, or salient files across a repository
- Investigate where a feature or configuration lives before writing an answer file
- Trace repository structure before opening an issue or PR
- Combine code search, file reads, commits, and branches for grounded conclusions
- Produce reports that cite exact files, commits, and branches

## Workflow

### Step 1: Search repository broadly
- **Tool**: `search_code` × 1-n times
- **Example**: `search_code({"query": "legacy_name"})`
- **Purpose**: Find candidate files, terms, or symbols related to the task.

### Step 2: Read candidate files
- **Tool**: `get_file_contents` × 1-n times
- **Example**: `get_file_contents({"path": "README.md"})`
- **Purpose**: Verify exact content and avoid relying on search snippets only.

### Step 3: Inspect branch context
- **Tool**: `list_branches` × 1-n times
- **Example**: `list_branches({})`
- **Purpose**: Check whether evidence may live on another branch.

### Step 4: Read branch details
- **Tool**: `get_branch` × 1-n times
- **Example**: `get_branch({"branch": "main"})`
- **Purpose**: Confirm commit SHA and branch status when branch-specific evidence matters.

### Step 5: Inspect history
- **Tool**: `list_commits` × 1-n times
- **Example**: `list_commits({"sha": "main"})`
- **Purpose**: Identify recent or relevant changes that may explain current repository state.

### Step 6: Read important commit
- **Tool**: `get_commit` × 1-n times
- **Example**: `get_commit({"sha": "abc123"})`
- **Purpose**: Verify changed files, author, timestamp, and message for forensic claims.

### Step 7: Persist finding
- **Tool**: `create_or_update_file` × 1-n times
- **Example**: `create_or_update_file({"path": "answers/investigation.md", "content": "..."})`
- **Purpose**: Write the evidence-backed answer, report, or issue content.

### Step 8: Verify output
- **Tool**: `get_file_contents` × 1-n times
- **Example**: `get_file_contents({"path": "answers/investigation.md"})`
- **Purpose**: Confirm saved findings are present and complete.

## Tools Involved

`search_code`, `get_file_contents`, `list_commits`, `get_commit`, `list_branches`, `get_branch`, `create_issue`, `create_or_update_file`, `add_issue_comment`

## Tips

- Search first, but always read full files before forming a conclusion.
- When answering when/who questions, use `get_commit`, not only `list_commits`.
- If multiple branches exist, inspect branch context before declaring evidence absent.
- Write reports with file paths and commit SHAs so results are auditable.
