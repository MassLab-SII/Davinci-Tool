# Documentation Generation

## Description

Systematically read any collection of files and directory structure, then generate comprehensive documentation that accurately reflects the actual content. Works with code projects, data collections, configuration systems, content repositories, or any structured file collection — producing overviews, indexes, catalogs, guides, and reference documentation.

## Use Cases

- Generate README and API docs for code projects
- Create content catalogs and indexes for data collections (papers, documents, media files)
- Build configuration guides documenting multi-environment setups
- Produce directory structure indexes with file/component descriptions
- Generate user guides from existing content and file organization
- Create inventory reports for file repositories

## Workflow

### Step 1: Discover allowed directories
- **Tool**: `list_allowed_directories`
- **Example**: `list_allowed_directories({})`
- **Purpose**: Discover which directories you are permitted to access. Use the returned paths as roots for all subsequent operations.

### Step 2: Inspect the workspace root
- **Tool**: `list_directory`
- **Example**: `list_directory({"path": "/workspace"})`
- **Purpose**: List the top-level contents to understand the project layout. Replace `/workspace` with the actual allowed path from Step 1.

### Step 3: Survey project structure
- **Tool**: `directory_tree`
- **Example**: `directory_tree({"path": "/workspace/project"})`
- **Purpose**: Get the full file tree as raw material for the directory layout section. The `path` parameter must be a **string**.

### Step 4: Identify key files
- **Tool**: `search_files` × 1-n times
- **Examples**:
  - `search_files({"path": "/workspace/project", "pattern": "*.py"})`
  - `search_files({"path": "/workspace/project", "pattern": "*.html"})`
  - `search_files({"path": "/workspace/project", "pattern": "*.json"})`
- **Purpose**: Locate all files to determine documentation scope — code files, data files, configs, or any other content. Both `path` and `pattern` must be **strings**.

### Step 5: Check for existing documentation
- **Tool**: `search_files`
- **Example**: `search_files({"path": "/workspace/project", "pattern": "*.md"})`
- **Purpose**: Find any existing docs that can be referenced or need updating.

### Step 6: Batch-read key files
- **Tool**: `read_multiple_files`
- **Examples**:
  - `read_multiple_files({"paths": ["/workspace/project/src/main.py", "/workspace/project/src/utils.py", "/workspace/project/config.json"]})`
  - `read_multiple_files({"paths": ["/workspace/data/papers/paper_001.html", "/workspace/data/papers/paper_002.html", "/workspace/data/papers/paper_003.html"]})`
- **Purpose**: Read core files to extract structure, content patterns, and component responsibilities. The `paths` parameter must be an **array of strings**.

### Step 7: Deep-read entry points and configs
- **Tool**: `read_text_file` × 1-n times
- **Examples**:
  - `read_text_file({"path": "/workspace/project/src/index.py"})`
  - `read_text_file({"path": "/workspace/project/config.yaml"})`
  - `read_text_file({"path": "/workspace/data/metadata.json"})`
- **Purpose**: Carefully read entry files, configs, or metadata to understand organization and key attributes. The `path` parameter must be a **string**.

### Step 8: Generate main documentation
- **Tool**: `write_file`
- **Examples**:
  - For code projects: `write_file({"path": "/workspace/project/README.md", "content": "# Project Name\n\n## Overview\n...\n\n## Directory Structure\n...\n\n## Installation\n...\n\n## Usage\n..."})`
  - For data collections: `write_file({"path": "/workspace/data/CATALOG.md", "content": "# Data Catalog\n\n## Overview\nThis collection contains 83 papers...\n\n## Contents\n| File | Title | Year |\n|------|-------|------|\n..."})`
  - For config systems: `write_file({"path": "/workspace/project/CONFIG_GUIDE.md", "content": "# Configuration Guide\n\n## Environments\n- development: ...\n- production: ...\n\n## Parameters\n..."})`
- **Purpose**: Write the primary documentation file, tailored to the content type — README for code, catalogs for data, guides for configs.

### Step 9: Generate supplementary documentation
- **Tool**: `write_file` × 1-n times
- **Examples**:
  - `write_file({"path": "/workspace/project/docs/API.md", "content": "# API Reference\n\n## Functions\n..."})`
  - `write_file({"path": "/workspace/data/2023/INDEX.md", "content": "# 2023 Papers\n\n| ID | Authors | Path |\n|----|---------|------|\n..."})`
- **Purpose**: Produce supplementary docs — per-directory indexes, component references, or topic-specific guides.

### Step 10: Verify documentation files
- **Tool**: `directory_tree`
- **Example**: `directory_tree({"path": "/workspace/project"})`
- **Purpose**: Confirm all doc files are properly created in the project.

## Tools Involved

`list_allowed_directories`, `list_directory`, `directory_tree`, `search_files`, `read_multiple_files`, `read_text_file`, `write_file`

## Tips

- Documentation must reflect actual content — never fabricate names, details, or features not found in files
- Reference the `directory_tree` output directly when writing the project structure section
- If existing docs are found, read them first to maintain consistency in style and terminology
- Adapt documentation style to content type:
  - Code projects: focus on architecture, APIs, usage examples
  - Data collections: emphasize catalogs, metadata, organization schemes
  - Config systems: document parameters, environments, and switching procedures
  - Content repositories: create indexes, summaries, and navigation guides
- For large collections (50+ files), organize documentation hierarchically with per-directory indexes
- All path parameters must be **strings**, and `paths` must be an **array of strings** — never pass wrong types
