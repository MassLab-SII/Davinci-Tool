# Text Transformation

## Description

Transform text across files in the workspace. Perform find-and-replace operations, reformat data files (CSV, JSON), clean whitespace, apply sed/awk expressions, and rewrite file contents to meet new format requirements.

## Use Cases

- Find and replace placeholder values across multiple config files
- Reformat log files into structured JSON
- Clean up inconsistent whitespace and formatting
- Apply sed expressions to modify file contents in-place
- Convert between data formats (CSV to JSON, text to structured output)

## Workflow

### Step 1: Audit — understand current format
- **Tool**: `read_file` and `search_content`
- **Purpose**: Examine the current content and identify what needs to change.

### Step 2: Plan — design the transformation
- **Tool**: `execute_command` with `head`, `wc`, `grep -c`
- **Purpose**: Understand the scope of changes needed.

### Step 3: Transform — apply changes
- **Tool**: `write_file` or `execute_command` with `sed`, `awk`, `sort`, `uniq`
- **Purpose**: Apply the transformation to the data.

### Step 4: Verify — check the output
- **Tool**: `read_file` and `search_content`
- **Purpose**: Confirm the transformation was applied correctly.

### Step 5: Clean up — remove temporary files
- **Tool**: `execute_command` with `rm`
- **Purpose**: Clean up any intermediate files created during transformation.

## Tools Involved

`read_file`, `write_file`, `search_content`, `execute_command`, `list_directory`

## Tips

- Always back up or read original files before transforming
- Use `sed -i` for in-place replacements, or write to new files for safety
- Use `write_file` for creating new files with transformed content
- Test transformations on a small subset or copy first
- Use `diff` to compare before/after when verifying transformations
