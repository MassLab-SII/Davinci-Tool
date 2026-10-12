# Data Aggregation & Reporting

## Description

Collect and aggregate data from diverse file sources scattered across a workspace — scan files of various types, extract target information (numerical values, records, attributes, metadata), perform calculations (totals, averages, counts, rankings), and generate structured summary reports in the required format. Works with any workspace containing data spread across multiple files and directories.

## Use Cases

- Scan files across a workspace to extract numerical data and generate a summary report with totals and averages
- Read information scattered across various file types and compile a unified, deduplicated list
- Extract date-based events from multiple documents and produce a chronological report
- Aggregate file metadata (sizes, types, counts) across directories and generate a statistics report
- Collect key-value data from heterogeneous file formats and produce a consolidated output
- Identify and rank items across files based on extracted attributes (price, frequency, score, etc.)

## Workflow

### Step 1: Discover allowed directories
- **Tool**: `list_allowed_directories`
- **Example**: `list_allowed_directories({})`
- **Purpose**: Discover which directories you are permitted to access. Use the returned paths as roots for all subsequent operations.

### Step 2: Inspect the workspace root
- **Tool**: `list_directory`
- **Example**: `list_directory({"path": "/workspace"})`
- **Purpose**: List the top-level contents to understand the workspace layout and file distribution. Replace `/workspace` with the actual allowed path from Step 1.

### Step 3: Discover all data sources
- **Tool**: `search_files` × 1-n times and/or `list_directory_with_sizes`
- **Examples**:
  - `search_files({"path": "/workspace", "pattern": "*.txt"})`
  - `search_files({"path": "/workspace", "pattern": "*.csv"})`
  - `search_files({"path": "/workspace", "pattern": "*.md"})`
  - `list_directory_with_sizes({"path": "/workspace/documents", "sortBy": "name"})`
- **Purpose**: Find all files that may contain relevant data. Search by multiple patterns to cover different file types. Both `path` and `pattern` must be **strings**.

### Step 4: Read initial batch of files
- **Tool**: `read_multiple_files` × 1-n times
- **Examples**:
  - `read_multiple_files({"paths": ["/workspace/documents/data1.txt", "/workspace/documents/data2.csv", "/workspace/notes/info.txt"]})`
  - `read_multiple_files({"paths": ["/workspace/reports/report1.txt", "/workspace/reports/report2.txt", "/workspace/logs/summary.log"]})`
- **Purpose**: Read files in batches to extract relevant data. Identify which files contain the target information. The `paths` parameter must be an **array of strings**.

### Step 5: Read additional files for complete coverage
- **Tool**: `read_text_file` × 1-n times
- **Examples**:
  - `read_text_file({"path": "/workspace/data/values.txt"})`
  - `read_text_file({"path": "/workspace/records/entries.csv"})`
  - `read_text_file({"path": "/workspace/metadata/info.json"})`
- **Purpose**: Read remaining files discovered in Step 3 that weren't covered in the initial batch. Ensure complete data coverage. The `path` parameter must be a **string**.

### Step 6: Check file metadata (if relevant)
- **Tool**: `get_file_info` × 1-n times
- **Examples**:
  - `get_file_info({"path": "/workspace/data/large_file.dat"})`
  - `get_file_info({"path": "/workspace/documents/old_report.txt"})`
- **Purpose**: Get file metadata when timestamps, sizes, or other properties are relevant to the aggregation task.

### Step 7: Create output directory (if needed)
- **Tool**: `create_directory`
- **Example**: `create_directory({"path": "/workspace/reports"})`
- **Purpose**: Create a directory for organized output files if the task requires multiple report files.

### Step 8: Generate summary report
- **Tool**: `write_file`
- **Examples**:
  - For numerical aggregation: `write_file({"path": "/workspace/summary.txt", "content": "documents/data1.txt;45.99\ndocuments/data2.csv;12.99\nnotes/info.txt;23.50\nTotal: 82.48"})`
  - For list compilation: `write_file({"path": "/workspace/compiled_list.txt", "content": "Entry 1: Value A\nSource: file1.txt\n\nEntry 2: Value B\nSource: file2.txt\n\nEntry 3: Value C\nSource: file3.csv"})`
  - For chronological report: `write_file({"path": "/workspace/timeline.md", "content": "# Timeline\n\n| Date | Event | Source |\n|------|-------|--------|\n| 2024-01-15 | Event A | notes.txt |\n| 2024-02-01 | Event B | report.txt |"})`
- **Purpose**: Write the final aggregated report with all extracted data, calculations, and formatting as required by the task.

### Step 9: Organize source files (if required)
- **Tool**: `move_file` × 1-n times (only if the task requires reorganization)
- **Examples**:
  - `move_file({"source": "/workspace/scattered_file.txt", "destination": "/workspace/organized/documents/scattered_file.txt"})`
- **Purpose**: If the task also requires organizing the source files into a clean structure, move them into appropriate directories.

## Tools Involved

`list_allowed_directories`, `list_directory`, `search_files`, `list_directory_with_sizes`, `get_file_info`, `read_text_file`, `read_multiple_files`, `create_directory`, `write_file`

## Tips

- Start broad (search all file types) then narrow down — relevant data may be in unexpected file formats
- When aggregating numerical values, ensure consistent units and precision (e.g., round to 2 decimal places for currency-like values)
- Use relative paths in reports (from the workspace root) when listing file sources for traceability
- When multiple values exist for the same item, clarify the aggregation rule (sum, average, min, max, latest) based on the task
- Read files completely — a file that contains one relevant entry likely has more
- For large workspaces, use `search_files` with multiple patterns to ensure no relevant files are missed
- All path parameters must be **strings**, `paths` must be an **array of strings**, and numeric parameters must be **numbers** (integers)
