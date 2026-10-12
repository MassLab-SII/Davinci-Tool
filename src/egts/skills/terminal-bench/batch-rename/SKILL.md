# Batch Rename & Organization

## Description

Rename and reorganize multiple files in the workspace following naming conventions. Use pattern matching, substitution, and batch move operations to transform inconsistent file names into a uniform structure.

## Use Cases

- Rename photo files from camera defaults (IMG_0001.jpg) to descriptive names
- Apply a consistent naming convention across a directory of files
- Flatten or restructure nested directories
- Move files into category-based subdirectories based on name patterns
- Add prefixes or suffixes to groups of related files

## Workflow

### Step 1: Survey — list current files
- **Tool**: `list_directory` or `search_files`
- **Purpose**: See all files that need renaming and their current names.

### Step 2: Plan — design naming convention
- **Tool**: `read_file` (sample files to understand content)
- **Purpose**: Determine the target naming pattern based on file content or type.

### Step 3: Execute — apply renames
- **Tool**: `execute_command` with `mv`, `rename`, or shell loops
- **Purpose**: Rename files individually or in batches.

### Step 4: Verify — check results
- **Tool**: `list_directory` or `get_directory_tree`
- **Purpose**: Confirm all files are renamed correctly.

## Tools Involved

`list_directory`, `search_files`, `execute_command`, `read_file`, `get_directory_tree`

## Tips

- Use shell loops for batch renaming: `for f in *.jpg; do mv "$f" "prefix_${f}"; done`
- `sed` can help generate new names from old patterns
- Always list files before and after renaming to verify
- Test on a small subset or with `echo` before executing actual `mv` commands
- Check for name collisions before starting batch operations
