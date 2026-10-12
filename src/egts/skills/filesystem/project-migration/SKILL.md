# Project Migration

## Description

Migrate a project from one directory structure to another. Analyze the old layout, design the new structure, move files to their new locations, and update all internal references (import paths, config paths) to ensure the project remains consistent after migration.

## Use Cases

- Split a monolithic project into modular structure
- Migrate from flat layout to layered architecture (MVC, Clean Architecture)
- Rename core modules and update all references
- Consolidate multiple small projects into a monorepo

## Workflow

### Step 1: Discover allowed directories
- **Tool**: `list_allowed_directories`
- **Example**: `list_allowed_directories({})`
- **Purpose**: Discover which directories you are permitted to access. Use the returned paths as roots for all subsequent operations.

### Step 2: Inspect the workspace root
- **Tool**: `list_directory`
- **Example**: `list_directory({"path": "/workspace"})`
- **Purpose**: List the top-level contents to understand what exists before migration. Replace `/workspace` with the actual allowed path from Step 1.

### Step 3: Analyze old project structure
- **Tool**: `directory_tree`
- **Example**: `directory_tree({"path": "/workspace/old_project"})`
- **Purpose**: Get the full file tree to understand the current organization. The `path` parameter must be a **string**.

### Step 4: Understand file dependencies
- **Tool**: `read_multiple_files`
- **Example**: `read_multiple_files({"paths": ["/workspace/old_project/main.py", "/workspace/old_project/utils.py", "/workspace/old_project/config.py"]})`
- **Purpose**: Read core source files to map import/require dependency relationships between files. The `paths` parameter must be an **array of strings**.

### Step 5: Locate config files with path references
- **Tool**: `search_files` × 1-n times
- **Examples**:
  - `search_files({"path": "/workspace/old_project", "pattern": "*.json"})`
  - `search_files({"path": "/workspace/old_project", "pattern": "*.yaml"})`
- **Purpose**: Find all configuration files that may contain path references needing updates. Both `path` and `pattern` must be **strings**.

### Step 6: Read config contents
- **Tool**: `read_multiple_files`
- **Example**: `read_multiple_files({"paths": ["/workspace/old_project/config.json", "/workspace/old_project/settings.yaml"]})`
- **Purpose**: Examine configuration files and record all file path references within them.

### Step 7: Create new directory structure
- **Tool**: `create_directory` × 1-n times
- **Examples**:
  - `create_directory({"path": "/workspace/new_project/src/core"})`
  - `create_directory({"path": "/workspace/new_project/src/utils"})`
  - `create_directory({"path": "/workspace/new_project/config"})`
  - `create_directory({"path": "/workspace/new_project/tests"})`
- **Purpose**: Build the target directory hierarchy according to the new architecture.

### Step 8: Move files to new locations
- **Tool**: `move_file` × 1-n times
- **Examples**:
  - `move_file({"source": "/workspace/old_project/main.py", "destination": "/workspace/new_project/src/main.py"})`
  - `move_file({"source": "/workspace/old_project/utils.py", "destination": "/workspace/new_project/src/utils/helpers.py"})`
- **Purpose**: Relocate files from old structure to new directories. Both `source` and `destination` must be **strings**.

### Step 9: Update internal references
- **Tool**: `read_text_file` → `edit_file` × 1-n times
- **Examples**:
  - `read_text_file({"path": "/workspace/new_project/src/main.py"})`
  - `edit_file({"path": "/workspace/new_project/src/main.py", "edits": [{"oldText": "from utils import helper", "newText": "from src.utils.helpers import helper"}]})`
- **Purpose**: Fix import statements and path references in source and config files. Read each file to confirm current import/path content, then use `edit_file` to precisely replace old paths with new ones. The `edits` parameter must be an **array of objects**.

### Step 10: Verify migration completeness
- **Tool**: `directory_tree`
- **Example**: `directory_tree({"path": "/workspace/new_project"})`
- **Purpose**: Confirm new structure is complete and old locations are empty.

### Step 11: Spot-check reference correctness
- **Tool**: `read_multiple_files`
- **Example**: `read_multiple_files({"paths": ["/workspace/new_project/src/main.py", "/workspace/new_project/config/settings.yaml"]})`
- **Purpose**: Re-read critical files to verify all path references point to valid new locations.

## Tools Involved

`list_allowed_directories`, `list_directory`, `directory_tree`, `search_files`, `read_multiple_files`, `read_text_file`, `create_directory`, `move_file`, `edit_file`

## Tips

- Map out all dependencies before moving any files — moving first and fixing later leads to broken references
- Move files in dependency order: shared modules first, then files that depend on them
- After moving a file, immediately update its internal imports before moving the next file
- Check both source code imports AND config file paths — config references are easy to miss
- All path parameters must be **strings**, `paths` must be an **array of strings**, and `edits` must be an **array of objects**
