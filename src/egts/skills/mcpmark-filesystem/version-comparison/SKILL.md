# Version Comparison

## Description

Analyze multiple versions of any document or file to track changes, extract embedded comments and annotations, identify per-contributor modifications across versions, and generate structured comparison reports. Works with versioned files of any type — legal agreements, technical specifications, configuration files, manuscripts, data schemas, or any content that evolves through numbered revisions (v0, v1, ... vN).

## Use Cases

- Compare multiple versions of a document and generate a diff report highlighting what changed between versions
- Track per-contributor modifications across versions (who changed what, how many times)
- Trace how a specific section or field evolved from one version to the next
- Extract and count inline comments or annotations embedded across document versions
- Analyze configuration or schema files across versions to identify added, removed, or modified fields
- Review versioned meeting notes, proposals, or drafts to summarize the revision history

## Workflow

### Step 1: Discover allowed directories
- **Tool**: `list_allowed_directories`
- **Example**: `list_allowed_directories({})`
- **Purpose**: Discover which directories you are permitted to access. Use the returned paths as roots for all subsequent operations.

### Step 2: Inspect the workspace root
- **Tool**: `list_directory`
- **Example**: `list_directory({"path": "/workspace"})`
- **Purpose**: List the top-level contents to locate the versioned document directory. Replace `/workspace` with the actual allowed path from Step 1.

### Step 3: Find versioned documents
- **Tool**: `search_files` or `list_directory`
- **Examples**:
  - `search_files({"path": "/workspace/documents", "pattern": "*v*.txt"})`
  - `search_files({"path": "/workspace/configs", "pattern": "*_v*.yaml"})`
  - `list_directory({"path": "/workspace/versions"})`
- **Purpose**: Enumerate all version files to understand the version range (v0 through vN) and file naming convention. Both `path` and `pattern` must be **strings**.

### Step 4: Read target versions
- **Tool**: `read_multiple_files` × 1-n times
- **Examples**:
  - `read_multiple_files({"paths": ["/workspace/documents/spec_v5.txt", "/workspace/documents/spec_v6.txt", "/workspace/documents/spec_v7.txt"]})`
  - `read_multiple_files({"paths": ["/workspace/configs/app_v0.yaml", "/workspace/configs/app_v1.yaml", "/workspace/configs/app_v2.yaml"]})`
- **Purpose**: Read the specific versions needed for comparison. Read in batches of 3-4 versions at a time. The `paths` parameter must be an **array of strings**.

### Step 5: Read additional versions for full context
- **Tool**: `read_text_file` × 1-n times
- **Examples**:
  - `read_text_file({"path": "/workspace/documents/spec_v8.txt"})`
  - `read_text_file({"path": "/workspace/configs/app_v9.yaml"})`
- **Purpose**: Read remaining versions or re-read specific versions for deeper analysis of particular sections or changes. The `path` parameter must be a **string**.

### Step 6: Read baseline version (if needed)
- **Tool**: `read_text_file`
- **Example**: `read_text_file({"path": "/workspace/documents/spec_v0.txt"})`
- **Purpose**: Read the original version as a baseline for understanding the full evolution of changes.

### Step 7: Generate comparison report
- **Tool**: `write_file`
- **Examples**:
  - For change summary: `write_file({"path": "/workspace/version_diff.txt", "content": "Changes from v5 to v7:\n- Section 2.1: Added new requirement\n- Section 3.4: Modified timeout value from 30s to 60s\n- Section 5: Removed deprecated API endpoint"})`
  - For contributor tracking: `write_file({"path": "/workspace/contributor_report.txt", "content": "Alice:\n- v3: Modified database schema\n- v5: Added error handling\nTotal: 8 changes\n\nBob:\n- v4: Updated configuration\nTotal: 3 changes"})`
  - For evolution trace: `write_file({"path": "/workspace/field_evolution.txt", "content": "timeout field evolution:\nv1: timeout=30\nv3: timeout=45 (increased for stability)\nv5: timeout=60 (final value)\nv7: unchanged"})`
- **Purpose**: Write the analysis results in the format required by the task — change summaries, contributor tracking, or field evolution traces.

## Tools Involved

`list_allowed_directories`, `list_directory`, `search_files`, `read_text_file`, `read_multiple_files`, `write_file`

## Tips

- When comparing versions, identify the type of change: additions, deletions, modifications, or reorderings
- Read versions in chronological order (v0, v1, v2...) to track the evolution of changes systematically
- For efficiency, use `read_multiple_files` for initial batch reading, then `read_text_file` for targeted re-reads of specific versions
- If documents contain inline annotations (e.g., `[author:content]`, `<!-- comment -->`), parse them to extract contributor information
- For structured files (YAML, JSON, CSV), compare field-by-field rather than line-by-line for more meaningful diffs
- All path parameters must be **strings**, and `paths` must be an **array of strings**
