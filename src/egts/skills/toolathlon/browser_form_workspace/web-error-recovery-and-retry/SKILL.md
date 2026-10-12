# Web Error Recovery And Retry

## Description

Complete browser workflows when pages are stale, forms are partially filled, or expected elements are missing by re-grounding in local requirements and retrying through observable page state. Use this as an operational sub-workflow for Toolathlon browser form tasks.

## Use Cases

- A form field, button, or result card is missing from the current page view
- A page reload or navigation step loses previously entered values
- A shopping, school-search, or application page returns no results under the first filter choice
- The browser state must be recovered without abandoning the task requirements stored in local files or memory

## Workflow

### Step 1: Re-read the non-negotiable task constraints
- **Tool**: `filesystem-read_file` × 1-n times
- **Example**: `filesystem-read_file({"path": "/workspace/requirements.txt"})`
- **Purpose**: Separate hard constraints from preferences before retrying. For example, budget caps, required location, degree level, or exact form identity should not be weakened during recovery.

### Step 2: Inspect the current page state
- **Tool**: `playwright_with_chunk-browser_snapshot`
- **Example**: `playwright_with_chunk-browser_snapshot({})`
- **Purpose**: Determine whether the problem is missing navigation, stale page state, validation errors, no results, or already-submitted state.

### Step 3: Wait only for a specific observable condition
- **Tool**: `playwright_with_chunk-browser_wait_for`
- **Example**: `playwright_with_chunk-browser_wait_for({"text": "Submit"})`
- **Purpose**: Wait for a concrete page element or text that proves the page is ready. Do not use arbitrary waiting when the expected condition can be named.

### Step 4: Retry the smallest browser action
- **Tool**: `playwright_with_chunk-browser_snapshot` × 1-n times
- **Example**: `playwright_with_chunk-browser_snapshot({})`
- **Purpose**: After a reload, back navigation, filter change, or field correction, inspect again before continuing. Retry one variable at a time so the recovered state remains explainable.

### Step 5: Record the recovery decision
- **Tool**: `filesystem-write_file`
- **Example**: `filesystem-write_file({"path": "/workspace/browser_recovery_note.md", "content": "Issue: initial filter returned no products. Recovery: preserved black/leather/budget constraints and broadened brand filter only. Evidence: snapshot showed three qualifying products."})`
- **Purpose**: Save why a retry path was valid, especially when a task has multiple acceptable routes or fallback candidates.

### Step 6: Verify the recovered state before final output
- **Tool**: `playwright_with_chunk-browser_snapshot`, then `filesystem-read_file`
- **Examples**:
  - `playwright_with_chunk-browser_snapshot({})`
  - `filesystem-read_file({"path": "/workspace/browser_recovery_note.md"})`
- **Purpose**: Confirm the page now satisfies the task constraints and the recovery note is durable.

## Tools Involved

`filesystem-list_allowed_directories`, `filesystem-list_directory`, `filesystem-read_file`, `filesystem-write_file`, `playwright_with_chunk-browser_snapshot`, `playwright_with_chunk-browser_wait_for`

## Tips

- Keep this as a recovery workflow, not a replacement for the main form-filling or web-research skill
- Never relax a hard requirement silently; record which preference was broadened and why
- Use condition-based waits tied to visible text or controls
- Re-check state after each retry so the trajectory shows causality rather than random browsing
