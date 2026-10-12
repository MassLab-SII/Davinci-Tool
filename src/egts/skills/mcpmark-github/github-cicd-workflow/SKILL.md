# GitHub CI/CD Workflow

## Description

Design or update GitHub Actions and CI/CD workflows by inspecting existing automation, package scripts, issue requirements, and committed workflow files.

## Use Cases

- Create basic CI checks for a repository
- Add issue linting or PR guard workflows
- Inspect existing package/test scripts before authoring YAML
- Create tracking issues for automation gaps
- Verify workflow files and supporting scripts after mutation

## Workflow

### Step 1: Find automation files
- **Tool**: `search_code` × 1-n times
- **Example**: `search_code({"query": ".github/workflows"})`
- **Purpose**: Locate existing workflow files and automation conventions.

### Step 2: Read workflow or package files
- **Tool**: `get_file_contents` × 1-n times
- **Example**: `get_file_contents({"path": ".github/workflows/ci.yml"})`
- **Purpose**: Understand triggers, jobs, commands, and syntax style.

### Step 3: Read task context
- **Tool**: `list_issues` × 1-n times
- **Example**: `list_issues({"state": "open"})`
- **Purpose**: Find CI-related requests or operational requirements when present.

### Step 4: Create tracking issue if needed
- **Tool**: `create_issue`
- **Example**: `create_issue({"title": "Add CI guardrails", "body": "..."})`
- **Purpose**: Document automation work when the benchmark task expects issue creation.

### Step 5: Write workflow YAML
- **Tool**: `create_or_update_file` × 1-n times
- **Example**: `create_or_update_file({"path": ".github/workflows/ci.yml", "content": "name: CI
..."})`
- **Purpose**: Add or update the workflow file with grounded commands.

### Step 6: Inspect commit history
- **Tool**: `list_commits` × 1-n times
- **Example**: `list_commits({"sha": "main"})`
- **Purpose**: Verify the workflow change is recorded.

### Step 7: Re-read workflow
- **Tool**: `get_file_contents` × 1-n times
- **Example**: `get_file_contents({"path": ".github/workflows/ci.yml"})`
- **Purpose**: Confirm trigger, job, and command content are correct.

## Tools Involved

`get_file_contents`, `search_code`, `list_issues`, `create_issue`, `create_or_update_file`, `list_commits`

## Tips

- Inspect package/config files before guessing test commands.
- Keep workflow YAML minimal and task-specific.
- Use existing naming and branch conventions when updating workflows.
- Check final YAML content because small indentation errors make workflows unusable.
