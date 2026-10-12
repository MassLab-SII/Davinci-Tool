# Project Scaffolding

## Description

Build a complete, well-structured project from scratch. Create multi-level directories, write configuration files, generate source code templates with cross-file references, and produce documentation — all forming a coherent, production-ready project skeleton.

## Use Cases

- Initialize a new Python/Node.js/Go project with standard layout
- Set up a data processing pipeline directory structure
- Create a microservice project skeleton
- Establish a normalized structure for existing loose code

## Workflow

### Step 1: Discover allowed directories
- **Tool**: `list_allowed_directories`
- **Example**: `list_allowed_directories({})`
- **Purpose**: Discover which directories you are permitted to access. The returned paths are the only valid roots for all subsequent operations.

### Step 2: Inspect the workspace root
- **Tool**: `list_directory`
- **Example**: `list_directory({"path": "/workspace"})`
- **Purpose**: List the top-level contents of the workspace to understand what already exists and avoid naming conflicts. Replace `/workspace` with the actual allowed path from Step 1.

### Step 3: Create core directory hierarchy
- **Tool**: `create_directory` × 1-n times
- **Examples**:
  - `create_directory({"path": "/workspace/myproject/src"})`
  - `create_directory({"path": "/workspace/myproject/tests"})`
  - `create_directory({"path": "/workspace/myproject/config"})`
  - `create_directory({"path": "/workspace/myproject/docs"})`
- **Purpose**: Build the project's directory skeleton. `create_directory` supports recursive creation (e.g., `src/core/models` in one call).

### Step 4: Write project configuration files
- **Tool**: `write_file` × 1-n times
- **Examples**:
  - `write_file({"path": "/workspace/myproject/pyproject.toml", "content": "[project]\nname = \"myproject\"\nversion = \"0.1.0\"\n..."})`
  - `write_file({"path": "/workspace/myproject/.gitignore", "content": "__pycache__/\n*.pyc\n.env\n..."})`
  - `write_file({"path": "/workspace/myproject/config/default.yaml", "content": "database:\n  host: localhost\n..."})`
- **Purpose**: Create project-level configs with meaningful, realistic content — not just placeholder comments.

### Step 5: Write core source code
- **Tool**: `write_file` × 1-n times
- **Examples**:
  - `write_file({"path": "/workspace/myproject/src/main.py", "content": "from src.utils import setup_logging\n\ndef main():\n    ..."})`
  - `write_file({"path": "/workspace/myproject/src/utils.py", "content": "import logging\n\ndef setup_logging():\n    ..."})`
- **Purpose**: Create source files with real logic and cross-file imports. Files should reference each other.

### Step 6: Write test files
- **Tool**: `write_file` × 1-n times
- **Examples**:
  - `write_file({"path": "/workspace/myproject/tests/test_main.py", "content": "from src.main import main\n\ndef test_main():\n    ..."})`
- **Purpose**: Create test files that import and reference the source code from Step 5.

### Step 7: Write project documentation
- **Tool**: `write_file`
- **Example**: `write_file({"path": "/workspace/myproject/README.md", "content": "# MyProject\n\n## Overview\n..."})`
- **Purpose**: Create a README.md covering project description, directory layout, install guide, and usage.

### Step 8: Verify the final structure
- **Tool**: `directory_tree`
- **Example**: `directory_tree({"path": "/workspace/myproject"})`
- **Purpose**: Confirm the project tree is complete and well-organized. The `path` parameter must be a string pointing to an allowed directory.

## Tools Involved

`list_allowed_directories`, `list_directory`, `create_directory`, `write_file`, `directory_tree`

## Tips

- Source files should have real import relationships between them — avoid isolated files with no cross-references
- Configuration files should contain realistic values, not just placeholder comments
- Always verify the final structure with `directory_tree` as the last step
- All path parameters must be **strings** — never pass objects or arrays for `path`
