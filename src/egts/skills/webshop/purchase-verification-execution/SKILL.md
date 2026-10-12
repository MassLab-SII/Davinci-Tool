# Purchase Verification & Execution

## Description

Before clicking Buy, perform a comprehensive final verification of the selected product, configured options, and price against the original shopping instruction. This is the last line of defense against attribute mismatch, wrong option selection, or budget overrun — mistakes that directly reduce the WebShop benchmark score across product match, attribute match, option match, and price constraint components.

## Use Cases

- After navigating product pages and selecting options, confirm every instruction requirement is satisfied before the irrevocable Buy click
- Verify the final configured price (which may change after option selection) is within the instruction's budget
- Double-check that the selected options (size, color) exactly match what the instruction specifies, not just what seemed reasonable
- When multiple navigation steps preceded purchase, re-read the instruction to avoid recency bias from recently viewed products
- Confirm the product on the current page is the one that passed attribute verification — not a different product navigated to by accident

## Workflow

### Step 1: Re-read the full instruction
- **Tool**: `get_instruction`
- **Example**: `get_instruction()`
- **Purpose**: Retrieve the original shopping instruction as the authoritative reference. Do not rely on memory — after multiple search, navigation, and product inspection steps, details may be misremembered. Note every required attribute, option, and the price constraint.

### Step 2: Read the current product page in full
- **Tool**: `get_page_observation`
- **Example**: `get_page_observation()`
- **Purpose**: Capture the complete current page content — product title, price (as currently configured with selected options), option selections, and any visible attributes. This is the evidence of what will be purchased.

### Step 3: Verify product identity
- **Purpose**: Confirm the product on the current page is the correct product type as specified in the instruction. Does the product title and description match the product category from the instruction? This maps to the `r_type` component of the WebShop reward — buying the wrong product type incurs a type penalty.

### Step 4: Verify selected options against instruction
- **Tool**: `get_available_actions`
- **Example**: `get_available_actions()`
- **Purpose**: Check whether any option selectors remain unconfigured. Then verify each selected option against the instruction's option requirements (`U_opt`). A correct product with wrong options scores zero on the option-match component.

### Step 5: Verify price against budget constraint
- **Purpose**: Read the displayed price from the current page (Step 2) and compare against the instruction's price constraint (`u_price`). Confirm the price is strictly within budget. Note: the price after option selection may differ from the search results price.

### Step 6: Build a mental checklist
- **Purpose**: Cross-reference each instruction requirement against the current state:
  - Product type: ✓/✗
  - Attribute 1 (e.g., color): ✓/✗
  - Attribute 2 (e.g., material): ✓/✗
  - Option 1 (e.g., size): ✓/✗
  - Price constraint: ✓/✗
  If any item fails, do NOT proceed to Buy — navigate back and find the correct product/option.

### Step 7: Execute the purchase
- **Tool**: `click_element`
- **Example**: `click_element({"element_text": "Buy"})`
- **Purpose**: Only after all verification checks pass, click Buy to complete the purchase. In WebShop, this action is immediate and ends the episode — there is no confirmation dialog.

### Step 8: Capture purchase confirmation
- **Tool**: `get_page_observation`
- **Example**: `get_page_observation()`
- **Purpose**: After clicking Buy, read the final page to capture the order confirmation. Record: purchased product name, final price, and any confirmation message. This is the terminal evidence for the trajectory and serves as the final state for synthesis.

## Tools Involved

`get_instruction`, `get_page_observation`, `get_available_actions`, `click_element`

## Tips

- **Never skip the final verification** — even if you're confident, a quick re-check prevents score-losing mistakes
- The Buy action is **irreversible** — once clicked, the episode ends and the purchase is final
- Price can change after option selection — always verify the final displayed price, not the search result price
- If verification reveals a mismatch, abandon the purchase and navigate back — a correct product found later is better than a wrong product bought now
- Multiple navigation steps can cause confusion about which product is currently displayed — the `get_page_observation` output is always the ground truth
- Option labels displayed after selection may be abbreviated — verify they semantically match the instruction, not just visually
