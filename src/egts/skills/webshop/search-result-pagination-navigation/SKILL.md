# Search Result Pagination & Navigation

## Description

When the target product is not visible on the first page of search results, systematically browse through subsequent pages using pagination controls, scan each page's product listings for instruction-matching candidates, and decide when to stop paginating — either because the product was found, results become irrelevant, or further pages are unlikely to contain better matches than candidates already seen.

## Use Cases

- Search for "mechanical keyboard" returns 10 results on page 1, but the specific Cherry MX Brown variant is on page 2 or 3
- Broad product category search ("lamp") returns 5+ pages of results — paginate until a candidate matching the instruction's specific attributes appears
- After screening all candidates on page 1, none fully satisfy the instruction — paginate to find additional options
- Search results degrade in relevance after page 3 — recognize when to stop and refine the query instead

## Workflow

### Step 1: Scan the current results page for candidates
- **Tool**: `get_page_observation`
- **Example**: `get_page_observation()`
- **Purpose**: Read all product listings on the current page. Mentally note which products could plausibly match the instruction based on their titles and visible prices. If no viable candidates are present, pagination is needed.

### Step 2: Check pagination availability
- **Tool**: `get_available_actions`
- **Example**: `get_available_actions()`
- **Purpose**: Determine whether "Next Page" or "Prev Page" actions are available. WebShop search results are paginated — if only one page exists, "Next Page" will not appear. Also note if "Back to Search" is available for returning to query reformulation.

### Step 3: Navigate to the next results page
- **Tool**: `click_element`
- **Example**: `click_element({"element_text": "Next Page"})`
- **Purpose**: Move to the next page of search results. Each page typically shows 10 products. The URL changes but the agent only sees the page content.

### Step 4: Observe the new page's products
- **Tool**: `get_page_observation`
- **Example**: `get_page_observation()`
- **Purpose**: Read the product listings on the new page. Compare relevance against previous pages. Products on later pages may have lower BM25 scores but could still be the correct match.

### Step 5: Check available actions on the new page
- **Tool**: `get_available_actions`
- **Example**: `get_available_actions()`
- **Purpose**: Identify clickable products and whether further pagination ("Next Page") or backward navigation ("Prev Page") is available.

### Step 6: Decide: investigate candidates or continue paginating
- **Purpose**: If a promising candidate appears on the current page, open it for attribute verification. If no candidates appear but more pages exist and results are still topically relevant, continue to the next page. If results have become clearly irrelevant (wrong product type, completely unrelated categories), stop paginating.

### Step 7: Stop paginating and pivot if needed
- **Purpose**: Recognize when pagination is no longer productive. Signs include: (a) 3+ pages scanned with no viable candidates, (b) results shifting to unrelated product types, (c) found a satisfactory candidate on a previous page. If no viable candidate exists across all scanned pages, return to search and refine the query using a different strategy.

### Step 8: Return to a specific page if needed
- **Tool**: `click_element`
- **Example**: `click_element({"element_text": "Prev Page"})`
- **Purpose**: Navigate backward if the best candidate was on a previous page. WebShop supports bidirectional pagination within a search session.

## Tools Involved

`get_page_observation`, `get_available_actions`, `click_element`, `search_product`

## Tips

- Don't paginate endlessly — after 3-4 pages, results typically degrade and query refinement is more effective than more pagination
- The best match may not be on page 1 — BM25 ranks by text relevance, not by how well the product satisfies all instruction attributes
- Track which pages you've already visited and which candidates you've screened to avoid circular navigation
- If a page has no clickable products, the search may have returned fewer results than expected — pagination may not be needed
- Use "Prev Page" to return to promising candidates rather than re-executing the search, which may produce different rankings
- Pagination is most useful in dense product categories (Electronics, Fashion) where many products share the same type
