# Git History Rewrite

## Description

Rewrite and manipulate git commit history in the workspace repository. Use interactive rebase to squash and reorder commits, bisect to find bug-introducing commits, cherry-pick specific changes, and manage history with reset and amend.

## Use Cases

- Use git bisect to find which commit introduced a bug
- Squash multiple WIP commits into a single clean commit with interactive rebase
- Cherry-pick a specific commit from one branch to another
- Amend the most recent commit message or contents
- Reset to a previous state and rebuild commit history

## Workflow

### Step 1: Survey — understand current history
- **Tool**: `execute_command` with `git log --oneline --graph --all`
- **Purpose**: Visualize the full commit history and branch structure.

### Step 2: Plan — decide on the rewrite operation
- **Tool**: `read_file` (examine files at specific commits)
- **Purpose**: Understand what needs to change in the history.

### Step 3: Execute — perform the rewrite
- **Tool**: `execute_command` with `git rebase -i`, `git bisect`, `git cherry-pick`
- **Purpose**: Carry out the history rewrite operation.

### Step 4: Verify — confirm the result
- **Tool**: `execute_command` with `git log`, `git diff`, `read_file`
- **Purpose**: Verify the history is now correct and files have expected content.

### Step 5: Clean up — finalize state
- **Tool**: `execute_command` with `git bisect reset`, `git branch -D`
- **Purpose**: Clean up any temporary bisect state or abandoned branches.

## Tools Involved

`execute_command`, `read_file`, `write_file`, `list_directory`

## Tips

- `git log --oneline --all` before any history rewrite to understand the starting state
- For bisect: mark known-good with `git bisect good` and known-bad with `git bisect bad`
- Interactive rebase: `git rebase -i HEAD~N` to squash/reorder the last N commits
- `git cherry-pick <commit-hash>` to apply a single commit to the current branch
- `git commit --amend` to modify the most recent commit (message or contents)
- Always verify with `git log --oneline` after any history rewrite
