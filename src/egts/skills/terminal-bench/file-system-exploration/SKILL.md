# File System Exploration

## Description

Explore the file system workspace by listing directories, reading file contents, searching for patterns, and analyzing file structures. This is a read-only investigation skill that builds understanding of the current workspace state before any modifications.

## Use Cases

- Navigate to a directory and list all files to understand the structure
- Search for specific content patterns across multiple files using grep
- Read file contents to understand what data is available
- Analyze directory trees to assess project scope
- Find files matching specific name patterns

## Workflow

### Step 1: Survey — list directory contents
- **Tool**: `list_directory`
- **Purpose**: See what files and subdirectories exist at a path.

### Step 2: Overview — get directory tree
- **Tool**: `get_directory_tree`
- **Purpose**: Understand the full hierarchy of the workspace or a subdirectory.

### Step 3: Inspect — read file contents
- **Tool**: `read_file`
- **Purpose**: Read file contents to understand what data is available.

### Step 4: Search — find patterns or files
- **Tool**: `search_content` or `search_files`
- **Purpose**: Locate specific content or files matching criteria.

### Step 5: Analyze — gather insights
- **Tool**: `execute_command` with `wc`, `du`, `diff`, `sort`
- **Purpose**: Count lines, measure sizes, compare files, sort content.

## Tools Involved

`list_directory`, `read_file`, `search_content`, `search_files`, `get_directory_tree`

## Tips

- Always start with `list_directory` to orient yourself
- Use `get_directory_tree` for a high-level view of the directory structure
- `search_content` is useful for finding specific text within files
- `search_files` helps locate files by name pattern across the directory tree
- All paths are relative to the current working directory
