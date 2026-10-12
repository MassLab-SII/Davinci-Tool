# Drag and Drop Manipulation

## Description
Drag items between containers, sort items by dragging, reorder lists, and reposition elements on the page. These MiniWoB++ tasks simulate real-world drag-and-drop interfaces for organizing, sorting, and transferring items.

## Use Cases
- drag-box — drag a box to a target position
- drag-circle — drag a circle onto a target
- drag-cube — manipulate 3D-ish cube controls
- drag-items, drag-items-grid — drag items between containers or grid cells
- drag-shapes, drag-shapes-2 — drag shapes to targets
- drag-single-shape — drag one shape to its destination
- drag-sort-numbers — reorder numbers by dragging
- moving-items — move items between lists

## Workflow

1. **Read the instruction**
   - Tool: `get_instruction`
   - Example: `get_instruction()` → understand what to drag and where to drop
   - Purpose: Know the source and target criteria

2. **Observe the page and identify draggable elements**
   - Tool: `get_observation`, `get_dom_elements`
   - Example: `get_observation()` → see the layout; `get_dom_elements()` → get refs for all elements
   - Purpose: Map each draggable item and drop target to EGTS refs

3. **Identify source and target refs**
   - Tool: `get_dom_elements`
   - Example: Look through the elements list to find the EGTS ref of the source item and target zone
   - Purpose: Get the exact ref numbers for the drag operation

4. **Execute the drag**
   - Tool: `drag_element`
   - Example: `drag_element(from_ref=3, to_ref=7)` — drag item with ref 3 to the element with ref 7
   - Purpose: Move the item

5. **Verify the result**
   - Tool: `get_observation`
   - Example: `get_observation()` → confirm the item moved correctly
   - Purpose: Check that the drag had the expected effect

6. **Repeat for multi-item drags**
   - Tool: `drag_element` for each remaining item
   - Purpose: Complete all required drag operations

## Tools Involved
- `get_instruction` — task goal
- `get_observation` — page layout and state
- `get_dom_elements` — find source and target refs
- `drag_element` — execute drag operations
- `click_element` — used as fallback for click-to-select interactions

## Tips
- Always get fresh `get_dom_elements()` before each drag — element positions and refs may change after movement
- For sort tasks: identify the correct order first, then execute drags one at a time
- The target element should be the drop zone/container, not another draggable item
- Drag operations may not work on all MiniWoB++ tasks (some use their own drag implementations)
- If drag doesn't trigger page change, fall back to `click_element` for selection-based tasks
- Some tasks expect items dragged to specific coordinates rather than onto another element
