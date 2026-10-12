# Search Query Iteration & Refinement

## Description

When an initial search query returns zero results, too few relevant products, or too many unrelated products, systematically iterate on the query — broaden by removing restrictive terms, narrow by adding discriminative attributes, substitute synonyms, or pivot to an entirely different query strategy. This is one of the four core challenges identified in the WebShop benchmark: query (re-)formulation.

## Use Cases

- Initial search for "red wool sweater" returns zero results — broaden to "wool sweater" then filter visually for red
- Search for "wireless noise cancelling headphones" returns 50+ results — narrow with brand or price tier
- Product type uses terminology that differs from WebShop's catalog — try synonyms ("sneakers" → "running shoes" → "athletic footwear")
- Multi-word instruction where keyword order or selection changes BM25 ranking dramatically — reorder or prune query terms
- Instruction contains a rare attribute that eliminates all results — remove that attribute and verify it manually on product pages

## Workflow

### Step 1: Evaluate the current search results
- **Tool**: `get_page_observation`
- **Example**: `get_page_observation()`
- **Purpose**: After executing a search, assess result quality. Categorize as: (a) zero results — query too restrictive, (b) irrelevant results — wrong product type surfacing, (c) too many results — query too broad, (d) plausible results but target product not visible — may need pagination or refinement.

### Step 2: Diagnose the failure mode
- **Tool**: `get_instruction` (reference)
- **Example**: `get_instruction()`
- **Purpose**: Compare the instruction against the search results. Identify which query terms may be causing the problem: overly specific terms that don't match catalog language, common terms that match too many unrelated products, or terms that the BM25 index doesn't weight effectively.

### Step 3: Choose a refinement strategy
- **Purpose**: Based on the diagnosis, select an approach:
  - **Broadening**: Remove the most restrictive attribute, keep product type. Use when zero results.
  - **Narrowing**: Add a discriminative attribute (brand, material, unique feature). Use when too many results.
  - **Synonym substitution**: Replace a term with a known synonym. Use when results are for the wrong product type.
  - **Term reordering**: Change keyword order, which affects BM25 scoring. Use when results are close but not quite right.
  - **Pivot**: Completely reformulate with a different product type description. Use when the category itself is wrong.

### Step 4: Execute the refined search
- **Tool**: `search_product`
- **Examples**:
  - Broadening: `search_product({"query": "wool sweater"})` — removed "red"
  - Narrowing: `search_product({"query": "Sony noise cancelling headphones"})` — added brand
  - Synonym: `search_product({"query": "athletic shoes lightweight"})` — replaced "sneakers"
  - Pivot: `search_product({"query": "desk lighting adjustable"})` — restructured query
- **Purpose**: Submit the refined query. The new query should differ meaningfully from the previous one — avoid trivial changes that won't affect BM25 ranking.

### Step 5: Observe refined results
- **Tool**: `get_page_observation`
- **Example**: `get_page_observation()`
- **Purpose**: Read the new search results. Compare against the previous search. Has the target product surfaced? Has relevance improved? If still unsatisfactory, return to Step 2 and try a different strategy.

### Step 6: Track attempted queries
- **Purpose**: Mentally track which queries have been tried and their outcomes. Avoid repeating a failed query. If 3-4 different query formulations all fail, the product may not exist in the catalog — consider the closest available match and proceed to attribute verification.

## Tools Involved

`search_product`, `get_page_observation`, `get_instruction`

## Tips

- Never repeat the same query — each attempt should differ in strategy, not just wording
- If broadening removed a required attribute, remember to verify that attribute manually on product detail pages
- BM25 is sensitive to term frequency and document length — rare terms get higher weight, common terms get lower weight
- Query order matters for BM25 — the first term gets slightly more weight
- After 3-4 failed queries, stop iterating and work with the best available results — the product may genuinely not exist in the dataset
- Keep search queries concise (2-5 words) — overlong queries dilute BM25 term weights
