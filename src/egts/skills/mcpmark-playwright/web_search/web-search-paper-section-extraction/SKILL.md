# Web Search Paper Section Extraction

## Description

Find a research paper through browser search, navigate to the paper text, locate a named section, and extract all paragraphs exactly.

## Use Cases

- Find a research paper through browser search, navigate to the paper text, locate a named section, and extract all paragraphs exactly
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

### Step 4: Enter domain-specific input
- **Tool**: `browser_type` × 1-n times
- **Example**: `browser_type({"selector": "input[name=q]", "text": "paper title section name"})`
- **Purpose**: Fill search boxes, forms, login fields, checkout fields, or admin filters.

### Step 5: Submit keyboard-driven input
- **Tool**: `browser_press_key` × 1-n times
- **Example**: `browser_press_key({"key": "Enter"})`
- **Purpose**: Trigger search, form submission, or field confirmation when the UI expects a keypress.

### Step 6: Click target control
- **Tool**: `browser_click` × 1-n times
- **Example**: `browser_click({"selector": "text=Result title"})`
- **Purpose**: Activate buttons, links, menu items, filters, pagination, or row actions.

### Step 7: Wait for state change
- **Tool**: `browser_wait_for` × 1-n times
- **Example**: `browser_wait_for({"text": "References"})`
- **Purpose**: Allow navigation, Ajax grids, result panels, or validation messages to settle.

### Step 8: Verify final browser state
- **Tool**: `browser_get_text` × 1-n times
- **Example**: `browser_get_text({})`
- **Purpose**: Confirm the final page state, extracted evidence, or mutation result is visible.

## Tools Involved

- `browser_navigate`
- `browser_snapshot`
- `browser_type`
- `browser_press_key`
- `browser_click`
- `browser_wait_for`
- `browser_get_text`
- `browser_evaluate`

## Tips

- Open and read source pages; do not trust search-result snippets alone.
- For exact extraction tasks, preserve paragraph order and wording.
- Use multiple sources when claims conflict or dates are ambiguous.
- Record enough page text to support the final answer.
