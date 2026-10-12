# File Deduplication & Search

## Description

Find duplicate files by comparing content across a directory, identify files containing specific patterns or shared substrings, and organize results by moving duplicates to a designated folder or writing detailed match reports.

## Use Cases

- Identify all files with identical content in a directory and move duplicates to a `duplicates/` folder
- Find files sharing a common substring of 30+ characters and report match positions
- Detect near-duplicate files across nested directories and generate a deduplication report
- Search for files containing specific keywords or patterns and list all matches

## Workflow

### Step 1: Discover allowed directories
- **Tool**: `list_allowed_directories`
- **Example**: `list_allowed_directories({})`
- **Purpose**: Discover which directories you are permitted to access. Use the returned paths as roots for all subsequent operations.

### Step 2: Inspect the workspace root
- **Tool**: `list_directory`
- **Example**: `list_directory({"path": "/workspace"})`
- **Purpose**: List the top-level contents to understand the workspace layout. Replace `/workspace` with the actual allowed path from Step 1.

### Step 3: List all target files
- **Tool**: `list_directory_with_sizes` or `search_files`
- **Examples**:
  - `list_directory_with_sizes({"path": "/workspace/data", "sortBy": "name"})`
  - `search_files({"path": "/workspace", "pattern": "*.txt"})`
- **Purpose**: Enumerate all files to compare. Using `list_directory_with_sizes` also reveals file sizes, which can be a quick pre-filter for duplicates (files with different sizes cannot be identical). Both `path` and `pattern` must be **strings**.

### Step 4: Batch-read files for comparison
- **Tool**: `read_multiple_files` × 1-n times
- **Examples**:
  - `read_multiple_files({"paths": ["/workspace/data/file1.txt", "/workspace/data/file2.txt", "/workspace/data/file3.txt", "/workspace/data/file4.txt"]})`
  - `read_multiple_files({"paths": ["/workspace/data/file5.txt", "/workspace/data/file6.txt", "/workspace/data/file7.txt", "/workspace/data/file8.txt"]})`
- **Purpose**: Read files in batches to compare their content. Group files by size for efficient duplicate detection — only compare files of the same size. The `paths` parameter must be an **array of strings**.

### Step 5: Read additional files (if needed)
- **Tool**: `read_text_file` × 1-n times
- **Examples**:
  - `read_text_file({"path": "/workspace/data/file9.txt"})`
  - `read_text_file({"path": "/workspace/data/file10.txt"})`
- **Purpose**: Read remaining files or re-read specific files for closer comparison when duplicates are suspected.

### Step 6: Create output directory
- **Tool**: `create_directory`
- **Example**: `create_directory({"path": "/workspace/data/duplicates"})`
- **Purpose**: Create a directory to hold duplicate files or search results.

### Step 7: Move duplicate files
- **Tool**: `move_file` × 1-n times
- **Examples**:
  - `move_file({"source": "/workspace/data/file3.txt", "destination": "/workspace/data/duplicates/file3.txt"})`
  - `move_file({"source": "/workspace/data/file7.txt", "destination": "/workspace/data/duplicates/file7.txt"})`
- **Purpose**: Move identified duplicate files to the duplicates directory, keeping one copy of each unique file in the original location. Both `source` and `destination` must be **strings**.

### Step 8: Write results report
- **Tool**: `write_file`
- **Example**: `write_file({"path": "/workspace/data/answer.txt", "content": "Duplicate groups found:\n\nGroup 1 (identical content):\n- file1.txt (kept)\n- file3.txt (moved to duplicates/)\n- file7.txt (moved to duplicates/)\n\nGroup 2 (identical content):\n- file2.txt (kept)\n- file8.txt (moved to duplicates/)"})`
- **Purpose**: Write a report documenting all duplicate groups, pattern matches, or search findings.

## Tools Involved

`list_allowed_directories`, `list_directory`, `search_files`, `read_text_file`, `read_multiple_files`, `list_directory_with_sizes`, `create_directory`, `move_file`, `write_file`

## Tips

- Pre-filter by file size before comparing content — files with different byte sizes cannot have identical content
- When comparing many files, batch reads with `read_multiple_files` are more efficient than individual `read_text_file` calls
- For substring matching, compare every pair of files and track match positions for the report
- When moving duplicates, keep one representative file in the original location and move the rest
- All path parameters must be **strings**, `paths` must be an **array of strings**, and both `source` and `destination` for `move_file` must be **strings**
