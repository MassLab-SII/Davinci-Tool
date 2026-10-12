# Form Filling and Submission

## Description
Type text into form fields, fill login/signup forms, use search engines, and submit completed forms. These MiniWoB++ tasks simulate real-world data entry workflows where the correct information must be entered into the right fields and submitted.

## Use Cases
- enter-text, enter-text-2, enter-text-dynamic — type specific text strings
- enter-date, enter-time, enter-password — enter formatted data
- login-user, login-user-popup — complete login forms
- sign-agreement — fill and sign agreements
- search-engine — use a search interface
- focus-text, focus-text-2 — type into focused fields
- choose-date, choose-date-easy/medium/nodelay — select dates

## Workflow

1. **Observe the page and read the instruction**
   - Tool: `get_observation`, `get_instruction`
   - Example: `get_observation()` → see what fields need filling
   - Purpose: Understand what data to enter and where

2. **Identify input fields**
   - Tool: `get_dom_elements`
   - Example: `get_dom_elements(filter_type="input")` → find all input elements with their refs
   - Purpose: Map each field to its EGTS ref

3. **Check current field values** (if needed)
   - Tool: `get_fields`
   - Example: `get_fields()` → see current values of all form fields
   - Purpose: Know what's already filled

4. **Type into each field** in the required order
   - Tool: `type_text`
   - Example: `type_text(ref=2, text="john.doe@example.com")` → fills the email field
   - Purpose: Enter the correct data

5. **Submit the form**
   - Tool: `click_element` or `press_key`
   - Example: `click_element(ref=5)` — click the submit button; or `press_key(ref=2, key="Enter")` — submit via keyboard
   - Purpose: Complete the form

6. **Verify submission**
   - Tool: `get_observation`
   - Example: `get_observation()` → confirm form was accepted
   - Purpose: Ensure success

## Tools Involved
- `get_observation` — see form structure
- `get_instruction` — understand what to enter
- `get_dom_elements` — find input field refs
- `get_fields` — read current field values
- `type_text` — enter text into fields
- `click_element` — click submit buttons

## Tips
- Use `clear_first=true` if replacing existing field content
- Use `get_fields()` to verify values after typing
- For date/time fields, match the exact format shown in the instruction
- Press Enter on the last field to submit forms without finding the submit button
- Some forms have dynamic validation — re-observe after each field
