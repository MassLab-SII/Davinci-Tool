# Metadata-Based Classification

## Description

Classify and organize files based on their metadata properties — sort files by size into category directories (small/medium/large), organize by creation or modification timestamps (year/month/day hierarchy), rename files based on attributes, and generate classification summary reports.

## Use Cases

- Classify files into small/medium/large directories based on byte-size thresholds
- Organize files into year/month subdirectories based on creation or modification timestamps
- Find and rename the largest or smallest file in a directory
- Sort files by extension type and move into categorized folders

## Workflow

### Step 1: Discover allowed directories
- **Tool**: `list_allowed_directories`
- **Example**: `list_allowed_directories({})`
- **Purpose**: Discover which directories you are permitted to access. Use the returned paths as roots for all subsequent operations.

### Step 2: Inspect the workspace root
- **Tool**: `list_directory`
- **Example**: `list_directory({"path": "/workspace"})`
- **Purpose**: List the top-level contents to understand the workspace layout. Replace `/workspace` with the actual allowed path from Step 1.

### Step 3: List files with sizes
- **Tool**: `list_directory_with_sizes`
- **Example**: `list_directory_with_sizes({"path": "/workspace/files", "sortBy": "size"})`
- **Purpose**: Get all files with their sizes to determine classification thresholds and plan the categorization. The `path` parameter must be a **string**.

### Step 4: Gather detailed metadata
- **Tool**: `get_file_info` × 1-n times
- **Examples**:
  - `get_file_info({"path": "/workspace/files/document.txt"})`
  - `get_file_info({"path": "/workspace/files/photo.jpg"})`
  - `get_file_info({"path": "/workspace/files/video.MOV"})`
- **Purpose**: Get detailed metadata for each file including size, creation time, modification time, and permissions. This is essential for timestamp-based classification. The `path` parameter must be a **string**.

### Step 5: Create category directories
- **Tool**: `create_directory` × 1-n times
- **Examples**:
  - For size classification:
    - `create_directory({"path": "/workspace/files/small_files"})`
    - `create_directory({"path": "/workspace/files/medium_files"})`
    - `create_directory({"path": "/workspace/files/large_files"})`
  - For time classification:
    - `create_directory({"path": "/workspace/files/2024/January"})`
    - `create_directory({"path": "/workspace/files/2024/February"})`
- **Purpose**: Create the category directories where files will be sorted into.

### Step 6: Move files into categories
- **Tool**: `move_file` × 1-n times
- **Examples**:
  - `move_file({"source": "/workspace/files/small_doc.txt", "destination": "/workspace/files/small_files/small_doc.txt"})`
  - `move_file({"source": "/workspace/files/large_video.MOV", "destination": "/workspace/files/large_files/large_video.MOV"})`
- **Purpose**: Move each file into its appropriate category directory based on the classification rules. Both `source` and `destination` must be **strings**.

### Step 7: Write classification report
- **Tool**: `write_file`
- **Example**: `write_file({"path": "/workspace/files/classification_report.txt", "content": "File Classification Report\n\nSmall files (<300 bytes): 5 files\n- small_doc.txt (128 bytes)\n- notes.txt (245 bytes)\n...\n\nMedium files (300-700 bytes): 3 files\n...\n\nLarge files (>700 bytes): 4 files\n..."})`
- **Purpose**: Document the classification results including which files were moved where and the criteria used.

### Step 8: Verify final organization
- **Tool**: `list_directory` × 1-n times
- **Examples**:
  - `list_directory({"path": "/workspace/files/small_files"})`
  - `list_directory({"path": "/workspace/files/large_files"})`
- **Purpose**: Confirm files have been correctly moved to their designated category directories.

## Tools Involved

`list_allowed_directories`, `list_directory`, `list_directory_with_sizes`, `get_file_info`, `create_directory`, `move_file`, `write_file`, `read_text_file`

## Tips

- Always use `get_file_info` for timestamp-based classification — `list_directory_with_sizes` only provides file sizes, not timestamps
- When classifying by size, apply threshold rules inclusively on boundaries (e.g., 300 bytes falls in "medium" if the range is 300-700 inclusive)
- Handle all file types regardless of extension — classification should be by metadata, not by file type
- When renaming via `move_file`, use the same directory but a different filename as the destination
- All path parameters must be **strings**, and both `source` and `destination` for `move_file` must be **strings**
