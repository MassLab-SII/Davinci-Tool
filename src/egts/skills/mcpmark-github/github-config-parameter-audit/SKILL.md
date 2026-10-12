# GitHub Config Parameter Audit

## Description

Audit code and configuration parameters across repository files, compare intended versus actual settings, and patch or report the configuration finding.

## Use Cases

- Find model, training, CI, or package configuration parameters
- Compare duplicate or conflicting parameter definitions
- Patch incorrect defaults or document discovered values
- Create issues for risky config drift
- Audit workflow files for trigger, permission, or command settings

## Workflow

### Step 1: Search parameter names
- **Tool**: `search_code` × 1-n times
- **Example**: `search_code({"query": "learning_rate"})`
- **Purpose**: Locate candidate config definitions and references.

### Step 2: Read primary config
- **Tool**: `get_file_contents` × 1-n times
- **Example**: `get_file_contents({"path": "config/default.yaml"})`
- **Purpose**: Verify exact value, type, comments, and context.

### Step 3: Search related references
- **Tool**: `search_code` × 1-n times
- **Example**: `search_code({"query": "learning_rate path:src"})`
- **Purpose**: Find code paths that consume the parameter.

### Step 4: Read related implementation
- **Tool**: `get_file_contents` × 1-n times
- **Example**: `get_file_contents({"path": "src/config.py"})`
- **Purpose**: Understand how the parameter is interpreted.

### Step 5: Create audit issue if needed
- **Tool**: `create_issue`
- **Example**: `create_issue({"title": "Config parameter audit", "body": "..."})`
- **Purpose**: Report drift or uncertainty with evidence.

### Step 6: Patch parameter if required
- **Tool**: `create_or_update_file` × 1-n times
- **Example**: `create_or_update_file({"path": "config/default.yaml", "content": "..."})`
- **Purpose**: Apply the requested configuration correction.

### Step 7: Open PR if needed
- **Tool**: `create_pull_request`
- **Example**: `create_pull_request({"title": "Audit config parameter", "head": "config/audit", "base": "main"})`
- **Purpose**: Route config changes through review when appropriate.

### Step 8: Verify final value
- **Tool**: `get_file_contents` × 1-n times
- **Example**: `get_file_contents({"path": "config/default.yaml"})`
- **Purpose**: Confirm final parameter value and format.

## Tools Involved

`search_code`, `get_file_contents`, `list_branches`, `get_branch`, `create_branch`, `create_or_update_file`, `create_pull_request`, `create_issue`

## Tips

- Search for both parameter name and common aliases.
- Read consumer code before changing a config value.
- Do not mix audit report and patch unless the task asks for both.
- Preserve YAML/JSON/TOML formatting exactly.
