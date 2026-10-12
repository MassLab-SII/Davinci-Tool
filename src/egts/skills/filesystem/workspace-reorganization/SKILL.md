# Workspace Reorganization

## Description

Analyze a messy workspace and systematically reorganize files into a clean directory structure. Involves scanning the current state, classifying files by type/purpose, designing a new layout, migrating files, and producing a reorganization report.

## Use Cases

- Sort mixed files in a flat root directory into categorized subdirectories
- Reorganize by file type (code/docs/data/config)
- Flatten deeply nested structures or consolidate scattered files
- Archive old files and clean up temporary artifacts

## Workflow

### Step 1: Discover allowed directories
- **Tool**: `list_allowed_directories`
- **Example**: `list_allowed_directories({})`
- **Purpose**: Discover which directories you are permitted to access. Use the returned paths as roots for all subsequent operations.

### Step 2: Inspect the workspace root
- **Tool**: `list_directory`
- **Example**: `list_directory({"path": "/workspace"})`
- **Purpose**: List the top-level contents to understand what exists before reorganization. Replace `/workspace` with the actual allowed path from Step 1.

### Step 3: Full structure scan
- **Tool**: `directory_tree`
- **Example**: `directory_tree({"path": "/workspace/messy_project"})`
- **Purpose**: Get the complete file tree to assess the current disorder. The `path` parameter must be a **string**.

### Step 4: Classify files by type
- **Tool**: `search_files` × 1-n times
- **Examples**:
  - `search_files({"path": "/workspace/messy_project", "pattern": "*.py"})`
  - `search_files({"path": "/workspace/messy_project", "pattern": "*.md"})`
  - `search_files({"path": "/workspace/messy_project", "pattern": "*.json"})`
- **Purpose**: Group files by extension to understand the type distribution. Both `path` and `pattern` must be **strings**.

### Step 5: Analyze file sizes
- **Tool**: `list_directory_with_sizes`
- **Example**: `list_directory_with_sizes({"path": "/workspace/messy_project", "sortBy": "size"})`
- **Purpose**: Identify large or unusual files to prioritize reorganization. The `path` parameter must be a **string**.

### Step 6: Sample-read key files
- **Tool**: `read_text_file` × 1-n times OR `read_multiple_files`
- **Examples**:
  - `read_text_file({"path": "/workspace/messy_project/unknown_file.txt"})`
  - `read_multiple_files({"paths": ["/workspace/messy_project/file1.dat", "/workspace/messy_project/file2.dat"]})`
- **Purpose**: Read selected files to understand their actual purpose and inform classification decisions. For `read_text_file`, `path` must be a **string**. For `read_multiple_files`, `paths` must be an **array of strings**.

### Step 7: Create new directory structure
- **Tool**: `create_directory` × 1-n times
- **Examples**:
  - `create_directory({"path": "/workspace/messy_project/code"})`
  - `create_directory({"path": "/workspace/messy_project/docs"})`
  - `create_directory({"path": "/workspace/messy_project/data"})`
  - `create_directory({"path": "/workspace/messy_project/config"})`
  - `create_directory({"path": "/workspace/messy_project/archive"})`
- **Purpose**: Build categorized directories based on analysis.

### Step 8: Migrate files
- **Tool**: `move_file` × 1-n times
- **Examples**:
  - `move_file({"source": "/workspace/messy_project/script.py", "destination": "/workspace/messy_project/code/script.py"})`
  - `move_file({"source": "/workspace/messy_project/README.md", "destination": "/workspace/messy_project/docs/README.md"})`
- **Purpose**: Move files from their original locations into the appropriate category directories. Both `source` and `destination` must be **strings**.

### Step 9: Generate reorganization report
- **Tool**: `write_file`
- **Example**: `write_file({"path": "/workspace/messy_project/REORGANIZATION_REPORT.md", "content": "# Reorganization Report\n\n## Changes\n- Moved script.py to code/\n..."})`
- **Purpose**: Document what was moved, the new structure, and any decisions made.

### Step 10: Verify final structure
- **Tool**: `directory_tree`
- **Example**: `directory_tree({"path": "/workspace/messy_project"})`
- **Purpose**: Confirm the reorganized layout is clean and logical.

## Tools Involved

`list_allowed_directories`, `list_directory`, `directory_tree`, `search_files`, `list_directory_with_sizes`, `read_text_file`, `read_multiple_files`, `create_directory`, `move_file`, `write_file`

## Tips

- Read ambiguous files before classifying them — file extensions don't always reflect actual content
- Create all target directories before starting file moves to avoid path errors
- When moving files, use descriptive destination names if renaming is appropriate (e.g., `project1_README.md`)
- The reorganization report should list every move operation for traceability
- All path parameters must be **strings**, never pass objects or arrays for single path arguments
