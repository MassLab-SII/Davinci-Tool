# Option Variant Configuration

## Description

When a product has configurable options (size, color, style, material variant, quantity), identify the required option values from the instruction, select each option correctly on the product page, and verify the configuration before adding to cart. Option selection is a critical error point — a correct product with wrong options gets zero option-match score.

## Use Cases

- Instruction specifies "size medium, navy blue" — select the correct size option and color option before buying
- Product has multiple color variants — identify which color name in the dropdown matches the instruction's color description
- Instruction requires a specific quantity or pack size — select the correct variant from options
- Product options use different terminology than the instruction (e.g., instruction says "navy" but dropdown says "dark blue") — map between them

## Workflow

### Step 1: Check what options are available on the product page
- **Tool**: `get_available_actions`
- **Example**: `get_available_actions()`
- **Purpose**: After navigating to the product detail page, list all configurable options. Identify which options correspond to the instruction's requirements (e.g., if "size medium" is required, look for a size selector in the available actions).

### Step 2: Read the product page to understand option values
- **Tool**: `get_page_observation`
- **Example**: `get_page_observation()`
- **Purpose**: Read all available option values and their labels. Some option dropdowns may show abbreviated text — the full observation gives context for which value to select.

### Step 3: Re-read the instruction for option requirements
- **Tool**: `get_instruction`
- **Example**: `get_instruction()`
- **Purpose**: Extract the exact option specifications from the instruction. Note: the instruction may use natural language ("navy blue", "size 10", "large") while options may use specific labeling ("Color: Navy", "10", "L").

### Step 4: Select each required option
- **Tool**: `click_element` × 1-n times (once per option)
- **Examples**:
  - `click_element({"element_text": "Navy"})` — select the color option
  - `click_element({"element_text": "M"})` — select the size option
  - `click_element({"element_text": "32oz"})` — select the size/quantity variant
- **Purpose**: Click on each option value that matches the instruction requirements. If the instruction specifies multiple options (e.g., color AND size), select each one in sequence.

### Step 5: Verify the selected configuration
- **Tool**: `get_page_observation`
- **Example**: `get_page_observation()`
- **Purpose**: After selecting options, re-read the page to confirm the selections were applied. The page content should now reflect the chosen options (e.g., updated price, selected variant shown).

### Step 6: Check remaining actions (including Buy)
- **Tool**: `get_available_actions`
- **Example**: `get_available_actions()`
- **Purpose**: Verify that all required options have been selected (no remaining required selectors) and that the "Buy" or "Add to Cart" action is now available.

### Step 7: Handle option mapping discrepancies
- **Purpose**: If the instruction's terminology doesn't exactly match option labels (e.g., instruction says "navy blue" but option says "Dark Blue" or "Navy"), use semantic matching — select the closest available option. If uncertain, prefer the option whose label shares the most words with the instruction.

## Tools Involved

`get_available_actions`, `get_page_observation`, `click_element`, `get_instruction`

## Tips

- Always check available actions BEFORE clicking — options may appear as clickable elements that aren't visible in the page text
- Select options in the order they appear on the page; the page may refresh after each selection
- Some products have required options that must be selected before "Buy" becomes available — if Buy is not visible, check for unselected options
- Option labels may use abbreviations (S/M/L, oz, ") — map instruction terms to their abbreviated equivalents
- If the exact option value from the instruction is not available, the product may still be the correct one if another variant name maps to the same specification
- Do NOT add to cart or click Buy until you have verified all options are correctly selected
