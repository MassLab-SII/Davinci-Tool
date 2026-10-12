# Keyword Search Query Formulation

## Description

Parse a shopping instruction to extract key product descriptors (type, category, brand, material, style), formulate effective search queries, execute searches, and evaluate result relevance. Refine queries when initial results don't contain the target product — the most fundamental skill that every WebShop task depends on.

## Use Cases

- Extract discriminative search terms from a natural language instruction like "I'm looking for a red wool sweater under $50"
- Formulate multiple candidate queries when the first search fails to surface the target product
- Identify when a search returns too many irrelevant results and needs narrowing keywords
- Distinguish between searching by product type ("mechanical keyboard") vs. brand ("Cherry MX") vs. attribute ("waterproof")

## Workflow

### Step 1: Read and parse the instruction
- **Tool**: `get_instruction`
- **Example**: `get_instruction()`
- **Purpose**: Retrieve the full shopping task instruction. Identify: (a) the product type/category, (b) required attributes (color, size, material, brand), (c) option requirements, and (d) any price constraint.

### Step 2: Extract searchable keywords
- **Tool**: *(mental analysis — no tool call)*
- **Purpose**: From the instruction, isolate the most discriminative terms. Prioritize product type + distinctive attributes. Avoid overly long queries that may return zero results. Example: from "Find a stainless steel water bottle, 32oz, in blue color", extract `"water bottle stainless steel"` as the primary query.

### Step 3: Execute the search
- **Tool**: `search_product`
- **Example**: `search_product({"query": "water bottle stainless steel"})`
- **Purpose**: Submit the formulated query to WebShop's Pyserini BM25 search engine. The query string should be concise (2-5 words) and focused on product identity over secondary attributes.

### Step 4: Observe search results
- **Tool**: `get_page_observation`
- **Example**: `get_page_observation()`
- **Purpose**: Read the search result listings. Note product names, prices, and brief descriptions. Assess whether any listed products plausibly match the instruction's product type.

### Step 5: Check available result actions
- **Tool**: `get_available_actions`
- **Example**: `get_available_actions()`
- **Purpose**: See which products are clickable in the results, whether pagination ("Next Page") is available, and whether the search bar is still active for refinement.

### Step 6: Evaluate and refine if needed
- **Tool**: `search_product` (if refinement needed)
- **Example**: `search_product({"query": "blue stainless water bottle 32oz"})`
- **Purpose**: If no results match the product type or all results are irrelevant, reformulate the query — add or remove keywords, try synonyms ("sneakers" → "running shoes"), or use broader terms. Avoid repeating the same failed query.

## Tools Involved

`get_instruction`, `search_product`, `get_page_observation`, `get_available_actions`

## Tips

- Start with 2-3 word queries and add keywords only if results are too broad — BM25 performs best with balanced term weighting
- Product-type words are more important than attribute words in queries — "water bottle" > "blue" for retrieval
- If search returns zero results, remove the most restrictive keyword first
- If search returns too many unrelated products, add the most distinctive attribute (brand, material, or unique descriptor)
- Always observe results immediately after searching — the page content is the only evidence of what was found
- The `query` parameter must be a **string**; empty queries will be rejected
