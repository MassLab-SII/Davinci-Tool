# GitHub Deployment Health Monitoring

## Description

Inspect deployment, nightly health, CI status, and operational workflow signals; create or update automation and tracking artifacts for repository health monitoring.

## Use Cases

- Add nightly health check workflows
- Create deployment status workflows or reports
- Track operational failures with issues or comments
- Add health-check documentation or workflow files
- Verify operational automation is committed correctly

## Workflow

### Step 1: Find operational workflows
- **Tool**: `search_code` × 1-n times
- **Example**: `search_code({"query": "deployment_status OR nightly"})`
- **Purpose**: Locate existing deployment or health-check automation.

### Step 2: Read workflow/config files
- **Tool**: `get_file_contents` × 1-n times
- **Example**: `get_file_contents({"path": ".github/workflows/deploy.yml"})`
- **Purpose**: Understand current triggers, jobs, and status checks.

### Step 3: Inspect related issues
- **Tool**: `list_issues` × 1-n times
- **Example**: `list_issues({"state": "open"})`
- **Purpose**: Find requests for deployment or nightly health monitoring.

### Step 4: Read target issue
- **Tool**: `get_issue` × 1-n times
- **Example**: `get_issue({"issue_number": 6})`
- **Purpose**: Extract exact health-monitoring requirements.

### Step 5: Create or update workflow
- **Tool**: `create_or_update_file` × 1-n times
- **Example**: `create_or_update_file({"path": ".github/workflows/nightly-health.yml", "content": "..."})`
- **Purpose**: Add the operational automation artifact.

### Step 6: Create tracking issue
- **Tool**: `create_issue`
- **Example**: `create_issue({"title": "Track nightly health", "body": "..."})`
- **Purpose**: Record operational monitoring scope when needed.

### Step 7: Add status comment
- **Tool**: `add_issue_comment` × 1-n times
- **Example**: `add_issue_comment({"issue_number": 6, "body": "Added nightly health workflow."})`
- **Purpose**: Document action taken on the relevant issue.

### Step 8: Verify committed workflow
- **Tool**: `get_file_contents` × 1-n times
- **Example**: `get_file_contents({"path": ".github/workflows/nightly-health.yml"})`
- **Purpose**: Confirm final workflow content is present.

## Tools Involved

`get_file_contents`, `search_code`, `list_issues`, `get_issue`, `create_issue`, `add_issue_comment`, `create_or_update_file`, `list_commits`

## Tips

- Distinguish CI validation from deployment health; use the task wording to choose scope.
- Inspect existing workflow naming before adding another file.
- For scheduled checks, verify cron and branch assumptions.
- After comments or issue creation, verify the tracking artifact exists.
