# System Inspection & Diagnostics

## Description

Inspect the execution environment: check OS information, resource usage (disk, memory, CPU), running processes, and environment variables. Generate comprehensive diagnostic reports for system health assessment.

## Use Cases

- Inspect system resource usage and identify top consumers
- Check disk usage across filesystems and directories
- List running processes and their resource consumption
- Review environment variables and system configuration
- Generate a comprehensive system health report

## Workflow

### Step 1: Overview — get environment summary
- **Tool**: `get_environment_info`
- **Purpose**: Get a high-level view of the system (OS, user, host, disk, memory).

### Step 2: Disk — analyze storage usage
- **Tool**: `execute_command` with `du -sh`, `df -h`
- **Purpose**: Find directories and volumes consuming the most space.

### Step 3: Processes — check running tasks
- **Tool**: `execute_command` with `ps aux`, `top -bn1`
- **Purpose**: Identify active processes and their resource usage.

### Step 4: Config — review environment and settings
- **Tool**: `execute_command` with `env`, `ulimit -a`
- **Purpose**: Check environment variables and system limits.

### Step 5: Report — document findings
- **Tool**: `write_file`
- **Purpose**: Generate a structured report of system health findings.

## Tools Involved

`get_environment_info`, `execute_command`, `get_directory_tree`, `search_files`, `write_file`, `read_file`, `list_directory`

## Tips

- Start with `get_environment_info` for a quick system overview
- Use `du -sh * | sort -rh | head` to find the largest directories
- `df -h` shows disk usage by filesystem; check Use% column for near-full volumes
- `ps aux --sort=-%mem | head` shows top memory-consuming processes
- Always generate a report file summarizing your findings for reference
