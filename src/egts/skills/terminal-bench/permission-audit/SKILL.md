# Permission Audit & Security Review

## Description

Audit file and directory permissions in the workspace, identify security issues (world-writable files, overly permissive configs, exposed secrets), fix insecure configurations, and verify corrections through systematic checks.

## Use Cases

- Find world-writable files that should be restricted
- Check configuration files for proper permission settings
- Identify files with exposed secrets (API keys, passwords) in readable locations
- Fix insecure permission configurations
- Generate a security audit report with findings and remediations

## Workflow

### Step 1: Scan — find files with risky permissions
- **Tool**: `execute_command` with `find -perm`, `ls -la`
- **Purpose**: Identify world-writable files, SUID binaries, and other permission issues.

### Step 2: Inspect — review flagged files
- **Tool**: `read_file`, `list_directory`
- **Purpose**: Check the content of files with suspicious permissions.

### Step 3: Classify — categorize findings by severity
- **Tool**: `execute_command` with `stat`, `ls -la`
- **Purpose**: Determine which issues are critical vs. informational.

### Step 4: Fix — correct insecure permissions
- **Tool**: `execute_command` with `chmod`, `chown`
- **Purpose**: Apply appropriate permission fixes (e.g., `chmod 600` for sensitive files).

### Step 5: Verify — confirm fixes were applied
- **Tool**: `execute_command` with `ls -la`, `find -perm`
- **Purpose**: Re-scan to verify permissions are now correct.

### Step 6: Report — document findings
- **Tool**: `write_file`
- **Purpose**: Generate an audit report with findings, actions taken, and verification.

## Tools Involved

`execute_command`, `list_directory`, `read_file`, `get_environment_info`, `search_files`, `write_file`

## Tips

- `find . -type f -perm -o+w` finds world-writable files
- `find . -type f -perm /6000` finds SUID/SGID files
- `ls -la` shows permissions in the first column (e.g., `-rw-r--r--`)
- Sensitive files (passwords, keys, configs) should be `600` or `640`, never `644` or `666`
- Directories with sensitive content should be `700` or `750`
- Always re-scan after fixing to verify the changes took effect
