# GitHub File And Documentation Update

## Description

Create or update repository files such as documentation, answer files, changelogs, migration guides, workflow files, or configuration files after reading current repository context.

## Use Cases

- Add documentation requested by an issue or task description
- Create answer files for repository investigation tasks
- Patch small configuration or workflow files after reading conventions
- Create branches and PRs for repository updates when the workflow requires review
- Verify committed file contents after mutation

## Workflow

### Step 1: Find target file
- **Tool**: `search_code` × 1-n times
- **Example**: `search_code({"query": "terminal shortcuts"})`
- **Purpose**: Locate existing docs, configs, or answer files relevant to the requested update.

### Step 2: Read current content
- **Tool**: `get_file_contents` × 1-n times
- **Example**: `get_file_contents({"path": "docs/usage.md"})`
- **Purpose**: Understand style, formatting, and existing information before writing.

### Step 3: Inspect branch target
- **Tool**: `list_branches` × 1-n times
- **Example**: `list_branches({})`
- **Purpose**: Identify the correct base branch for the update.

### Step 4: Create branch if needed
- **Tool**: `create_branch`
- **Example**: `create_branch({"branch": "docs/update-shortcuts", "from_branch": "main"})`
- **Purpose**: Isolate the change when the task expects PR-based workflow.

### Step 5: Write file update
- **Tool**: `create_or_update_file` × 1-n times
- **Example**: `create_or_update_file({"path": "docs/usage.md", "content": "...", "branch": "docs/update-shortcuts"})`
- **Purpose**: Create or update the required repository file.

### Step 6: Open PR if needed
- **Tool**: `create_pull_request`
- **Example**: `create_pull_request({"title": "Update terminal shortcuts docs", "head": "docs/update-shortcuts", "base": "main"})`
- **Purpose**: Submit the change through review when appropriate.

### Step 7: Verify final file
- **Tool**: `get_file_contents` × 1-n times
- **Example**: `get_file_contents({"path": "docs/usage.md", "branch": "docs/update-shortcuts"})`
- **Purpose**: Confirm the exact intended content exists.

## Tools Involved

`get_file_contents`, `search_code`, `list_branches`, `get_branch`, `create_branch`, `create_or_update_file`, `create_pull_request`

## Tips

- Do not overwrite files from memory; read them first and preserve local style.
- Use branch and PR tools when a task asks for reviewed repository changes.
- For answer files, include enough evidence to reconstruct why the answer is correct.
- Verify file contents after every write.
