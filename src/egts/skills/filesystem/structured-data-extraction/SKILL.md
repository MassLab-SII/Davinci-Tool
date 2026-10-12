# Structured Data Extraction

## Description

Parse and extract structured data from files in various formats — identify repeating record patterns, extract fields from HTML/CSV/text/JSON files, deduplicate entries, aggregate by categories, and generate organized outputs with index files and summary reports. Works with any file collection containing parseable structured content.

## Use Cases

- Extract key-value fields from text-based record files (e.g., name, ID, score, status) and compute aggregated statistics
- Parse HTML files to extract metadata from tags and attributes, then organize files by extracted categories
- Process CSV or delimited data files to filter, sort, and generate formatted reports
- Deduplicate entries across multiple files based on extracted field values
- Organize files into category directories based on extracted metadata and generate index documents
- Extract structured information from configuration files, log entries, or any files with consistent field patterns

## Workflow

### Step 1: Discover allowed directories
- **Tool**: `list_allowed_directories`
- **Example**: `list_allowed_directories({})`
- **Purpose**: Discover which directories you are permitted to access. Use the returned paths as roots for all subsequent operations.

### Step 2: Inspect the workspace root
- **Tool**: `list_directory`
- **Example**: `list_directory({"path": "/workspace"})`
- **Purpose**: List the top-level contents to understand the data layout. Replace `/workspace` with the actual allowed path from Step 1.

### Step 3: Survey data structure
- **Tool**: `directory_tree` or `search_files`
- **Examples**:
  - `directory_tree({"path": "/workspace/data"})`
  - `search_files({"path": "/workspace", "pattern": "*.html"})`
  - `search_files({"path": "/workspace", "pattern": "*.txt"})`
- **Purpose**: Understand the full scope of data files — how many files, what types, and where they are located. Both `path` and `pattern` must be **strings**.

### Step 4: Read sample files to understand format
- **Tool**: `read_text_file` × 1-n times
- **Examples**:
  - `read_text_file({"path": "/workspace/data/records/record_001.txt"})`
  - `read_text_file({"path": "/workspace/data/pages/page_001.html"})`
  - `read_text_file({"path": "/workspace/data/entries.csv", "head": 20})`
- **Purpose**: Read representative files to understand the data format, identify parseable fields, and plan the extraction strategy. The `path` parameter must be a **string**, and `head` must be a **number** (integer).

### Step 5: Batch-read data files
- **Tool**: `read_multiple_files` × 1-n times
- **Examples**:
  - `read_multiple_files({"paths": ["/workspace/data/records/record_001.txt", "/workspace/data/records/record_002.txt", "/workspace/data/records/record_003.txt"]})`
  - `read_multiple_files({"paths": ["/workspace/data/pages/page_001.html", "/workspace/data/pages/page_002.html", "/workspace/data/pages/page_003.html"]})`
- **Purpose**: Read files in batches to extract structured data. Parse each file for the relevant fields (names, IDs, values, metadata tags). The `paths` parameter must be an **array of strings**.

### Step 6: Create output directory structure
- **Tool**: `create_directory` × 1-n times
- **Examples**:
  - `create_directory({"path": "/workspace/organized/2023"})`
  - `create_directory({"path": "/workspace/organized/2022"})`
  - `create_directory({"path": "/workspace/organized/2021"})`
- **Purpose**: Create directories for organizing files by extracted categories (year, author, grade, etc.).

### Step 7: Move files into organized structure
- **Tool**: `move_file` × 1-n times
- **Examples**:
  - `move_file({"source": "/workspace/data/pages/page_042.html", "destination": "/workspace/organized/2023/page_042.html"})`
  - `move_file({"source": "/workspace/data/pages/page_015.html", "destination": "/workspace/organized/2022/page_015.html"})`
- **Purpose**: Move files into the organized directory structure based on extracted metadata. Both `source` and `destination` must be **strings**.

### Step 8: Generate index and summary files
- **Tool**: `write_file` × 1-n times
- **Examples**:
  - `write_file({"path": "/workspace/organized/2023/INDEX.md", "content": "# 2023 Entries\n\n| ID | Title | Category | Local Path |\n|----|-------|----------|------------|\n| 042 | Entry Title | CategoryA | page_042.html |"})`
  - `write_file({"path": "/workspace/organized/SUMMARY.md", "content": "# Collection Summary\n\n| Category | Count | Index Link |\n|----------|-------|------------|\n| 2023 | 7 | [View Index](2023/INDEX.md) |"})`
  - `write_file({"path": "/workspace/duplicates.txt", "content": "name: John Smith\ncount: 3\nids: R001, R042, R098\n\nname: Emily Chen\ncount: 2\nids: R015, R067"})`
- **Purpose**: Write structured output files — index files per category, summary tables, and formatted reports with extracted data.

## Tools Involved

`list_allowed_directories`, `list_directory`, `search_files`, `directory_tree`, `read_text_file`, `read_multiple_files`, `create_directory`, `move_file`, `write_file`

## Tips

- Read sample files first to identify the consistent field pattern (e.g., "Key: Value" lines, CSV columns, HTML tags) before batch processing
- When parsing HTML files, look for `<meta>` tags, heading tags, or table structures as primary data sources
- For delimited files (CSV, TSV), identify the delimiter and header row before extracting fields
- When generating index files with markdown tables, ensure consistent column alignment and proper escaping
- Process files in batches of 3-5 with `read_multiple_files` rather than one at a time — this is more efficient
- When deduplicating, define the key field(s) clearly — exact match vs. fuzzy match produces different results
- All path parameters must be **strings**, `paths` must be an **array of strings**, and numeric parameters must be **numbers** (integers)
