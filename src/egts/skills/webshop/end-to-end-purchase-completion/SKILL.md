# End-to-End Purchase Completion

## Description

Execute the full shopping workflow from instruction understanding through search, product identification, attribute verification, option selection, and final purchase — with a final verification step confirming the purchased product matches the original instruction. This is the complete purchase lifecycle skill for straightforward tasks with 1-3 clearly specified attributes.

## Use Cases

- Straightforward tasks like "Find a hardcover copy of The Great Gatsby for under $20" — search, verify, buy
- Tasks where the product is uniquely identifiable from search results without candidate comparison
- Tasks with minimal option selection (product has no configurable variants) requiring mainly product match verification
- Serving as the default workflow when the task doesn't require specialized comparison, budget optimization, or option configuration strategies

## Workflow

### Step 1: Read and parse the instruction
- **Tool**: `get_instruction`
- **Example**: `get_instruction()`
- **Purpose**: Retrieve the full task instruction. Note: (a) the product type/name, (b) required attributes, (c) any option requirements, and (d) the price constraint. For straightforward tasks, the instruction should clearly identify a specific product.

### Step 2: Formulate and execute search
- **Tool**: `search_product`
- **Example**: `search_product({"query": "Great Gatsby hardcover"})`
- **Purpose**: Search using the most distinctive product identifiers from the instruction. For named products (books, branded items), use the name directly. For generic products, include the product type and key attributes.

### Step 3: Observe search results and identify the target
- **Tool**: `get_page_observation`
- **Example**: `get_page_observation()`
- **Purpose**: Read the search results page. For straightforward tasks, the correct product should be clearly identifiable from the result titles and prices. If the exact product is visible, proceed directly to it.

### Step 4: Open the identified product
- **Tool**: `get_available_actions`, `click_element`
- **Examples**:
  - `get_available_actions()` — list clickable product titles
  - `click_element({"element_text": "The Great Gatsby (Hardcover)"})` — open the target product
- **Purpose**: Navigate to the product detail page. Confirm the product title and price match expectations.

### Step 5: Verify product attributes
- **Tool**: `get_page_observation`
- **Example**: `get_page_observation()`
- **Purpose**: Read the Item page. Check: (a) is this the correct product type? (b) does the price meet the budget constraint? (c) are any visible attributes consistent with the instruction? For simple tasks, the product title + price check may be sufficient.

### Step 6: Check for required options
- **Tool**: `get_available_actions`
- **Example**: `get_available_actions()`
- **Purpose**: Identify whether the product has configurable options (size, color, format). If options exist and the instruction specifies values, select them. If the instruction doesn't mention options and none are required, proceed to purchase.

### Step 7: Select options if required
- **Tool**: `click_element` × 1-n times
- **Example**: `click_element({"element_text": "Hardcover"})`
- **Purpose**: Select any option values specified in the instruction. Verify the selection was applied with `get_page_observation()`.

### Step 8: Check available actions for Buy
- **Tool**: `get_available_actions`
- **Example**: `get_available_actions()`
- **Purpose**: Confirm that all required selections are complete and the "Buy" action is available. If Buy is not visible, re-check for unselected options or navigation steps.

### Step 9: Execute the purchase
- **Tool**: `click_element`
- **Example**: `click_element({"element_text": "Buy"})`
- **Purpose**: Complete the purchase. In WebShop, clicking Buy ends the episode immediately.

### Step 10: Verify purchase result
- **Tool**: `get_page_observation`
- **Example**: `get_page_observation()`
- **Purpose**: After clicking Buy, observe the final page to confirm the purchase was processed — check for order confirmation message, purchased product name, and final price. This is the last evidence before the episode ends.

## Tools Involved

`get_instruction`, `search_product`, `get_page_observation`, `get_available_actions`, `click_element`

## Tips

- For straightforward tasks, don't over-engineer the workflow — if search returns the exact product with the right price, proceed to purchase without unnecessary candidate comparison
- Always verify the price on the detail page before buying — the search result price may differ
- If the instruction specifies multiple products, this workflow handles one product at a time; use multi-product-candidate-screening for comparison-heavy tasks
- The Buy action is immediate and final — double-check product match and price before clicking
- After purchase, the final page observation is critical evidence for the trajectory — it confirms what was bought and at what price
- This skill is the "happy path" baseline; when tasks require deeper attribute verification, option configuration, or budget optimization, combine with those specialized skills
