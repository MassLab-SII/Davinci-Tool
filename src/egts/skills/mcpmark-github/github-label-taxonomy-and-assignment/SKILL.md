# GitHub Label Taxonomy And Assignment

## Description

Create, update, standardize, and assign labels based on issue, PR, comment, contributor, or repository-taxonomy evidence.

## Use Cases

- Standardize label names and colors
- Assign contributor or topic labels to issues
- Tag issues and PRs during triage workflows
- Create missing labels required by automation or taxonomy tasks
- Verify final labels after issue or label mutation

## Workflow

### Step 1: Read current labels
- **Tool**: `list_labels` × 1-n times
- **Example**: `list_labels({})`
- **Purpose**: Understand existing taxonomy, colors, and naming conventions.

### Step 2: Inspect candidate issues
- **Tool**: `list_issues` × 1-n times
- **Example**: `list_issues({"state": "open"})`
- **Purpose**: Find items that may need labels.

### Step 3: Read issue evidence
- **Tool**: `get_issue` × 1-n times
- **Example**: `get_issue({"issue_number": 12})`
- **Purpose**: Verify body, current labels, and metadata.

### Step 4: Read comments
- **Tool**: `list_issue_comments` × 1-n times
- **Example**: `list_issue_comments({"issue_number": 12})`
- **Purpose**: Use discussion evidence for contributor or topic labels.

### Step 5: Create or update label
- **Tool**: `create_label`
- **Example**: `create_label({"name": "needs-triage", "color": "ededed"})`
- **Purpose**: Add missing taxonomy entries when required.

### Step 6: Assign label
- **Tool**: `update_issue` × 1-n times
- **Example**: `update_issue({"issue_number": 12, "labels": ["needs-triage"]})`
- **Purpose**: Apply the selected label set to the issue.

### Step 7: Verify taxonomy and issue
- **Tool**: `get_issue` × 1-n times
- **Example**: `get_issue({"issue_number": 12})`
- **Purpose**: Confirm labels are correctly assigned.

## Tools Involved

`list_issues`, `get_issue`, `list_issue_comments`, `list_labels`, `create_label`, `update_label`, `update_issue`, `list_commits`, `create_issue`

## Tips

- Preserve existing label taxonomy when possible.
- When standardizing colors, check all affected labels before mutating.
- Do not assign contributor labels without commit/comment/PR evidence.
- After label mutation, verify both label definition and issue assignment.
