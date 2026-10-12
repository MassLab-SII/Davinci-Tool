# Reddit Forum Listing Metrics Extraction

## Description

Extract ranked post metrics from forum listings: titles, votes, comments, authors, dates, page counts, and visible post totals.

## Use Cases

- Extract ranked post metrics from forum listings: titles, votes, comments, authors, dates, page counts, and visible post totals
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

### Step 3: Click target control
- **Tool**: `browser_click` × 1-n times
- **Example**: `browser_click({"selector": "text=Sign up"})`
- **Purpose**: Activate buttons, links, menu items, filters, pagination, or row actions.

### Step 4: Wait for state change
- **Tool**: `browser_wait_for` × 1-n times
- **Example**: `browser_wait_for({"text": "Submit"})`
- **Purpose**: Allow navigation, Ajax grids, result panels, or validation messages to settle.

### Step 5: Extract structured DOM evidence
- **Tool**: `browser_evaluate` × 1-n times
- **Example**: `browser_evaluate({"script": "Array.from(document.querySelectorAll('.submission')).map(x => x.innerText)"})`
- **Purpose**: Collect table rows, grid values, attributes, counters, or computed state precisely.

### Step 6: Verify final browser state
- **Tool**: `browser_get_text` × 1-n times
- **Example**: `browser_get_text({})`
- **Purpose**: Confirm the final page state, extracted evidence, or mutation result is visible.

## Tools Involved

- `browser_snapshot`
- `browser_get_text`
- `browser_click`
- `browser_wait_for`
- `browser_evaluate`

## Tips

- Confirm login/session state before posting, voting, or changing settings.
- Use sorting and pagination deliberately; forum listings can hide target posts.
- Verify mutations by returning to the visible post, comment, forum, or settings page.
- For counts, distinguish visible page counts from total community counts.
