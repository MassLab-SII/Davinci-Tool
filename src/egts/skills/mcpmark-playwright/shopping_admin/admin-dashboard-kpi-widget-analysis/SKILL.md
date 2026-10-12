# Admin Dashboard KPI Widget Analysis

## Description

Extract dashboard KPIs and widget rows such as Lifetime Sales, Revenue, Bestsellers, Last Orders, Top Search Terms, and Last Search Terms.

## Use Cases

- Extract dashboard KPIs and widget rows such as Lifetime Sales, Revenue, Bestsellers, Last Orders, Top Search Terms, and Last Search Terms
- Navigate Magento Admin dashboards, grids, reports, and configuration pages.
- Extract KPI, order, catalog, customer, marketing, store, and tax records.
- Search and filter admin grids before reading row-level evidence.
- Create or inspect admin records when the task requires mutation.
- Verify admin state through records-found counts, visible values, and screenshots.

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
- **Example**: `browser_click({"selector": "text=Filters"})`
- **Purpose**: Activate buttons, links, menu items, filters, pagination, or row actions.

### Step 4: Wait for state change
- **Tool**: `browser_wait_for` × 1-n times
- **Example**: `browser_wait_for({"text": "records found"})`
- **Purpose**: Allow navigation, Ajax grids, result panels, or validation messages to settle.

### Step 5: Extract structured DOM evidence
- **Tool**: `browser_evaluate` × 1-n times
- **Example**: `browser_evaluate({"script": "Array.from(document.querySelectorAll('.data-row')).map(r => r.innerText)"})`
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

- Admin pages often require navigation through menus; confirm the current section after each jump.
- Grid filters may persist; clear or verify filter state before extracting counts.
- Use row values, records-found counts, and page headings as verification anchors.
- For configuration pages, read current values before changing or reporting them.
