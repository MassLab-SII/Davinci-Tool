# Multi-Product Candidate Screening

## Description

When a search returns multiple products that could plausibly match the instruction, systematically screen each candidate by opening detail pages, comparing their attributes against requirements, eliminating non-matches, and selecting the product that best satisfies all constraints. This skill addresses the strategic exploration challenge — common in dense product categories like Electronics and Fashion.

## Use Cases

- Search for "wireless headphones" returns 5+ results — screen each to find the one with noise cancelling under $100
- Multiple products share the same name but differ in brand, specs, or options — identify which is the correct match
- Instruction specifies multiple equally-weighted attributes ("waterproof, lightweight, under $50") — find the product that maximizes attribute satisfaction
- Ambiguous product type ("LED desk lamp with adjustable brightness and color temperature") — compare candidates to find the one with both features

## Workflow

### Step 1: Survey the search results
- **Tool**: `get_page_observation`
- **Example**: `get_page_observation()`
- **Purpose**: After executing a search, read all product listings on the current results page. Note product names, visible prices, and brief descriptions. Mentally rank candidates by how well their titles match the instruction.

### Step 2: List all clickable candidates
- **Tool**: `get_available_actions`
- **Example**: `get_available_actions()`
- **Purpose**: Identify every clickable product title in the results. Note pagination availability ("Next Page") if more results exist beyond the current page.

### Step 3: Open the most promising candidate
- **Tool**: `click_element`
- **Example**: `click_element({"element_text": "Wireless Bluetooth Headphone Noise Cancelling"})`
- **Purpose**: Start with the candidate whose title best matches the instruction's product type and key attributes.

### Step 4: Read detail page and verify attributes
- **Tool**: `get_page_observation`
- **Example**: `get_page_observation()`
- **Purpose**: Capture the product's full details. Check the product title, price, and visible specifications against the instruction requirements.

### Step 5: Check Description and Overview
- **Tool**: `click_element` (Description), `get_page_observation`, `click_element` (Overview), `get_page_observation`
- **Examples**:
  - `click_element({"element_text": "Description"})` → `get_page_observation()`
  - `click_element({"element_text": "Overview"})` → `get_page_observation()`
- **Purpose**: Extract hidden attributes from both detail sections. Verify features that aren't visible in the search listing or main Item page.

### Step 6: Score the candidate against instruction
- **Tool**: `get_instruction` (reference check)
- **Example**: `get_instruction()`
- **Purpose**: Re-read the original instruction and count: (a) how many required attributes this product satisfies, (b) whether the price is within budget, (c) whether all required options are available. Decide: keep as best-match or eliminate.

### Step 7: Return to results and screen next candidate
- **Tool**: `click_element`
- **Example**: `click_element({"element_text": "Back to Search"})`
- **Purpose**: Navigate back to the search results page. If pagination is needed, click "Next Page" to access additional candidates.

### Step 8: Repeat Steps 3-7 for each viable candidate
- **Purpose**: Continue screening until you have examined all promising candidates or have found a product that satisfies all requirements with high confidence.

### Step 9: Select the best-matching product
- **Purpose**: After screening, identify the product that satisfies the most required attributes AND is within budget. Navigate to its detail page to proceed with option selection and purchase. If multiple products are equally good, prefer the lower-priced one.

## Tools Involved

`search_product`, `click_element`, `get_page_observation`, `get_available_actions`, `get_instruction`

## Tips

- Don't screen every single search result — prioritize candidates whose titles contain instruction keywords
- Track which candidates you've already examined to avoid re-visiting the same product
- If no candidate satisfies all attributes, choose the one that satisfies the most — some attributes may be more important than others
- In dense categories (Electronics, Fashion), checking at least 2-3 candidates before deciding significantly improves match accuracy
- Use "Next Page" to access more results if the first page has no viable candidates
- The WebShop search engine (BM25) may rank products by text relevance, not price — the best match may not be the first result
