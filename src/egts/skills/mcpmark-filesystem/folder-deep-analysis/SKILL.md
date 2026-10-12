# Folder Deep Analysis

## Description

Perform deep recursive analysis of folder structures — count files and folders at each level, calculate total sizes, classify files by extension, identify the deepest paths, and optionally mirror an existing directory structure with filtering rules and placeholder files.

## Use Cases

- Generate a comprehensive folder statistics report (total files, folders, size, depth, extension breakdown)
- Find the deepest path in a nested directory structure and calculate its depth level
- Mirror a directory structure into a new location, applying filtering rules (skip certain directories, rename others)
- Create a file type distribution report showing counts per extension across all subdirectories

## Workflow

### Step 1: Discover allowed directories
- **Tool**: `list_allowed_directories`
- **Example**: `list_allowed_directories({})`
- **Purpose**: Discover which directories you are permitted to access. Use the returned paths as roots for all subsequent operations.

### Step 2: Inspect the workspace root
- **Tool**: `list_directory`
- **Example**: `list_directory({"path": "/workspace"})`
- **Purpose**: List the top-level contents to locate the target directory for analysis. Replace `/workspace` with the actual allowed path from Step 1.

### Step 3: Get full directory tree
- **Tool**: `directory_tree`
- **Example**: `directory_tree({"path": "/workspace/complex_structure"})`
- **Purpose**: Get the complete recursive tree view. This reveals the full hierarchy, all files and folders, and helps identify the deepest paths. The `path` parameter must be a **string**.

### Step 4: List subdirectories with sizes
- **Tool**: `list_directory_with_sizes` × 1-n times
- **Examples**:
  - `list_directory_with_sizes({"path": "/workspace/complex_structure", "sortBy": "size"})`
  - `list_directory_with_sizes({"path": "/workspace/complex_structure/subdir_A", "sortBy": "size"})`
  - `list_directory_with_sizes({"path": "/workspace/complex_structure/subdir_A/nested", "sortBy": "size"})`
- **Purpose**: Traverse subdirectories level by level to collect per-file sizes. Aggregate totals across all directories. The `path` parameter must be a **string**.

### Step 5: Get file metadata for specific items
- **Tool**: `get_file_info` × 1-n times
- **Examples**:
  - `get_file_info({"path": "/workspace/complex_structure/subdir_A/nested/deep/file.txt"})`
  - `get_file_info({"path": "/workspace/complex_structure/large_file.dat"})`
- **Purpose**: Get precise size, timestamps, or permissions for specific files when exact metadata is needed. The `path` parameter must be a **string**.

### Step 6: Create mirrored structure (for structure mirroring tasks)
- **Tool**: `create_directory` × 1-n times
- **Examples**:
  - `create_directory({"path": "/workspace/mirror/subdir_A"})`
  - `create_directory({"path": "/workspace/mirror/subdir_A/nested"})`
  - `create_directory({"path": "/workspace/mirror/subdir_B_processed"})`
- **Purpose**: Recreate the directory structure in a new location, applying any filtering rules (skip directories with too many files, append suffixes to numbered directories).

### Step 7: Create placeholder files (for mirroring)
- **Tool**: `write_file` × 1-n times
- **Examples**:
  - `write_file({"path": "/workspace/mirror/subdir_A/placeholder.txt", "content": ""})`
  - `write_file({"path": "/workspace/mirror/subdir_B_processed/placeholder.txt", "content": ""})`
- **Purpose**: Place empty or placeholder files in the mirrored directories to mark their existence.

### Step 8: Write statistics report
- **Tool**: `write_file`
- **Example**: `write_file({"path": "/workspace/structure_analysis.txt", "content": "total number of files: 42\ntotal number of folders: 12\ntotal size of all files: 156789\n\ndepth: 5\ncomplex_structure/A/B/C/D\n\ntxt: 15\npy: 8\njpg: 10\nmov: 3\n(no extension): 6"})`
- **Purpose**: Write the comprehensive analysis report including file/folder counts, total size, deepest path with depth, and file type classification.

## Tools Involved

`list_allowed_directories`, `list_directory`, `directory_tree`, `list_directory_with_sizes`, `get_file_info`, `create_directory`, `write_file`

## Tips

- Use `directory_tree` first to get the overall picture, then `list_directory_with_sizes` to get exact sizes per directory
- When calculating total size, sum file sizes from all directories — do not count directory entries themselves
- For depth calculation, the root analysis directory is depth 0, its immediate subdirectories are depth 1, etc.
- Files without extensions (no `.` in the filename) should be classified as "(no extension)" in the type breakdown
- When mirroring, apply filtering rules before creating directories — this avoids needing to delete directories later
- Ignore `.DS_Store` files in counts unless the task specifically says to include them
- All path parameters must be **strings**
