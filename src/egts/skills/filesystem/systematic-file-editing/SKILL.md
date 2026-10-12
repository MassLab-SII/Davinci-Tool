# Systematic File Editing

## Description

Systematically edit content across multiple files in a workspace. Search for target files, read to understand patterns, execute precise edits (renaming, extracting shared content, applying uniform changes), and verify consistency.

## Use Cases

- Rename identifiers, terms, or labels across multiple files
- Extract duplicated content into a shared file
- Apply uniform edits (headers, version numbers, formatting)
- Update references after restructuring
- Unify patterns across files

## Workflow

### Step 1: Discover allowed directories
- **Tool**: `list_allowed_directories`
- **Example**: `list_allowed_directories({})`
- **Purpose**: Discover which directories you are permitted to access.

### Step 2: Inspect the workspace root
- **Tool**: `list_directory`
- **Example**: `list_directory({"path": "/workspace"})`
- **Purpose**: List the top-level contents to understand the project layout.

### Step 3: Survey project structure
- **Tool**: `directory_tree`
- **Example**: `directory_tree({"path": "/workspace/project"})`
- **Purpose**: Get the full file tree to understand file distribution. The `path` parameter must be a **string**.

### Step 4: Search for target files
- **Tool**: `search_files`
- **Example**: `search_files({"path": "/workspace/project", "pattern": "*.txt"})`
- **Purpose**: Locate all files that need editing. Both `path` and `pattern` must be **strings**.

### Step 5: Batch-read files
- **Tool**: `read_multiple_files`
- **Example**: `read_multiple_files({"paths": ["/workspace/project/docs/file1.txt", "/workspace/project/docs/file2.txt"]})`
- **Purpose**: Read files to understand patterns and identify edit targets. The `paths` parameter must be an **array of strings**.

### Step 6: Deep-read key files
- **Tool**: `read_text_file` × 1-n times
- **Example**: `read_text_file({"path": "/workspace/project/docs/main.txt"})`
- **Purpose**: Carefully read specific files to pinpoint exact edit locations.

### Step 7: Execute edits
- **Tool**: `edit_file` × 1-n times
- **Examples**:
  - `edit_file({"path": "/workspace/project/docs/file1.txt", "edits": [{"oldText": "version 1.0", "newText": "version 2.0"}]})`
  - `edit_file({"path": "/workspace/project/docs/file2.txt", "edits": [{"oldText": "version 1.0", "newText": "version 2.0"}]})`
- **Purpose**: Apply precise edits across files. The `edits` parameter must be an **array of objects** with `oldText` and `newText` fields.

### Step 8: Create shared file if needed
- **Tool**: `write_file`
- **Example**: `write_file({"path": "/workspace/project/common.txt", "content": "Shared content extracted from multiple files"})`
- **Purpose**: If extracting shared content, create the new file.

### Step 9: Verify modifications
- **Tool**: `read_multiple_files`
- **Example**: `read_multiple_files({"paths": ["/workspace/project/docs/file1.txt", "/workspace/project/docs/file2.txt"]})`
- **Purpose**: Re-read all edited files to confirm consistency.

### Step 10: Generate change summary
- **Tool**: `write_file`
- **Example**: `write_file({"path": "/workspace/project/CHANGES.md", "content": "# Edit Summary\n\n## Modified Files\n- file1.txt: Updated version\n- file2.txt: Updated version"})`
- **Purpose**: Document changes for audit trail.

## Tools Involved

`list_allowed_directories`, `list_directory`, `directory_tree`, `search_files`, `read_multiple_files`, `read_text_file`, `edit_file`, `write_file`

## Tips

- Always read files before editing to get exact `oldText` content
- Each file may have slight variations — base edits on actual content
- Process files in consistent order for reproducibility
- When extracting shared content, update original files to reference the new file
- All path parameters must be **strings**, `paths` and `edits` must be **arrays**
