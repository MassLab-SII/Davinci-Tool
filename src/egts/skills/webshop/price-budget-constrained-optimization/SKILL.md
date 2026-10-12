# Price Budget Constrained Optimization

## Description

When a shopping instruction specifies a strict budget ("under $50", "around $30", "cheapest"), prioritize price constraints alongside attribute matching. Identify all products satisfying non-price requirements, compare their prices, and select the option that delivers the best value — either the cheapest match or the one with the best price-to-features ratio, depending on the instruction's intent.

## Use Cases

- Find the cheapest "64GB USB flash drive with USB 3.0" under a stated budget
- Filter out products that meet all attribute requirements but exceed the price limit
- When multiple products satisfy all non-price requirements, select the lowest-priced option
- Instruction says "best value" — evaluate the price-to-features trade-off rather than just picking the cheapest
- Instruction has an implied price constraint ("affordable", "budget-friendly") — interpret the price sensitivity

## Workflow

### Step 1: Identify the price constraint from the instruction
- **Tool**: `get_instruction`
- **Example**: `get_instruction()`
- **Purpose**: Read the instruction and extract the exact price constraint. Note whether it's a hard limit ("under $40"), a soft target ("around $30"), or a relative preference ("cheapest", "best value", "affordable").

### Step 2: Search for products by type and required attributes
- **Tool**: `search_product`
- **Example**: `search_product({"query": "USB flash drive 64GB USB 3.0"})`
- **Purpose**: Search for products matching the non-price requirements. Do NOT include the price in the search query — price filtering should be done manually by examining results, as the search engine uses text matching, not numeric range filtering.

### Step 3: Scan prices in search results
- **Tool**: `get_page_observation`
- **Example**: `get_page_observation()`
- **Purpose**: Read the search results page and note the displayed prices for each product. Identify which products are under, near, or over the budget.

### Step 4: Open the cheapest candidate first
- **Tool**: `click_element`
- **Example**: `click_element({"element_text": "Budget USB Flash Drive 64GB"})`
- **Purpose**: Navigate to the detail page of the lowest-priced product that plausibly matches the product type. Price optimization starts with the cheapest option and works upward only if the cheapest fails attribute verification.

### Step 5: Verify non-price attributes on the detail page
- **Tool**: `get_page_observation`, `click_element` (Description/Overview), `get_page_observation`
- **Examples**:
  - `get_page_observation()` — read the Item page
  - `click_element({"element_text": "Description"})` → `get_page_observation()`
- **Purpose**: Confirm that the product satisfies all required non-price attributes. A cheap product that doesn't meet requirements is not a valid choice. Check critical attributes first — if a must-have attribute is missing, move to the next candidate immediately.

### Step 6: Verify the exact price on the detail page
- **Tool**: `get_page_observation`
- **Example**: `get_page_observation()`
- **Purpose**: Confirm the final price shown on the product detail page. The detail page price is authoritative — search result prices may differ.

### Step 7: Evaluate and decide
- **Purpose**: If the cheapest candidate satisfies all non-price requirements AND is within budget → select it. If it fails attribute checks or exceeds budget → return to search results and examine the next cheapest candidate. For "best value" instructions, you may need to examine 2-3 candidates and weigh price against features.

### Step 8: Return to results and examine next candidate (if needed)
- **Tool**: `click_element`
- **Example**: `click_element({"element_text": "Back to Search"})`
- **Purpose**: If the current candidate is not suitable, return to search and open the next cheapest option. Continue until a satisfactory product is found.

## Tools Involved

`get_instruction`, `search_product`, `get_page_observation`, `get_available_actions`, `click_element`

## Tips

- Never include price in the search query string — BM25 doesn't understand numeric ranges, and price terms in the query may filter out relevant products with different price phrasing
- The cheapest product may have hidden quality trade-offs — verify all required attributes, not just price
- For "best value" instructions, consider the feature-to-price ratio: a $45 product with all features may be better value than a $15 product missing key attributes
- If all products matching non-price requirements exceed the budget, the task may require a trade-off — relax the least critical attribute first
- Always verify the price on the detail page, not just the search results snippet
- For "under $X" constraints, the product price must be strictly less than X (not equal to X)
