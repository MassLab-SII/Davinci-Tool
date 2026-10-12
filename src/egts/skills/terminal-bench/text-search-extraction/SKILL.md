# Text Search & Extraction

## Description

Search for and extract text patterns from files in the workspace. Use grep-based search, file reading, and shell pipelines to find, filter, and extract specific data from text files, logs, CSVs, and JSON documents.

## Use Cases

- Search log files for error patterns and count occurrences
- Extract specific columns from CSV files for analysis
- Find configuration values across multiple config files
- Parse JSON log files and extract structured data fields
- Search for TODO comments or specific patterns in source code

## Workflow

### Step 1: Locate — find relevant files
- **Tool**: `search_files` or `get_directory_tree`
- **Purpose**: Identify which files to search through.

### Step 2: Search — find matching content
- **Tool**: `search_content`
- **Purpose**: Search for patterns within files to locate relevant data.

### Step 3: Read — examine results in context
- **Tool**: `read_file`
- **Purpose**: Read the surrounding content of matches for context.

### Step 4: Extract — pull out specific data
- **Tool**: `execute_command` with `grep`, `awk`, `cut`, `jq`
- **Purpose**: Extract structured data from matching lines.

### Step 5: Summarize — aggregate findings
- **Tool**: `execute_command` with `wc`, `sort`, `uniq`
- **Purpose**: Count, sort, and summarize extracted results.

## Tools Involved

`read_file`, `search_content`, `search_files`, `execute_command`, `get_directory_tree`

## Tips

- `search_content` with `recursive=true` searches all files in a directory tree
- Use `read_file` with `start_line` and `lines` to read specific portions of large files
- Pipe shell commands: `grep ... | sort | uniq -c | sort -rn` for frequency analysis
- For JSON files, use `execute_command` with `jq` for structured extraction
- For CSV files, use `awk -F,` or `cut -d,` to extract specific columns
