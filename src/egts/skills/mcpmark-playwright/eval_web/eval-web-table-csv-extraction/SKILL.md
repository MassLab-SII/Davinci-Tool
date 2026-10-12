# Eval Web Table CSV Extraction

## Description

Extract complete table/card data from eval-web pages and format it as exact CSV evidence.

## Use Cases

- Extract complete table/card data from eval-web pages and format it as exact CSV evidence
- Extract exact facts from controlled evaluation pages.
- Interact with forms, buttons, tables, and stateful widgets.
- Verify page success conditions through DOM text and snapshots.
- Collect visual or diagnostic evidence when page state is ambiguous.
- Produce grounded browser observations instead of guessing from page names.

## Workflow

### Step 1: Navigate to the task page
- **Tool**: `browser_navigate`
- **Example**: `browser_navigate({"url": "http://host.docker.internal:8000/task"})`
- **Purpose**: Open the page or search entry point required by the task.

### Step 2: Capture page structure
- **Tool**: `browser_snapshot` × 1-n times
- **Example**: `browser_snapshot({})`
- **Purpose**: Ground the next action in the current visible accessibility tree.

### Step 3: Read visible page text
- **Tool**: `browser_get_text` × 1-n times
- **Example**: `browser_get_text({})`
- **Purpose**: Collect the current page text before filtering, extracting, or mutating state.

### Step 4: Wait for state change
- **Tool**: `browser_wait_for` × 1-n times
- **Example**: `browser_wait_for({"text": "Correct"})`
- **Purpose**: Allow navigation, Ajax grids, result panels, or validation messages to settle.

### Step 5: Extract structured DOM evidence
- **Tool**: `browser_evaluate` × 1-n times
- **Example**: `browser_evaluate({"script": "Array.from(document.querySelectorAll('table tr')).map(r => r.innerText)"})`
- **Purpose**: Collect table rows, grid values, attributes, counters, or computed state precisely.

### Step 6: Verify final browser state
- **Tool**: `browser_get_text` × 1-n times
- **Example**: `browser_get_text({})`
- **Purpose**: Confirm the final page state, extracted evidence, or mutation result is visible.

## Tools Involved

- `browser_navigate`
- `browser_snapshot`
- `browser_get_text`
- `browser_evaluate`
- `browser_wait_for`

## Tips

- Use `browser_snapshot` before clicking so actions are grounded in visible elements.
- Prefer `browser_get_text` for final evidence and `browser_evaluate` for structured extraction.
- After typing or clicking, wait for the result area before judging success.
- Screenshots are useful when visual state matters, but text/DOM evidence should still be captured.
