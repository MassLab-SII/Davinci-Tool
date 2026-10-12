# Text Editing and Formatting

## Description
Perform copy/paste operations, highlight text, transform text content, find and replace text, and resize text areas. These MiniWoB++ tasks cover the core text manipulation primitives found in editors and word processors.

## Use Cases
- copy-paste, copy-paste-2 — copy text from one field to another
- highlight-text, highlight-text-2 — highlight specific text portions
- text-editor — use a rich text editor interface
- text-transform — transform text (uppercase, lowercase, etc.)
- find-word — locate a specific word in text
- resize-textarea — resize a text area by dragging

## Workflow

1. **Read the instruction and observe the page**
   - Tool: `get_instruction`, `get_observation`
   - Example: `get_observation()` → see the source text and target area
   - Purpose: Understand what text operation is needed

2. **Get all interactive elements**
   - Tool: `get_dom_elements`
   - Example: `get_dom_elements()` → find input/textarea refs and button refs
   - Purpose: Map the text source, target field, and action buttons to EGTS refs

3. **For copy-paste: select source, copy, paste to target**
   - Tool: `click_element` (select), `press_key` (copy/paste shortcuts), or `type_text`
   - Example: Click source field → `press_key(ref=3, key="Enter")` or use Ctrl+A/Ctrl+C/Ctrl+V patterns
   - Purpose: Transfer text between fields

4. **For highlight tasks: select the specified text range**
   - Tool: `click_element` to focus, then use the task-specific method
   - Purpose: Mark the correct text portion

5. **For text transformation: type or use buttons**
   - Tool: `type_text` or `click_element` on formatting buttons
   - Example: `type_text(ref=5, text="TRANSFORMED TEXT")` → enter the transformed result
   - Purpose: Apply the required transformation

6. **Verify the result**
   - Tool: `get_observation` or `get_fields`
   - Example: `get_fields()` → check the output field contains the expected text
   - Purpose: Confirm the operation succeeded

## Tools Involved
- `get_instruction` — task goal
- `get_observation` — page content
- `get_dom_elements` — find element refs
- `get_fields` — read field values
- `type_text` — enter text
- `press_key` — keyboard shortcuts (Ctrl+A, Ctrl+C, Ctrl+V, etc.)
- `click_element` — focus fields, click buttons

## Tips
- For copy-paste: the text source is usually shown in the instruction or in a read-only area
- `press_key` with Tab can move between fields quickly
- Use `clear_first=true` with `type_text` when replacing entire field content
- Key combinations (Ctrl+C, Ctrl+V) may need multiple `press_key` calls in sequence
- Some tasks display the expected result — compare your output against it
