# GitHub Commit History Forensics

## Description

Trace commits, branches, file history, authorship, and salient repository changes to answer when, where, and who questions with durable evidence.

## Use Cases

- Record recent commits and commit dates
- Find the commit that introduced a feature or reference
- Attribute file or feature changes to contributors
- Aggregate commits from multiple branches
- Write evidence-backed answer files or issues

## Workflow

### Step 1: Scope the history search
- **Tool**: `list_branches` × 1-n times
- **Example**: `list_branches({})`
- **Purpose**: Identify branches that may contain the target change.

### Step 2: Search for related code or docs
- **Tool**: `search_code` × 1-n times
- **Example**: `search_code({"query": "RAG"})`
- **Purpose**: Find files or terms that can narrow commit history.

### Step 3: List commits
- **Tool**: `list_commits` × 1-n times
- **Example**: `list_commits({"sha": "main"})`
- **Purpose**: Collect candidate commits in the relevant branch or path context.

### Step 4: Inspect specific commit
- **Tool**: `get_commit` × 1-n times
- **Example**: `get_commit({"sha": "abc123"})`
- **Purpose**: Verify author, date, message, and changed files.

### Step 5: Read current file state
- **Tool**: `get_file_contents` × 1-n times
- **Example**: `get_file_contents({"path": "README.md"})`
- **Purpose**: Compare current content with commit evidence when needed.

### Step 6: Persist forensic answer
- **Tool**: `create_or_update_file` × 1-n times
- **Example**: `create_or_update_file({"path": "answers/commit-history.md", "content": "..."})`
- **Purpose**: Save the commit evidence and conclusion.

### Step 7: Verify answer artifact
- **Tool**: `get_file_contents` × 1-n times
- **Example**: `get_file_contents({"path": "answers/commit-history.md"})`
- **Purpose**: Confirm the final artifact includes exact SHAs and dates.

## Tools Involved

`list_commits`, `get_commit`, `list_branches`, `get_branch`, `search_code`, `get_file_contents`, `create_or_update_file`, `create_issue`

## Tips

- Use exact commit SHAs in the final answer.
- Do not infer authorship from file contents when commit metadata is available.
- For multi-branch tasks, inspect each relevant branch separately.
- If search finds many files, prioritize files changed in candidate commits.
