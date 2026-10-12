# Basic Click Interaction

## Description
Execute single and multi-click interactions on buttons, links, shapes, and various clickable UI elements in MiniWoB++ tasks. These tasks require identifying the correct target element(s) from the page and clicking them in the right sequence.

## Use Cases
- click-button, click-button-sequence — click specific buttons
- click-link — follow the correct hyperlink
- click-shape, click-color, click-shades — select the correct visual element
- click-dialog, click-dialog-2 — interact with dialog boxes
- click-test, click-test-2, click-test-transfer — click the right option
- click-widget, click-option, click-pie — click specific widget elements
- visual tasks: circle-center, count-shape, identify-shape, etc.

## Workflow

1. **Observe the page** — understand what the task asks you to do
   - Tool: `get_observation`
   - Example: `get_observation()` → see page title, instruction, and visible text
   - Purpose: Understand the task goal and current page state

2. **Scan interactive elements** — find what's clickable on the page
   - Tool: `get_dom_elements`
   - Example: `get_dom_elements()` → returns elements with egts_ref numbers, tags, and text
   - Purpose: Map egts_ref numbers to visible elements

3. **Re-read instruction** if unclear
   - Tool: `get_instruction`
   - Example: `get_instruction()` → confirms exact task requirement
   - Purpose: Ensure you click the right targets

4. **Click the target element(s)** — execute the required clicks
   - Tool: `click_element`
   - Example: `click_element(ref=3)` → clicks the element with egts_ref=3
   - Purpose: Perform the interaction

5. **Verify the result** — check that the page changed correctly
   - Tool: `get_observation`
   - Example: `get_observation()` → confirm success or identify next step
   - Purpose: Validate the click had the expected effect

## Tools Involved
- `get_observation` — page state overview
- `get_dom_elements` — find element refs
- `get_instruction` — confirm task goal
- `click_element` — execute clicks

## Tips
- Always call `get_dom_elements()` after page changes to get fresh EGTS refs
- EGTS refs are only valid within a single observation-action cycle
- For multi-click sequences, verify each click before proceeding
- Hidden elements (visible=false) cannot be clicked
- Pay attention to aria_label for accessibility-labeled elements
