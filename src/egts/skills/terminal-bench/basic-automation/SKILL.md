# Basic Shell Automation

## Description

Write and execute shell scripts for task automation in the workspace. Create scripts for file processing loops, conditional logic, text manipulation, and basic data pipelines. Covers the full script lifecycle: plan, write, test, and execute.

## Use Cases

- Write a script that loops through files and computes line counts
- Create a backup script that archives directories with timestamps
- Write a monitoring script that checks disk usage and reports warnings
- Build a file processing script that filters and transforms data
- Automate repetitive file operations with parameterized scripts

## Workflow

### Step 1: Understand — survey the environment
- **Tool**: `list_directory`, `read_file`, `get_environment_info`
- **Purpose**: Understand what files exist, what data is available, and what the script needs to do.

### Step 2: Write — create the script file
- **Tool**: `write_file`
- **Purpose**: Write the shell script with proper shebang (`#!/bin/bash`) and logic.

### Step 3: Execute — run the script
- **Tool**: `execute_command` with `bash script.sh`
- **Purpose**: Run the script and observe output.

### Step 4: Debug — check output and fix issues
- **Tool**: `read_file`, `execute_command`
- **Purpose**: Read error output, check for issues, and iterate on fixes.

### Step 5: Verify — confirm the result
- **Tool**: `list_directory`, `read_file`
- **Purpose**: Verify the script produced the expected output files or state changes.

## Tools Involved

`write_file`, `execute_command`, `read_file`, `list_directory`, `get_environment_info`

## Tips

- Always start scripts with `#!/bin/bash` and `set -e` for error handling
- Use `set -x` temporarily for debugging script execution
- Use `write_file` to create the script, then `execute_command` with `bash` to run it
- Test with a small subset of data first before running on the full dataset
- Add `echo` statements in scripts for visibility into execution progress
