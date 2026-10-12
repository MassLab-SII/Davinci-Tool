# Config Management

## Description

Manage a project's multi-environment configuration system. Analyze existing configs, derive environment-specific variants (dev/staging/prod), synchronize shared fields across environments, and ensure consistency. Produce a configuration guide documenting the differences.

## Use Cases

- Derive multi-environment configs (dev/staging/prod) from a single base config
- Audit multiple config files for consistency and detect missing or conflicting fields
- Update shared config fields and propagate changes to all environments
- Create config templates and environment variable example files

## Workflow

### Step 1: Discover allowed directories
- **Tool**: `list_allowed_directories`
- **Example**: `list_allowed_directories({})`
- **Purpose**: Discover which directories you are permitted to access. Use the returned paths as roots for all subsequent operations.

### Step 2: Inspect the workspace root
- **Tool**: `list_directory`
- **Example**: `list_directory({"path": "/workspace"})`
- **Purpose**: List the top-level contents to understand the project layout. Replace `/workspace` with the actual allowed path from Step 1.

### Step 3: Search for all config files
- **Tool**: `search_files` × 1-n times
- **Examples**:
  - `search_files({"path": "/workspace/project", "pattern": "*.yaml"})`
  - `search_files({"path": "/workspace/project", "pattern": "*.json"})`
- **Purpose**: Locate every configuration file in the workspace. Both `path` and `pattern` must be **strings**.

### Step 4: Batch-read existing configs
- **Tool**: `read_multiple_files`
- **Example**: `read_multiple_files({"paths": ["/workspace/project/config.yaml", "/workspace/project/settings.json"]})`
- **Purpose**: Read all configs simultaneously to analyze structure and spot differences. The `paths` parameter must be an **array of strings**.

### Step 5: Deep-read the base config
- **Tool**: `read_text_file`
- **Example**: `read_text_file({"path": "/workspace/project/config.yaml"})`
- **Purpose**: Thoroughly understand every field in the base configuration. The `path` parameter must be a **string**.

### Step 6: Create config directory structure
- **Tool**: `create_directory`
- **Example**: `create_directory({"path": "/workspace/project/config/environments"})`
- **Purpose**: Set up the multi-environment config directory layout. The `path` parameter must be a **string**.

### Step 7: Generate environment-specific configs
- **Tool**: `write_file` × 1-n times
- **Examples**:
  - `write_file({"path": "/workspace/project/config/environments/development.yaml", "content": "database:\n  host: localhost\n  debug: true\n..."})`
  - `write_file({"path": "/workspace/project/config/environments/staging.yaml", "content": "database:\n  host: staging.example.com\n  debug: false\n..."})`
  - `write_file({"path": "/workspace/project/config/environments/production.yaml", "content": "database:\n  host: prod.example.com\n  debug: false\n..."})`
  - `write_file({"path": "/workspace/project/config/.env.example", "content": "DB_HOST=localhost\nDB_PASSWORD=${DB_PASSWORD}\n..."})`
- **Purpose**: Derive environment variants from the base config. Both `path` and `content` must be **strings**.

### Step 8: Update shared fields in existing configs
- **Tool**: `read_text_file` → `edit_file` × 1-n times
- **Examples**:
  - `read_text_file({"path": "/workspace/project/config.yaml"})`
  - `edit_file({"path": "/workspace/project/config.yaml", "edits": [{"oldText": "version: 1.0", "newText": "version: 2.0"}]})`
- **Purpose**: Synchronize common config fields across existing files to maintain consistency. Read each file first to confirm current content, then use `edit_file` to update. The `edits` parameter must be an **array of objects**, each with `oldText` and `newText` string fields.

### Step 9: Write config documentation
- **Tool**: `write_file`
- **Example**: `write_file({"path": "/workspace/project/config/README.md", "content": "# Configuration Guide\n\n## Environments\n- development: Local dev with debug enabled\n- staging: Production-like testing\n- production: Optimized and hardened\n\n## Switching Environments\n...\n"})`
- **Purpose**: Document the config system: environment differences, how to switch, and field reference.

### Step 10: Verify config completeness
- **Tool**: `directory_tree`
- **Example**: `directory_tree({"path": "/workspace/project/config"})`
- **Purpose**: Confirm all config files are properly created. The `path` parameter must be a **string**.

## Tools Involved

`list_allowed_directories`, `list_directory`, `search_files`, `read_multiple_files`, `read_text_file`, `create_directory`, `write_file`, `edit_file`, `directory_tree`

## Tips

- Environment configs should share the same schema/structure — only values should differ
- Sensitive values (passwords, API keys) should use placeholder tokens like `${DB_PASSWORD}` rather than real values
- The `.env.example` file should list every required environment variable with descriptive comments
- When editing existing configs, always read first to avoid overwriting fields added by other processes
- All path parameters must be **strings**, `paths` must be an **array of strings**, and `edits` must be an **array of objects** — never pass wrong types
