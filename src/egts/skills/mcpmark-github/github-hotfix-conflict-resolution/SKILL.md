# GitHub Hotfix Conflict Resolution

## Description

Coordinate hotfixes and conflict resolution by inspecting issues, PRs, branches, and changed files before creating support branches, fixes, PRs, merges, or explanatory comments.

## Use Cases

- Resolve conflict-related benchmark tasks
- Create hotfix branches for critical issues
- Inspect PR files before deciding merge or close action
- Patch infrastructure or source files to unblock a release
- Leave issue/PR comments documenting resolution evidence

## Workflow

### Step 1: Read urgent issue
- **Tool**: `get_issue` × 1-n times
- **Example**: `get_issue({"issue_number": 21})`
- **Purpose**: Understand the reported failure, affected branch, or requested hotfix.

### Step 2: Inspect PR landscape
- **Tool**: `list_pull_requests` × 1-n times
- **Example**: `list_pull_requests({"state": "open"})`
- **Purpose**: Find PRs involved in the conflict or hotfix workflow.

### Step 3: Read PR details and files
- **Tool**: `get_pull_request_files` × 1-n times
- **Example**: `get_pull_request_files({"pull_number": 8})`
- **Purpose**: Identify conflicting or affected files.

### Step 4: Inspect branches
- **Tool**: `list_branches` × 1-n times
- **Example**: `list_branches({})`
- **Purpose**: Determine base, hotfix, and target branches.

### Step 5: Create support branch
- **Tool**: `create_branch`
- **Example**: `create_branch({"branch": "hotfix/critical-issue", "from_branch": "main"})`
- **Purpose**: Prepare isolated work for the fix.

### Step 6: Patch required file
- **Tool**: `create_or_update_file` × 1-n times
- **Example**: `create_or_update_file({"path": "src/fix.py", "content": "...", "branch": "hotfix/critical-issue"})`
- **Purpose**: Apply the minimal hotfix or conflict-resolution artifact.

### Step 7: Open or merge PR
- **Tool**: `create_pull_request`
- **Example**: `create_pull_request({"title": "Hotfix critical issue", "head": "hotfix/critical-issue", "base": "main"})`
- **Purpose**: Route the fix through the appropriate PR workflow.

### Step 8: Document resolution
- **Tool**: `add_issue_comment` × 1-n times
- **Example**: `add_issue_comment({"issue_number": 21, "body": "Resolved via hotfix branch and PR."})`
- **Purpose**: Leave traceable evidence on the issue or PR.

## Tools Involved

`list_issues`, `get_issue`, `list_pull_requests`, `get_pull_request`, `get_pull_request_files`, `list_branches`, `create_branch`, `create_or_update_file`, `create_pull_request`, `merge_pull_request`, `update_pull_request`, `add_issue_comment`

## Tips

- Do not assume the default branch; inspect branches first.
- Read changed files before declaring a conflict resolved.
- Keep hotfix changes narrow and tied to the issue evidence.
- After creating PRs or comments, verify the relevant issue/PR state.
