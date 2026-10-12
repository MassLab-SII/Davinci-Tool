# Reddit Search Sort Pagination Comment Mining

## Description

Use Postmill search, sort switches, pagination, post detail pages, and comment lists to locate specific evidence.

## Use Cases

- Use Postmill search, sort switches, pagination, post detail pages, and comment lists to locate specific evidence
- Navigate Postmill forums, posts, comments, and user/session flows.
- Extract listing metrics such as votes, comments, authors, and timestamps.
- Create posts, comments, forums, or wiki content when required.
- Use search, sorting, and pagination to locate forum evidence.
- Verify engagement or account state after mutations.

## Workflow

### Step 1: Capture page structure
- **Tool**: `browser_snapshot` × 1-n times
- **Example**: `browser_snapshot({})`
- **Purpose**: Ground the next action in the current visible accessibility tree.

### Step 2: Read visible page text
- **Tool**: `browser_get_text` × 1-n times
- **Example**: `browser_get_text({})`
- **Purpose**: Collect the current page text before filtering, extracting, or mutating state.

### Step 3: Enter domain-specific input
- **Tool**: `browser_type` × 1-n times
- **Example**: `browser_type({"selector": "input[name=username]", "text": "egts_user"})`
- **Purpose**: Fill search boxes, forms, login fields, checkout fields, or admin filters.

### Step 4: Submit keyboard-driven input
- **Tool**: `browser_press_key` × 1-n times
- **Example**: `browser_press_key({"key": "Enter"})`
- **Purpose**: Trigger search, form submission, or field confirmation when the UI expects a keypress.

### Step 5: Click target control
- **Tool**: `browser_click` × 1-n times
- **Example**: `browser_click({"selector": "text=Sign up"})`
- **Purpose**: Activate buttons, links, menu items, filters, pagination, or row actions.

### Step 6: Wait for state change
- **Tool**: `browser_wait_for` × 1-n times
- **Example**: `browser_wait_for({"text": "Submit"})`
- **Purpose**: Allow navigation, Ajax grids, result panels, or validation messages to settle.

### Step 7: Extract structured DOM evidence
- **Tool**: `browser_evaluate` × 1-n times
- **Example**: `browser_evaluate({"script": "Array.from(document.querySelectorAll('.submission')).map(x => x.innerText)"})`
- **Purpose**: Collect table rows, grid values, attributes, counters, or computed state precisely.

### Step 8: Verify final browser state
- **Tool**: `browser_get_text` × 1-n times
- **Example**: `browser_get_text({})`
- **Purpose**: Confirm the final page state, extracted evidence, or mutation result is visible.

## Tools Involved

- `browser_snapshot`
- `browser_get_text`
- `browser_click`
- `browser_type`
- `browser_press_key`
- `browser_wait_for`
- `browser_evaluate`

## Tips

- Confirm login/session state before posting, voting, or changing settings.
- Use sorting and pagination deliberately; forum listings can hide target posts.
- Verify mutations by returning to the visible post, comment, forum, or settings page.
- For counts, distinguish visible page counts from total community counts.
