# Widget and Control Interaction

## Description
Manipulate specialized UI widgets and controls: sliders, colorwheels, spinners, autocomplete inputs, and scroll-based text areas. These MiniWoB++ tasks require fine-grained interaction with non-standard form controls.

## Use Cases
- use-slider, use-slider-2 — set a slider to a specific value
- use-colorwheel, use-colorwheel-2 — select a color from a colorwheel
- use-spinner — increment/decrement a numeric spinner
- use-autocomplete, use-autocomplete-nodelay — type into an autocomplete field and select a suggestion
- scroll-text, scroll-text-2 — scroll through text to find information

## Workflow

1. **Read the instruction to understand the target value**
   - Tool: `get_instruction`
   - Example: `get_instruction()` → see the target slider value, color, or spinner number
   - Purpose: Know exactly what value to set

2. **Observe the current state of the widget**
   - Tool: `get_observation`, `get_dom_elements`
   - Example: `get_observation()` → see current value; `get_dom_elements()` → find widget element refs
   - Purpose: Map the widget controls to EGTS refs

3. **For sliders: click at the correct position or use drag**
   - Tool: `click_element` or `drag_element`
   - Example: Click at specific x,y positions to set the slider
   - Purpose: Move the slider to the target value

4. **For colorwheels: click at the correct color position**
   - Tool: `click_element`
   - Example: Find the element with the target color position and click it
   - Purpose: Select the matching color

5. **For autocomplete: type and select**
   - Tool: `type_text` then `click_element`
   - Example: `type_text(ref=2, text="por")` → wait → `get_dom_elements()` to see suggestions → `click_element(ref=5)`
   - Purpose: Trigger and select from autocomplete suggestions

6. **For spinners: click increment/decrement buttons**
   - Tool: `click_element`
   - Example: Repeatedly click the up-arrow button until the target value is reached
   - Purpose: Reach the target number

7. **For scroll-text: scroll and read**
   - Tool: `scroll_page`
   - Example: `scroll_page(direction="down", amount=200)` → `get_observation()` to read revealed text
   - Purpose: Find specific information in long scrollable text

8. **Verify the final value**
   - Tool: `get_observation` or `get_fields`
   - Example: Check the widget now shows the target value
   - Purpose: Confirm success

## Tools Involved
- `get_instruction` — target value
- `get_observation` — widget state
- `get_dom_elements` — find control refs
- `click_element` — interact with widget controls
- `type_text` — autocomplete input
- `scroll_page` — scroll to reveal content
- `drag_element` — slider/colorwheel manipulation

## Tips
- Sliders may need multiple interactions to reach the exact value
- For autocomplete: type a partial string, then wait for suggestions to appear before querying `get_dom_elements`
- Colorwheels: the target color name in the instruction matches a specific color on the wheel
- Spinners: count the clicks needed by calculating the difference between current and target values
- Scroll-text tasks: the answer is typically in the text revealed by scrolling
