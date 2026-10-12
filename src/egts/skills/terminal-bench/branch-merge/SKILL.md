# Branch & Merge Operations

## Description

Create and manage git branches in the workspace repository, perform merges, resolve conflicts, and clean up merged branches. Handle collaborative git workflows including feature branches and integration.

## Use Cases

- Create a feature branch, make changes, and merge back to main
- Resolve merge conflicts between two divergent branches
- List and switch between branches
- Delete merged branches to keep the repository clean
- Compare branches with git diff before merging

## Workflow

### Step 1: Check — inspect current branch state
- **Tool**: `execute_command` with `git branch`, `git status`
- **Purpose**: Understand which branches exist and which is active.

### Step 2: Branch — create or switch branches
- **Tool**: `execute_command` with `git checkout -b` or `git switch`
- **Purpose**: Create a new branch or switch to an existing one.

### Step 3: Modify — make changes on the branch
- **Tool**: `write_file` or `execute_command`
- **Purpose**: Make file changes that will be committed on the branch.

### Step 4: Commit — record branch changes
- **Tool**: `execute_command` with `git add` and `git commit`
- **Purpose**: Commit changes to the branch.

### Step 5: Merge — integrate branches
- **Tool**: `execute_command` with `git merge`
- **Purpose**: Merge the branch back to main or integrate changes.

### Step 6: Resolve — handle conflicts if needed
- **Tool**: `read_file`, `write_file`, `execute_command` with `git add`
- **Purpose**: Read conflicted files, resolve conflicts, and mark as resolved.

### Step 7: Clean up — remove merged branches
- **Tool**: `execute_command` with `git branch -d`
- **Purpose**: Delete branches that have been successfully merged.

## Tools Involved

`execute_command`, `read_file`, `write_file`, `list_directory`

## Tips

- Use `git log --oneline --graph --all` to visualize branch topology
- Before merging, run `git diff main..feature` to preview changes
- For merge conflicts: files contain `<<<<<<<`, `=======`, `>>>>>>>` markers
- After resolving conflicts: `git add <file>` then `git commit`
- Use `git merge --no-ff` to always create a merge commit for traceability
