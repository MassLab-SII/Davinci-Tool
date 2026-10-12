# Content Transformation

## Description

Transform file contents through splitting, merging, text conversion, and counting operations. This skill covers dividing a large file into N equal-sized parts, combining multiple files into a single output, applying text transformations (uppercase, formatting), and counting words or characters across files.

## Use Cases

- Split a large text file into N equal-character-count parts in a new directory
- Merge the N smallest files in a directory into a single combined file
- Convert all text files in a folder to uppercase and count words per file
- Concatenate files in alphabetical order with section headers between them

## Workflow

### Step 1: Discover allowed directories
- **Tool**: `list_allowed_directories`
- **Example**: `list_allowed_directories({})`
- **Purpose**: Discover which directories you are permitted to access. Use the returned paths as roots for all subsequent operations.

### Step 2: Inspect the workspace root
- **Tool**: `list_directory`
- **Example**: `list_directory({"path": "/workspace"})`
- **Purpose**: List the top-level contents to understand what files are available. Replace `/workspace` with the actual allowed path from Step 1.

### Step 3: Identify target files
- **Tool**: `list_directory_with_sizes` or `search_files`
- **Examples**:
  - `list_directory_with_sizes({"path": "/workspace/data", "sortBy": "size"})`
  - `search_files({"path": "/workspace", "pattern": "*.txt"})`
- **Purpose**: Find and assess the files to transform. Use `list_directory_with_sizes` when file size matters (e.g., finding the N smallest/largest files), or `search_files` to find files by pattern. Both `path` and `pattern` must be **strings**.

### Step 4: Read source file(s)
- **Tool**: `read_text_file` or `read_multiple_files`
- **Examples**:
  - `read_text_file({"path": "/workspace/data/large_file.txt"})`
  - `read_multiple_files({"paths": ["/workspace/data/file1.txt", "/workspace/data/file2.txt", "/workspace/data/file3.txt"]})`
- **Purpose**: Read the content to transform. For splitting, read the single source file. For merging, read all files to combine. The `path` parameter must be a **string**, and `paths` must be an **array of strings**.

### Step 5: Create output directory
- **Tool**: `create_directory`
- **Example**: `create_directory({"path": "/workspace/data/split"})`
- **Purpose**: Create a directory for the transformed output files (e.g., split parts, converted files).

### Step 6: Write transformed output files
- **Tool**: `write_file` × 1-n times
- **Examples**:
  - For splitting: `write_file({"path": "/workspace/data/split/split_01.txt", "content": "...first part content..."})`
  - For merging: `write_file({"path": "/workspace/data/merged.txt", "content": "=== file1.txt ===\n...content...\n\n=== file2.txt ===\n...content..."})`
  - For uppercase: `write_file({"path": "/workspace/output/FILE1.txt", "content": "...UPPERCASED CONTENT..."})`
- **Purpose**: Write each transformed output. For splitting, divide the source content into equal character counts. For merging, concatenate with headers. For conversion, write the transformed text.

### Step 7: Write summary or answer file (if needed)
- **Tool**: `write_file`
- **Example**: `write_file({"path": "/workspace/data/answer.txt", "content": "file1.txt: 245 words\nfile2.txt: 312 words\ntotal: 557 words"})`
- **Purpose**: If the task requires counts, statistics, or a summary, write the results to a designated output file.

### Step 8: Verify results
- **Tool**: `read_text_file` × 1-n times
- **Examples**:
  - `read_text_file({"path": "/workspace/data/split/split_01.txt"})`
  - `read_text_file({"path": "/workspace/data/split/split_10.txt"})`
- **Purpose**: Spot-check the first and last output files to confirm the transformation was applied correctly.

## Tools Involved

`list_allowed_directories`, `list_directory`, `list_directory_with_sizes`, `search_files`, `read_text_file`, `read_multiple_files`, `create_directory`, `write_file`

## Tips

- When splitting by equal character count, calculate `total_chars / N` and split precisely — ensure all parts have the same character count (last part may absorb the remainder)
- When merging files, sort them in the required order (alphabetical, by size, etc.) before reading
- For text transformations, process each file's content entirely before writing — do not write partial results
- When counting words, use whitespace splitting as the default word boundary
- All path parameters must be **strings**, `paths` must be an **array of strings**, and numeric parameters like `tail`/`head` must be **numbers** (integers)
