# Category Hierarchy Browsing

## Description

Navigate WebShop's product taxonomy by browsing category and subcategory pages as an alternative discovery path to keyword search. When the instruction's product type is clear but keyword search terms are difficult to formulate — or when keyword search returns poor results — browse down the category hierarchy to find products organized by type, department, and subcategory.

## Use Cases

- Instruction asks for a product type that maps naturally to a category ("men's leather wallet") but keyword search returns mixed results — browse Fashion > Accessories > Wallets
- The instruction uses vague terminology ("something for the kitchen") — browse the Kitchen/Food category to see what's available
- Keyword search keeps returning the wrong product type due to ambiguous terms — sidestep search entirely and navigate by category
- Exploring related subcategories to discover product variants not captured by initial search terms
- Multi-category tasks where products might live in different departments — browse both to compare

## Workflow

### Step 1: Start from the homepage or search reset
- **Tool**: `get_available_actions`
- **Example**: `get_available_actions()`
- **Purpose**: At the beginning of a session or after resetting, check the top-level navigation. WebShop's homepage may display category links, a search bar, and featured sections. Identify the category structure.

### Step 2: Map instruction to top-level category
- **Tool**: `get_instruction`
- **Example**: `get_instruction()`
- **Purpose**: Read the instruction and determine which of WebShop's 5 top-level categories (Fashion, Makeup, Electronics, Furniture, Food) best matches the product type. For example, "cotton t-shirt" → Fashion, "USB drive" → Electronics.

### Step 3: Navigate into the target top-level category
- **Tool**: `click_element`
- **Example**: `click_element({"element_text": "Electronics"})`
- **Purpose**: Click the category link to enter the department page. This page typically shows subcategories and possibly featured products.

### Step 4: Observe subcategories and featured products
- **Tool**: `get_page_observation`
- **Example**: `get_page_observation()`
- **Purpose**: Read the category page content. Identify: (a) available subcategories, (b) any featured or top-selling products, (c) whether the page shows product listings directly or requires further subcategory navigation.

### Step 5: Check available subcategory navigation
- **Tool**: `get_available_actions`
- **Example**: `get_available_actions()`
- **Purpose**: List all clickable subcategories and products on the current category page. Determine the drill-down path to reach the specific product type.

### Step 6: Drill down into the relevant subcategory
- **Tool**: `click_element`
- **Example**: `click_element({"element_text": "USB Flash Drives"})`
- **Purpose**: Navigate deeper into the category hierarchy. Repeat Steps 4-6 as needed until reaching a product listing page showing individual products.

### Step 7: Browse products within the subcategory
- **Tool**: `get_page_observation`, `get_available_actions`
- **Examples**:
  - `get_page_observation()` — read product listings
  - `get_available_actions()` — identify clickable products and pagination
- **Purpose**: Once at the product listing level, scan for products matching the instruction's attributes. If the subcategory contains many products, use pagination to browse additional pages.

### Step 8: Select a product for detail verification
- **Tool**: `click_element`
- **Example**: `click_element({"element_text": "SanDisk 64GB Ultra USB 3.0 Flash Drive"})`
- **Purpose**: Click on a promising product to open its detail page. Proceed with attribute verification and purchase workflow from this point.

### Step 9: Navigate back up the hierarchy if needed
- **Tool**: `click_element`
- **Example**: `click_element({"element_text": "Back to Electronics"})` or `click_element({"element_text": "Back to Search"})`
- **Purpose**: If the current subcategory doesn't contain matching products, navigate back up to try a different subcategory or switch to keyword search.

## Tools Involved

`get_available_actions`, `get_page_observation`, `click_element`, `get_instruction`, `search_product`

## Tips

- Category browsing works best when the product type clearly belongs to one category — for cross-category products, keyword search may be faster
- Subcategory names may use different terminology than the instruction — "Footwear" vs "shoes", "Computers & Tablets" vs "laptop"
- Some products may appear in multiple categories — if not found in the expected category, try a related one
- Category pages may show "featured" or "best-selling" items rather than a complete listing — paginate to see all products
- Combine with keyword search: browse to the right category, then use search within that context to filter further
- Category navigation is slower than keyword search for specific products, but more reliable when search terms are ambiguous
