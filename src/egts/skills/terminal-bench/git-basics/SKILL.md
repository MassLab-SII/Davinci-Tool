# Git Basics

## Description

Initialize git repositories in the workspace, stage and commit files, view history and diffs. Core version control operations for tracking changes and managing project history.

## Use Cases

- Initialize a new git repository and make the first commit
- Stage specific files and write meaningful commit messages
- View commit history with git log and file diffs
- Check repository status and understand the staging area
- Configure git user settings for a repository

## Workflow

### Step 1: Initialize — create or verify the repository
- **Tool**: `execute_command` with `git init` or `git status`
- **Purpose**: Create a new repo or check the state of an existing one.

### Step 2: Configure — set user identity
- **Tool**: `execute_command` with `git config user.email` / `git config user.name`
- **Purpose**: Ensure commits have proper authorship.

### Step 3: Stage — add files to the staging area
- **Tool**: `execute_command` with `git add`
- **Purpose**: Select which files to include in the next commit.

### Step 4: Commit — create a snapshot
- **Tool**: `execute_command` with `git commit -m "..."`
- **Purpose**: Record the staged changes with a descriptive message.

### Step 5: Review — inspect history
- **Tool**: `execute_command` with `git log --oneline`, `git diff`, `git status`
- **Purpose**: Verify commits and understand the repository state.

## Tools Involved

`execute_command`, `read_file`, `write_file`, `list_directory`, `get_environment_info`

## Tips

- Always check `git status` before and after operations
- Use `git log --oneline` for a compact history view
- Write descriptive commit messages: "Add feature X" not "update"
- `git diff` shows unstaged changes; `git diff --staged` shows staged changes
- Use `git add <file>` for specific files, not `git add .` blindly
