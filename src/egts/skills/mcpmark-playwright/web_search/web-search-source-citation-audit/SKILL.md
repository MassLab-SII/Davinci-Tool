# Web Search Source Citation Audit

## Description

Audit a source page for headings, citations, outbound links, metadata, and exact text spans supporting the final answer.

## Use Cases

- Audit a source page for headings, citations, outbound links, metadata, and exact text spans supporting the final answer
- Search for public facts and verify them against source pages.
- Extract precise biographical, paper, or citation evidence.
- Compare multiple candidate pages before choosing a final fact.
- Audit headings, links, snippets, and page text for source support.
- Preserve exact text spans when the task asks for extraction.

## Workflow

### Step 1: Navigate to the task page
- **Tool**: `browser_navigate`
- **Example**: `browser_navigate({"url": "https://www.google.com/search?q=target+person+birth+year"})`
- **Purpose**: Open the page or search entry point required by the task.

### Step 2: Capture page structure
- **Tool**: `browser_snapshot` × 1-n times
- **Example**: `browser_snapshot({})`
- **Purpose**: Ground the next action in the current visible accessibility tree.

### Step 3: Read visible page text
- **Tool**: `browser_get_text` × 1-n times
- **Example**: `browser_get_text({})`
- **Purpose**: Collect the current page text before filtering, extracting, or mutating state.

### Step 4: Wait for state change
- **Tool**: `browser_wait_for` × 1-n times
- **Example**: `browser_wait_for({"text": "References"})`
- **Purpose**: Allow navigation, Ajax grids, result panels, or validation messages to settle.

### Step 5: Extract structured DOM evidence
- **Tool**: `browser_evaluate` × 1-n times
- **Example**: `browser_evaluate({"script": "document.body.innerText"})`
- **Purpose**: Collect table rows, grid values, attributes, counters, or computed state precisely.

### Step 6: Inspect network evidence
- **Tool**: `browser_network_requests` × 1-n times
- **Example**: `browser_network_requests({})`
- **Purpose**: Check request activity when page state depends on loading, redirects, or source-page auditing.

### Step 7: Verify final browser state
- **Tool**: `browser_get_text` × 1-n times
- **Example**: `browser_get_text({})`
- **Purpose**: Confirm the final page state, extracted evidence, or mutation result is visible.

## Tools Involved

- `browser_navigate`
- `browser_snapshot`
- `browser_get_text`
- `browser_evaluate`
- `browser_network_requests`
- `browser_wait_for`

## Tips

- Open and read source pages; do not trust search-result snippets alone.
- For exact extraction tasks, preserve paragraph order and wording.
- Use multiple sources when claims conflict or dates are ambiguous.
- Record enough page text to support the final answer.
