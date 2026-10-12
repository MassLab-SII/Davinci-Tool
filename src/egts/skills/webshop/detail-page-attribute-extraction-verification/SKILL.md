# Detail Page Attribute Extraction & Verification

## Description

Open a product's detail page and systematically verify every required attribute from the shopping instruction against the product's specifications. This skill handles the core challenge of compositional instruction understanding — tasks with 3-8 hidden attributes where the agent must confirm each constraint (color, material, size, brand, feature) before purchasing.

## Use Cases

- Verify a "cotton t-shirt, v-neck, navy blue, size medium" actually matches all four constraints on its detail page
- Check product description and overview sections for attributes not visible in the search result summary
- Identify when a product appears to match in search results but fails attribute verification on the detail page
- Distinguish between products that match in title but differ in specifications

## Workflow

### Step 1: Open the candidate product page
- **Tool**: `click_element`
- **Example**: `click_element({"element_text": "Navy Blue Cotton V-Neck T-Shirt"})`
- **Purpose**: From search results, click the product title to navigate to the Item page where full details are shown. Use `get_available_actions()` first to see the exact clickable product text.

### Step 2: Read the product detail page
- **Tool**: `get_page_observation`
- **Example**: `get_page_observation()`
- **Purpose**: Capture the full Item page content — product title, price, description summary, and available options. This is the primary evidence source for attribute verification.

### Step 3: Check available detail sections
- **Tool**: `get_available_actions`
- **Example**: `get_available_actions()`
- **Purpose**: Identify whether "Description" and "Overview" detail sections are available. Also check for option selectors (size, color dropdowns) and the "Buy" button.

### Step 4: Open Description section (if available)
- **Tool**: `click_element`
- **Example**: `click_element({"element_text": "Description"})`
- **Purpose**: Navigate to the Item-Detail page for Description. This section often contains material composition, dimensions, care instructions, and other attributes not shown on the main Item page.

### Step 5: Read the Description content
- **Tool**: `get_page_observation`
- **Example**: `get_page_observation()`
- **Purpose**: Extract attribute-relevant information from the description text. Look for material, size specs, features, and other instruction-matching details.

### Step 6: Open Overview section (if available)
- **Tool**: `click_element`
- **Example**: `click_element({"element_text": "Overview"})`
- **Purpose**: Navigate to the Item-Detail page for Overview, which often contains structured specifications and attribute lists.

### Step 7: Read the Overview content
- **Tool**: `get_page_observation`
- **Example**: `get_page_observation()`
- **Purpose**: Extract structured product attributes. Cross-reference against the instruction's required attributes.

### Step 8: Cross-reference instruction against product attributes
- **Tool**: `get_instruction` (if needed)
- **Example**: `get_instruction()`
- **Purpose**: Re-read the original instruction and systematically check each required attribute against the evidence gathered from Steps 2-7. Build a mental checklist: color ✓, material ✓, size ✓, price ✓, etc.

### Step 9: Return to search results or navigate back
- **Tool**: `click_element`
- **Example**: `click_element({"element_text": "Back to Search"})`
- **Purpose**: If the product fails one or more attribute checks, return to search results to examine the next candidate. If all attributes match, proceed to option selection and purchase.

## Tools Involved

`click_element`, `get_page_observation`, `get_available_actions`, `get_instruction`, `search_product`

## Tips

- Always check both Description AND Overview when available — attributes may appear in only one section
- Verify every attribute from the instruction independently; don't assume a product that "looks right" matches all constraints
- The product title in search results may not reflect actual specifications on the detail page — always verify on the Item page
- Price displayed on the detail page is the final price; compare against any budget constraint in the instruction
- If a product fails a required attribute, move to the next candidate immediately rather than spending more steps on it
- The `element_text` parameter must be a **string** that exactly matches a clickable element as returned by `get_available_actions()`
