# File System Manipulation

## Description

Modify the file system workspace by creating, writing, organizing, and deleting files and directories. Build nested directory structures, populate them with content, and restructure existing layouts.

## Use Cases

- Create a nested directory structure with specific files
- Organize scattered files into subdirectories by type or extension
- Move and copy files to restructure a project
- Create files with specific content at targeted paths
- Clean up temporary or unwanted directories

## Workflow

### Step 1: Survey — understand current state
- **Tool**: `list_directory` or `get_directory_tree`
- **Purpose**: See what exists before making changes.

### Step 2: Plan — identify target organization
- **Tool**: `search_files` or `search_content`
- **Purpose**: Find files that need to be moved or reorganized.

### Step 3: Create — build new structure
- **Tool**: `write_file` or `execute_command` with `mkdir -p`
- **Purpose**: Create directories and files as needed.

### Step 4: Move — reorganize files
- **Tool**: `execute_command` with `mv`, `cp`, `rm`
- **Purpose**: Move, copy, or remove files to achieve the target organization.

### Step 5: Verify — confirm the result
- **Tool**: `list_directory` or `get_directory_tree`
- **Purpose**: Confirm the file system matches the desired structure.

## Tools Involved

`list_directory`, `read_file`, `write_file`, `execute_command`, `search_files`

## Tips

- Always survey the current state before making changes
- Use `write_file` for creating new files with known content
- Use `execute_command` with `mv`, `cp`, `rm` for batch operations
- Verify the result with `list_directory` after changes
- Be careful with `rm` — prefer `mv` to a backup location first
