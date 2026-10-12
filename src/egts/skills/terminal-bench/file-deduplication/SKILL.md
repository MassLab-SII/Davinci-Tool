# File Deduplication

## Description

Find and remove duplicate files in the workspace by comparing content. Use hashing and diff tools to identify redundant copies, verify uniqueness, and clean up storage by removing or consolidating duplicates.

## Use Cases

- Find duplicate files across multiple directories by comparing content hashes
- Identify backup copies that are identical to originals
- Remove redundant files while preserving unique content
- Verify that files in different locations are truly identical before deduplication

## Workflow

### Step 1: Inventory — list all candidate files
- **Tool**: `search_files` or `list_directory`
- **Purpose**: Build a complete inventory of files to check.

### Step 2: Inspect — sample file contents
- **Tool**: `read_file`
- **Purpose**: Read sample files to understand what content exists.

### Step 3: Compare — identify duplicates
- **Tool**: `execute_command` with `md5sum`, `sha256sum`, `diff`
- **Purpose**: Generate and compare file hashes to identify duplicates.

### Step 4: Remove — clean up duplicates
- **Tool**: `execute_command` with `rm`
- **Purpose**: Remove identified duplicate files.

### Step 5: Verify — confirm cleanup
- **Tool**: `list_directory` or `search_files`
- **Purpose**: Verify only unique files remain and no data was lost.

## Tools Involved

`search_files`, `read_file`, `execute_command`, `list_directory`, `search_content`

## Tips

- Use `find . -type f -exec md5sum {} \; | sort | uniq -w32 -d` to find duplicates by hash
- Always `read_file` on suspected duplicates to verify before deleting
- Consider keeping one copy and removing the rest (not deleting all)
- Use `diff file1 file2` to confirm two files are truly identical
- Be careful with `rm` — verify each file before deletion
