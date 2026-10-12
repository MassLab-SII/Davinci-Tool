# Browser State Verification

## Description

Verify browser-based research, shopping, and application tasks by comparing the live page state with the local requirements and saving traceable evidence. Use this in Toolathlon `browser_form_workspace` tasks where the final answer depends on what was actually visible or submitted in a browser session.

## Use Cases

- Confirm that a web form submission reached the expected confirmation or post-submit state
- Verify product, university, professor, or conference information gathered from web pages before writing a recommendation
- Capture browser evidence for tasks where a page changes after filtering, clicking, or navigating
- Save a concise verification note that links local constraints to observed page state

## Workflow

### Step 1: Discover allowed workspace roots
- **Tool**: `filesystem-list_allowed_directories`
- **Example**: `filesystem-list_allowed_directories({})`
- **Purpose**: Identify the writable workspace roots for verification notes and any local task instructions.

### Step 2: Inspect local task inputs
- **Tool**: `filesystem-list_directory`, then `filesystem-read_file` × 1-n times
- **Examples**:
  - `filesystem-list_directory({"path": "/workspace"})`
  - `filesystem-read_file({"path": "/workspace/requirements.txt"})`
- **Purpose**: Read the exact constraints to verify, such as budget, location, target field, application preference, or required output format.

### Step 3: Capture the current browser state
- **Tool**: `playwright_with_chunk-browser_snapshot` × 1-n times
- **Example**: `playwright_with_chunk-browser_snapshot({})`
- **Purpose**: Inspect the accessible page text and controls after navigation, filtering, filling, or submission. Use this as the primary evidence of current browser state.

### Step 4: Capture visual evidence when page structure matters
- **Tool**: `playwright_with_chunk-browser_take_screenshot`
- **Example**: `playwright_with_chunk-browser_take_screenshot({})`
- **Purpose**: Preserve a visual checkpoint when confirmation banners, selected filters, rankings, or rendered tables are important and may not be obvious from text alone.

### Step 5: Compare observed state to local requirements
- **Tool**: `filesystem-write_file`
- **Example**: `filesystem-write_file({"path": "/workspace/browser_verification.md", "content": "Requirement | Observed browser evidence | Status\n--- | --- | ---\nBudget < $400 | Product A listed at $329 | pass"})`
- **Purpose**: Write a structured verification note tying each task requirement to browser evidence, not just a generic statement that the page looked correct.

### Step 6: Re-read the verification artifact
- **Tool**: `filesystem-read_file`
- **Example**: `filesystem-read_file({"path": "/workspace/browser_verification.md"})`
- **Purpose**: Confirm the saved verification artifact exists and contains the evidence needed for downstream synthesis.

## Tools Involved

`filesystem-list_allowed_directories`, `filesystem-list_directory`, `filesystem-read_file`, `filesystem-write_file`, `playwright_with_chunk-browser_snapshot`, `playwright_with_chunk-browser_take_screenshot`

## Tips

- Treat browser snapshots as evidence, not completion by themselves; compare them against explicit task constraints
- Use screenshots when page layout, selected filters, or confirmation state matters
- Do not invent confirmation: if the snapshot does not show success, navigate or inspect again before writing the verification note
- Keep the final note compact but traceable enough for EGTS synthesis to reconstruct the browser-side intent
