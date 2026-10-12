# Disk Space Analysis & Cleanup

## Description

Find large files and directories consuming disk space in the workspace, identify candidates for cleanup, generate space usage reports, and safely remove unnecessary files to reclaim storage.

## Use Cases

- Find the largest files and directories in the workspace
- Generate a disk usage report sorted by size
- Identify old or temporary files that can be safely removed
- Locate files exceeding a size threshold for review
- Clean up archive directories while preserving recent files

## Workflow

### Step 1: Overview — check overall disk usage
- **Tool**: `get_environment_info` or `execute_command` with `df -h`
- **Purpose**: Understand total disk usage and available space.

### Step 2: Scan — find the largest consumers
- **Tool**: `execute_command` with `du -sh`, `find -size`
- **Purpose**: Identify which directories and files use the most space.

### Step 3: Tree — visualize directory sizes
- **Tool**: `get_directory_tree`
- **Purpose**: See the directory structure with context for size distribution.

### Step 4: Inspect — examine candidate files
- **Tool**: `read_file`, `list_directory`
- **Purpose**: Check file contents before deciding to delete.

### Step 5: Clean — remove unnecessary files
- **Tool**: `execute_command` with `rm`
- **Purpose**: Remove identified junk files, temp files, or duplicates.

### Step 6: Report — document what was done
- **Tool**: `write_file`
- **Purpose**: Generate a cleanup report showing what was removed and space saved.

## Tools Involved

`get_directory_tree`, `search_files`, `execute_command`, `list_directory`, `write_file`, `get_environment_info`

## Tips

- `du -sh * | sort -rh | head -20` shows the 20 largest items
- `find . -type f -size +1M -exec ls -lh {} \;` finds files larger than 1MB
- `find . -type f -name "*.log" -size +10M` finds large log files
- Always `read_file` or check file contents before deleting
- Generate a before/after report to document space savings
