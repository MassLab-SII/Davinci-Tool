# GitHub Actions Automation Authoring

## Description

Author GitHub Actions workflows for linting, PR automation, deployment status, issue automation, nightly health checks, and CI guardrails.

## Use Cases

- Create workflows for linting and tests
- Add PR automation or issue management workflows
- Add deployment status or nightly health workflows
- Create automation on a branch and open a PR
- Verify workflow YAML and trigger coverage

## Workflow

### Step 1: Find existing workflows
- **Tool**: `search_code` × 1-n times
- **Example**: `search_code({"query": "on:"})`
- **Purpose**: Discover current GitHub Actions patterns and workflow locations.

### Step 2: Read supporting scripts
- **Tool**: `get_file_contents` × 1-n times
- **Example**: `get_file_contents({"path": "package.json"})`
- **Purpose**: Determine valid commands for tests, linting, or deployment checks.

### Step 3: Check related issues
- **Tool**: `list_issues` × 1-n times
- **Example**: `list_issues({"state": "open"})`
- **Purpose**: Use issue requirements as workflow design constraints.

### Step 4: Create branch if needed
- **Tool**: `create_branch`
- **Example**: `create_branch({"branch": "ci/add-pr-automation", "from_branch": "main"})`
- **Purpose**: Prepare a dedicated branch for automation work.

### Step 5: Write workflow file
- **Tool**: `create_or_update_file` × 1-n times
- **Example**: `create_or_update_file({"path": ".github/workflows/pr-automation.yml", "content": "name: PR Automation
..."})`
- **Purpose**: Create the requested GitHub Actions workflow.

### Step 6: Open PR if needed
- **Tool**: `create_pull_request`
- **Example**: `create_pull_request({"title": "Add PR automation workflow", "head": "ci/add-pr-automation", "base": "main"})`
- **Purpose**: Submit the automation change for review.

### Step 7: Verify workflow content
- **Tool**: `get_file_contents` × 1-n times
- **Example**: `get_file_contents({"path": ".github/workflows/pr-automation.yml"})`
- **Purpose**: Confirm triggers, permissions, and jobs match the task.

## Tools Involved

`get_file_contents`, `search_code`, `list_issues`, `create_issue`, `create_or_update_file`, `list_commits`, `create_branch`, `create_pull_request`

## Tips

- Inspect real project commands before writing workflow jobs.
- Include only permissions needed by the task.
- Use `.github/workflows/*.yml` or `.yaml` consistently with existing repository style.
- For automation tasks, verify both the file path and YAML body.
