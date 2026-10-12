# GitHub Issue Management

## Description

Manage GitHub issues with evidence-first triage: inspect issues, comments, labels, and related repository context before creating, commenting, labeling, closing, or reopening issues.

## Use Cases

- Triage bug reports and feature requests with label and comment evidence
- Close stale or answered issues after checking recent discussion
- Create tracking issues for missing automation, documentation, or regression work
- Reopen or update issues when new repository evidence changes the conclusion
- Connect issue actions to PRs, commits, and labels for maintainable project state

## Workflow

### Step 1: Inspect available issues
- **Tool**: `list_issues` × 1-n times
- **Example**: `list_issues({"state": "open"})`
- **Purpose**: Find candidate issues and understand current issue volume.

### Step 2: Read the target issue
- **Tool**: `get_issue` × 1-n times
- **Example**: `get_issue({"issue_number": 17})`
- **Purpose**: Verify title, body, labels, assignees, and current state before acting.

### Step 3: Read discussion history
- **Tool**: `list_issue_comments` × 1-n times
- **Example**: `list_issue_comments({"issue_number": 17})`
- **Purpose**: Use comments as evidence for whether the issue should be answered, labeled, or closed.

### Step 4: Inspect label taxonomy
- **Tool**: `list_labels` × 1-n times
- **Example**: `list_labels({})`
- **Purpose**: Choose an existing label when possible and avoid inventing duplicate categories.

### Step 5: Apply issue update
- **Tool**: `update_issue` × 1-n times
- **Example**: `update_issue({"issue_number": 17, "labels": ["bug", "needs-triage"]})`
- **Purpose**: Apply labels, close/reopen status, title/body edits, or other issue metadata changes.

### Step 6: Add maintainer note
- **Tool**: `add_issue_comment` × 1-n times
- **Example**: `add_issue_comment({"issue_number": 17, "body": "Confirmed from the latest logs and labeled for follow-up."})`
- **Purpose**: Leave a traceable explanation for the change.

### Step 7: Verify final state
- **Tool**: `get_issue` × 1-n times
- **Example**: `get_issue({"issue_number": 17})`
- **Purpose**: Confirm labels, state, and comments match the intended outcome.

## Tools Involved

`list_issues`, `get_issue`, `list_issue_comments`, `list_labels`, `create_issue`, `add_issue_comment`, `update_issue`

## Tips

- Do not close an issue only from the title; read body and comments first.
- Prefer existing labels unless the task explicitly requires a new taxonomy.
- When creating issues, include concrete reproduction/evidence from files, commits, PRs, or comments.
- For mutation tasks, always verify final state with `get_issue`.
