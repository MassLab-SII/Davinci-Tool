# GitHub Documentation Audit And Maintenance

## Description

Audit repository documentation, tutorials, translations, and answer artifacts; locate the right files, update concise docs, and verify committed content.

## Use Cases

- Add missing usage or shortcut documentation
- Count translations or documentation variants
- Find tracking IDs, legacy names, or salient docs files
- Maintain answer files for repository information tasks
- Update docs while preserving existing style and structure

## Workflow

### Step 1: Search documentation surface
- **Tool**: `search_code` × 1-n times
- **Example**: `search_code({"query": "README OR docs"})`
- **Purpose**: Find README files, docs folders, tutorials, translation files, or answer locations.

### Step 2: Read top-level docs
- **Tool**: `get_file_contents` × 1-n times
- **Example**: `get_file_contents({"path": "README.md"})`
- **Purpose**: Understand current terminology and documentation style.

### Step 3: Inspect related files
- **Tool**: `get_file_contents` × 1-n times
- **Example**: `get_file_contents({"path": "docs/tutorial.md"})`
- **Purpose**: Gather enough evidence for accurate documentation updates.

### Step 4: Check branch context
- **Tool**: `list_branches` × 1-n times
- **Example**: `list_branches({})`
- **Purpose**: Confirm target branch for documentation maintenance.

### Step 5: Create branch if needed
- **Tool**: `create_branch`
- **Example**: `create_branch({"branch": "docs/audit-update", "from_branch": "main"})`
- **Purpose**: Prepare an isolated documentation update branch.

### Step 6: Write documentation artifact
- **Tool**: `create_or_update_file` × 1-n times
- **Example**: `create_or_update_file({"path": "docs/audit.md", "content": "..."})`
- **Purpose**: Create or update docs, indexes, answer files, or maintenance notes.

### Step 7: Open PR if needed
- **Tool**: `create_pull_request`
- **Example**: `create_pull_request({"title": "Update documentation audit", "head": "docs/audit-update", "base": "main"})`
- **Purpose**: Submit documentation changes when a PR workflow is expected.

### Step 8: Verify final docs
- **Tool**: `get_file_contents` × 1-n times
- **Example**: `get_file_contents({"path": "docs/audit.md"})`
- **Purpose**: Confirm content reflects actual repository evidence.

## Tools Involved

`search_code`, `get_file_contents`, `list_branches`, `get_branch`, `create_branch`, `create_or_update_file`, `create_pull_request`, `list_commits`

## Tips

- Documentation must reflect actual repository content.
- For counts or indexes, cite paths or file groups used in the calculation.
- Preserve existing heading style and terminology.
- Do not fabricate features that are not visible in files or commits.
