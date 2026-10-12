# Dropdown Menu and Tab Navigation

## Description
Navigate hierarchical UI elements including dropdown menus, tab panels, collapsible sections, tree views, and selection lists. These MiniWoB++ tasks require finding and activating the correct navigation path through nested UI components.

## Use Cases
- click-menu, click-menu-2 — navigate dropdown menus to find the right item
- click-tab, click-tab-2, click-tab-2-easy/medium/hard — switch between tab panels
- click-collapsible, click-collapsible-2 — expand/collapse sections
- click-collapsible-nodelay, click-collapsible-2-nodelay — instant expand/collapse
- navigate-tree — traverse a directory tree to find a target
- choose-list — select an item from a list

## Workflow

1. **Understand the navigation goal**
   - Tool: `get_instruction`
   - Example: `get_instruction()` → see which menu item or tab to navigate to
   - Purpose: Know the target path through the UI hierarchy

2. **Observe the current UI state**
   - Tool: `get_observation`
   - Example: `get_observation()` → see visible menu items, tab labels, tree nodes
   - Purpose: Understand what's currently visible

3. **Get interactive elements with positions**
   - Tool: `get_dom_elements`
   - Example: `get_dom_elements()` → see all clickable elements with their refs, text, and positions
   - Purpose: Plan the navigation sequence

4. **Click through the hierarchy step by step**
   - Tool: `click_element`
   - Example: `click_element(ref=5)` — expand a menu; then `get_dom_elements()` to see new items
   - Purpose: Navigate to the target

5. **Scroll if needed** for long menus or trees
   - Tool: `scroll_page`
   - Example: `scroll_page(direction="down", amount=200)` → reveal more items
   - Purpose: Access items below the fold

6. **Select the final target**
   - Tool: `click_element`
   - Example: `click_element(ref=12)` — select the target menu item or tab
   - Purpose: Complete the navigation

7. **Verify the result**
   - Tool: `get_observation`
   - Example: `get_observation()` → confirm the correct item was selected
   - Purpose: Ensure success

## Tools Involved
- `get_instruction` — navigation goal
- `get_observation` — current UI state
- `get_dom_elements` — element refs and positions
- `click_element` — navigate through hierarchy
- `scroll_page` — reveal hidden items

## Tips
- Always re-query `get_dom_elements()` after each click — menus/tabs reveal new elements dynamically
- Menu items may only appear after their parent is expanded
- For nested navigation, build the path incrementally: expand → observe → expand → observe → select
- Tab panels: clicking a tab reveals its content, other tabs stay accessible
- Tree navigation: each level may require a separate click-and-observe cycle
