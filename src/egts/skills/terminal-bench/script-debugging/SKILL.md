# Script Debugging & Repair

## Description

Debug and fix broken or incomplete shell scripts in the workspace. Read error outputs, identify failures through systematic diagnosis, apply targeted patches, and verify corrections through iterative testing.

## Use Cases

- Debug a script that produces unexpected output or errors
- Fix syntax errors, missing shebangs, or permission issues
- Add error handling to scripts that fail silently
- Repair scripts with incorrect path references or variable usage
- Test edge cases and add input validation to existing scripts

## Workflow

### Step 1: Read — examine the script
- **Tool**: `read_file`
- **Purpose**: Read the complete script to understand its intended behavior.

### Step 2: Execute — reproduce the failure
- **Tool**: `execute_command` with `bash -x script.sh`
- **Purpose**: Run with debug tracing to see each command and its output.

### Step 3: Diagnose — identify the root cause
- **Tool**: `read_file` (re-read relevant sections), `execute_command` (test individual commands)
- **Purpose**: Isolate which line or logic is failing and why.

### Step 4: Fix — apply the correction
- **Tool**: `write_file`
- **Purpose**: Rewrite the script with the fix applied.

### Step 5: Test — verify the fix
- **Tool**: `execute_command`
- **Purpose**: Run the fixed script and confirm it produces correct output.

### Step 6: Harden — add safeguards
- **Tool**: `write_file`
- **Purpose**: Add `set -e`, input validation, and error messages.

## Tools Involved

`read_file`, `write_file`, `execute_command`, `search_content`, `list_directory`

## Tips

- Run scripts with `bash -x` to trace each command execution
- Check exit codes: `$?` after each command
- Test individual commands from the script in isolation
- Common issues: missing `#!/bin/bash`, wrong paths, unquoted variables, missing permissions
- Add `|| echo "FAILED: command"` after critical commands during debugging
