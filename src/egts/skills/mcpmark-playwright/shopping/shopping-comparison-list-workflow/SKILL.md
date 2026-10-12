# Shopping Comparison List Workflow

## Description

Add selected storefront products to the comparison list, open comparison, count items, and extract comparable SKU/price attributes.

## Use Cases

- Add selected storefront products to the comparison list, open comparison, count items, and extract comparable SKU/price attributes
- Search and compare storefront products across categories and filters.
- Extract product detail attributes such as SKU, price, rating, reviews, and options.
- Operate comparison lists, carts, quantities, and checkout forms.
- Optimize selections under budget, rating, manufacturer, or bundle constraints.
- Verify storefront state through visible text and structured DOM reads.

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
- **Example**: `browser_click({"selector": "text=Add to Cart"})`
- **Purpose**: Activate buttons, links, menu items, filters, pagination, or row actions.

### Step 4: Wait for state change
- **Tool**: `browser_wait_for` × 1-n times
- **Example**: `browser_wait_for({"text": "Shopping Cart"})`
- **Purpose**: Allow navigation, Ajax grids, result panels, or validation messages to settle.

### Step 5: Extract structured DOM evidence
- **Tool**: `browser_evaluate` × 1-n times
- **Example**: `browser_evaluate({"script": "Array.from(document.querySelectorAll('.product-item')).map(x => x.innerText)"})`
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

- Product names can be similar; verify SKU or detail-page attributes before selecting.
- After cart mutations, re-read cart totals rather than assuming quantity updates succeeded.
- Use filters and sorting together for budget or ranking tasks.
- For checkout forms, verify validation or available shipping methods after submission.
