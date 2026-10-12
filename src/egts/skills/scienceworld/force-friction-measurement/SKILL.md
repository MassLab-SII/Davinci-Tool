# Force and Friction Measurement

## Description

Set up inclined planes and measure friction coefficients for different surfaces — adjust the plane angle, observe when objects begin to slide, determine critical angles, and compare frictional properties across named and unknown surfaces through systematic visual observation of the physical apparatus. This is the core mechanics workflow covering all three Forces benchmark tasks: determine the angle of an inclined plane, measure friction of known surfaces, and measure friction of unknown surfaces.

## Use Cases

- Determine the angle of an inclined plane by observing block motion at different settings
- Measure the friction coefficient of a named surface (e.g., wood, metal, rubber)
- Measure the friction coefficient of an unknown surface and identify it by comparison
- Compare frictional properties of multiple surfaces in a single experiment
- Conduct systematic angle-adjustment experiments to find the threshold where an object begins to slide

## Workflow

### Step 1: Read the experimental objective
- **Tool**: `get_task_description`
- **Example**: `get_task_description({})`
- **Purpose**: Determine what you need to measure — an inclined plane angle, friction coefficient of a named surface, or friction coefficient of an unknown surface for identification.

### Step 2: Survey the workspace
- **Tool**: `look_around`
- **Example**: `look_around({})`
- **Purpose**: Identify the inclined plane apparatus, blocks or objects to place on it, surface materials, and any measurement instruments. Note the plane's current orientation and available adjustments.

### Step 3: Navigate to the room with the inclined plane
- **Tool**: `open_object` / `go_to_location`
- **Examples**:
  - `open_object({"object": "door to workshop"})`
  - `go_to_location({"location": "workshop"})`
- **Purpose**: The inclined plane apparatus is typically in the workshop or lab. Open any closed doors to access the equipment.

### Step 4: Inspect the inclined plane apparatus in detail
- **Tool**: `look_at_object`
- **Example**: `look_at_object({"object": "inclined plane"})`
- **Purpose**: Understand the plane's current angle, the surface material attached to it, and any blocks or objects available. The detailed description reveals the current angle reading and surface properties.

### Step 5: Gather test objects and surface materials
- **Tool**: `pick_up_object`
- **Examples**:
  - `pick_up_object({"object": "wooden block"})` — the test object to place on the plane
  - `pick_up_object({"object": "metal surface"})` — a surface material to attach to the plane
  - `pick_up_object({"object": "unknown surface"})` — an unidentified surface to test
- **Purpose**: Collect the blocks and surface samples needed for the experiment. For angle determination you need a block; for friction measurement you also need the surface to test.

### Step 6: Place the test object on the inclined plane
- **Tool**: `move_object_to_container`
- **Example**: `move_object_to_container({"object": "wooden block", "container": "inclined plane"})`
- **Purpose**: Position the object on the plane so you can observe its behavior at different angles. The object must be on the plane for the apparatus to function.

### Step 7: Attach or change the surface on the plane (for friction tasks)
- **Tool**: `move_object_to_container`
- **Example**: `move_object_to_container({"object": "metal surface", "container": "inclined plane"})`
- **Purpose**: Replace or attach the surface being tested. Different surfaces produce different friction coefficients — this is the key experimental variable.

### Step 8: Activate the inclined plane mechanism
- **Tool**: `activate_device`
- **Example**: `activate_device({"device": "inclined plane"})`
- **Purpose**: Start the plane's angle adjustment mechanism. This may raise or lower the plane to a new angle setting.

### Step 9: Observe the result at the current angle
- **Tool**: `look_at_object`
- **Example**: `look_at_object({"object": "inclined plane"})`
- **Purpose**: Check the current angle and whether the block is sliding or stationary. This is the core observation — you must take repeated readings to find the critical angle where motion begins.

### Step 10: Adjust the plane to a different angle
- **Tool**: `activate_device` / `deactivate_device`
- **Examples**:
  - `activate_device({"device": "inclined plane"})` — raise the angle further
  - `deactivate_device({"device": "inclined plane"})` — stop or lower the plane
- **Purpose**: Iteratively change the angle to bracket the threshold where the block transitions from static to sliding. Find the exact angle where motion begins.

### Step 11: Wait briefly between observations
- **Tool**: `wait_time`
- **Example**: `wait_time({"seconds": 1})`
- **Purpose**: Allow the apparatus to settle after each angle adjustment before taking the next observation.

### Step 12: Repeat the observation cycle for each surface or object
- **Tool**: `look_at_object` × repeated
- **Example**: `look_at_object({"object": "inclined plane"})`
- **Purpose**: For friction tasks with multiple surfaces, repeat Steps 7-11 for each surface material. For angle determination, repeat Steps 8-10 across a range of angles. The systematic observation cycle is the core experimental method — you may need 30-160+ `look_at_object` calls across the full experiment.

### Step 13: For unknown surfaces, compare against known values
- **Tool**: `look_at_object`
- **Example**: `look_at_object({"object": "inclined plane"})`
- **Purpose**: When measuring friction of an unknown surface, compare the observed critical angle against the known angles for named surfaces. The surface whose critical angle most closely matches the unknown is your identification.

### Step 14: Report your measurement result
- **Tool**: `focus_on_object`
- **Example**: `focus_on_object({"object": "inclined plane"})`
- **Purpose**: Designate the apparatus, the surface, or the measured result as your answer. The task system verifies you found the correct angle, friction coefficient, or surface identification.

## Tools Involved

`look_around`, `look_at_object`, `look_in_container`, `check_inventory`, `get_task_description`, `go_to_location`, `open_object`, `pick_up_object`, `put_down_object`, `move_object_to_container`, `activate_device`, `deactivate_device`, `use_object_on_object`, `wait_time`, `focus_on_object`

## Tips

- `look_at_object` on the inclined plane is your primary observation tool — each call reveals the current angle and block motion state. Expect to call it 30-160+ times per task.
- The inclined plane must be explicitly activated between angle changes — each `activate_device` call typically increases the angle by one increment.
- Friction experiments are systematic and repetitive: place block, adjust angle, observe, record threshold, repeat for each surface. Do not skip the observation step after each angle change.
- For unknown surface identification, test all known surfaces first to establish reference critical angles, then test the unknown and compare.
- Different block materials (wood, metal, rubber) on the same surface produce different friction coefficients — the task may vary both block and surface.
- The plane may need to be deactivated and reactivated to reset its angle for a new test run — `deactivate_device` typically returns the plane to a lower starting position.
- Surface materials may be loose in the room, inside containers, or already attached to the plane — check all three locations with `look_around` and `look_in_container`.
- If a block slides off the plane, pick it up again and replace it before continuing — the apparatus requires a test object to be present.
- These are the longest-running tasks in ScienceWorld (up to 164 gold steps for friction tasks) — patience and systematic methodology are essential.
