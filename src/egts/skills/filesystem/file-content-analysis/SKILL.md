# File Content Analysis

## Description

Analyze file contents to identify patterns, diagnose issues, extract insights, and generate reports. Search for specific content, understand structure, trace relationships, identify anomalies, and produce analysis outputs.

## Use Cases

- Locate specific content or patterns across files
- Diagnose issues by analyzing file contents
- Extract key information and generate summary reports
- Trace relationships and dependencies between files
- Identify anomalies, errors, or missing elements

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
- **Purpose**: Get the full file tree to understand organization. The `path` parameter must be a **string**.

### Step 4: Locate target files
- **Tool**: `search_files` × 1-n times
- **Examples**:
  - `search_files({"path": "/workspace/project", "pattern": "*.txt"})`
  - `search_files({"path": "/workspace/project/logs", "pattern": "*.log"})`
- **Purpose**: Find files relevant to the analysis task. Both `path` and `pattern` must be **strings**.

### Step 5: Assess file sizes
- **Tool**: `list_directory_with_sizes` or `get_file_info`
- **Examples**:
  - `list_directory_with_sizes({"path": "/workspace/project/logs"})`
  - `get_file_info({"path": "/workspace/project/data/large.log"})`
- **Purpose**: Check file sizes to determine reading strategy (full read vs. tail for large files).

### Step 6: Batch-read files
- **Tool**: `read_multiple_files` × 1-n times
- **Example**: `read_multiple_files({"paths": ["/workspace/project/data/file1.txt", "/workspace/project/data/file2.txt"]})`
- **Purpose**: Read multiple files to search for patterns or compare contents. The `paths` parameter must be an **array of strings**.

### Step 7: Deep-read key files
- **Tool**: `read_text_file` × 1-n times
- **Examples**:
  - `read_text_file({"path": "/workspace/project/logs/error.log"})`
  - `read_text_file({"path": "/workspace/project/config.json"})`
- **Purpose**: Carefully read specific files to extract detailed information or diagnose issues.

### Step 8: Apply fixes if needed
- **Tool**: `edit_file` × 1-n times
- **Example**: `edit_file({"path": "/workspace/project/data/config.txt", "edits": [{"oldText": "timeout=30", "newText": "timeout=60"}]})`
- **Purpose**: Fix identified issues. The `edits` parameter must be an **array of objects**.

### Step 9: Generate analysis report
- **Tool**: `write_file`
- **Example**: `write_file({"path": "/workspace/project/analysis_report.md", "content": "# Analysis Report\n\n## Findings\n- Pattern X found in 5 files\n- Issue Y identified in file Z\n\n## Recommendations\n..."})`
- **Purpose**: Write structured analysis results with findings and recommendations.

### Step 10: Verify outputs
- **Tool**: `read_text_file`
- **Example**: `read_text_file({"path": "/workspace/project/analysis_report.md"})`
- **Purpose**: Confirm the report is correctly generated.

## Tools Involved

`list_allowed_directories`, `list_directory`, `directory_tree`, `search_files`, `list_directory_with_sizes`, `get_file_info`, `read_multiple_files`, `read_text_file`, `edit_file`, `write_file`

## Tips

- Use `search_files` with specific patterns to narrow down candidate files quickly
- Check file sizes before reading — use tail strategy for very large files
- When analyzing patterns, read multiple files in batch for efficiency
- For issue diagnosis, read the complete file to understand context
- Generate structured reports with clear sections: findings, analysis, recommendations
- All path parameters must be **strings**, `paths` must be an **array of strings**
