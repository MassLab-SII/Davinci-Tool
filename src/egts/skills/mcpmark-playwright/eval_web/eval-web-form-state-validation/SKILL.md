# Eval Web Form State Validation

## Description

Interact with ordinary web forms, selectors, buttons, and inline result areas, then verify resulting DOM text or input state.

## Use Cases

- Interact with ordinary web forms, selectors, buttons, and inline result areas, then verify resulting DOM text or input state
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

### Step 4: Enter domain-specific input
- **Tool**: `browser_type` × 1-n times
- **Example**: `browser_type({"selector": "input[name=answer]", "text": "calculated value"})`
- **Purpose**: Fill search boxes, forms, login fields, checkout fields, or admin filters.

### Step 5: Submit keyboard-driven input
- **Tool**: `browser_press_key` × 1-n times
- **Example**: `browser_press_key({"key": "Enter"})`
- **Purpose**: Trigger search, form submission, or field confirmation when the UI expects a keypress.

### Step 6: Click target control
- **Tool**: `browser_click` × 1-n times
- **Example**: `browser_click({"selector": "text=Submit"})`
- **Purpose**: Activate buttons, links, menu items, filters, pagination, or row actions.

### Step 7: Wait for state change
- **Tool**: `browser_wait_for` × 1-n times
- **Example**: `browser_wait_for({"text": "Correct"})`
- **Purpose**: Allow navigation, Ajax grids, result panels, or validation messages to settle.

### Step 8: Verify final browser state
- **Tool**: `browser_get_text` × 1-n times
- **Example**: `browser_get_text({})`
- **Purpose**: Confirm the final page state, extracted evidence, or mutation result is visible.

## Tools Involved

- `browser_navigate`
- `browser_snapshot`
- `browser_click`
- `browser_type`
- `browser_press_key`
- `browser_wait_for`
- `browser_get_text`
- `browser_evaluate`

## Tips

- Use `browser_snapshot` before clicking so actions are grounded in visible elements.
- Prefer `browser_get_text` for final evidence and `browser_evaluate` for structured extraction.
- After typing or clicking, wait for the result area before judging success.
- Screenshots are useful when visual state matters, but text/DOM evidence should still be captured.
