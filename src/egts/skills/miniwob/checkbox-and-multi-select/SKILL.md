# Checkbox and Multi-Select

## Description
Toggle checkboxes and multi-select options according to task instruction constraints. These MiniWoB++ tasks require selecting, deselecting, or transferring multiple items based on specified criteria.

## Use Cases
- click-checkboxes — select/deselect specific checkboxes
- click-checkboxes-large — manage many checkboxes at once
- click-checkboxes-soft — toggle checkboxes with soft constraints
- click-checkboxes-transfer — move items between checkbox groups
- number-checkboxes — select checkboxes by numeric criteria

## Workflow

1. **Read the instruction carefully**
   - Tool: `get_instruction`
   - Example: `get_instruction()` → understand which checkboxes to select/deselect
   - Purpose: Know the exact selection criteria

2. **Observe all checkboxes on the page**
   - Tool: `get_dom_elements`
   - Example: `get_dom_elements(filter_type="input")` → find all checkbox inputs with their labels and refs
   - Purpose: Map each checkbox to its EGTS ref and label text

3. **Click the target checkboxes**
   - Tool: `click_element`
   - Example: `click_element(ref=3)` — toggle checkbox with egts_ref=3
   - Purpose: Select or deselect according to the instruction

4. **Verify current state**
   - Tool: `get_observation` or `get_dom_elements`
   - Example: `get_observation()` → confirm the correct checkboxes are selected
   - Purpose: Ensure all required checkboxes are in the right state

5. **Submit or finalize** if the task requires it
   - Tool: `click_element`
   - Example: `click_element(ref=10)` — click submit/transfer button
   - Purpose: Complete the checkbox operation

## Tools Involved
- `get_instruction` — understand selection criteria
- `get_observation` — see page layout
- `get_dom_elements` — find checkbox refs and labels
- `click_element` — toggle checkboxes
- `scroll_page` — reveal hidden checkboxes in large sets

## Tips
- Filter DOM elements by `filter_type="input"` and look for `type: "checkbox"` in the result
- Check element text carefully — some checkboxes have similar labels
- For transfer tasks, note which group each checkbox belongs to
- Large checkbox sets may require scrolling: use `scroll_page` to reveal hidden options
- Toggle means click once; re-clicking undoes the selection
