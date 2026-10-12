# Data Aggregation & Merging

## Description

Merge, deduplicate, sort, and aggregate data from multiple files in the workspace. Combine CSV/JSON sources, compute statistics across datasets, and produce consolidated output files.

## Use Cases

- Merge multiple CSV files, deduplicate rows, and sort by a column
- Combine JSON log files and extract aggregate statistics
- Compute summary statistics (count, sum, avg, min, max) across datasets
- Join related data from multiple sources into a single report
- Concatenate and normalize data from different formats

## Workflow

### Step 1: Inventory — identify all data sources
- **Tool**: `list_directory`, `search_files`
- **Purpose**: Find all files that need to be merged or aggregated.

### Step 2: Inspect — understand each source's structure
- **Tool**: `read_file`, `search_content`
- **Purpose**: Read headers, sample rows, understand schema and format.

### Step 3: Merge — combine data sources
- **Tool**: `execute_command` with `cat`, `awk`, `jq`, `sort`
- **Purpose**: Concatenate files, handle headers, normalize formats.

### Step 4: Deduplicate — remove redundant entries
- **Tool**: `execute_command` with `sort -u`, `uniq`, `awk`
- **Purpose**: Remove duplicate rows or records.

### Step 5: Aggregate — compute summary statistics
- **Tool**: `execute_command` with `awk`, `wc`, `sort`
- **Purpose**: Compute counts, sums, averages, and other statistics.

### Step 6: Export — write final output
- **Tool**: `write_file`
- **Purpose**: Save the consolidated, deduplicated, and aggregated result.

## Tools Involved

`read_file`, `search_content`, `execute_command`, `write_file`, `list_directory`, `search_files`

## Tips

- For CSV merging: handle headers carefully — keep only the first file's header
- `sort -t, -k2 -n` sorts CSV numerically by column 2
- `awk -F, '{sum+=$3} END {print sum/NR}'` computes column averages
- Use `jq -s` to slurp multiple JSON objects into an array
- Always `read_file` on a few rows of the final output to verify correctness
