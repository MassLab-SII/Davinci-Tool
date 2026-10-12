# Electrical Circuit Experiments

## Description

Build complete electrical circuits by connecting batteries, wires, and components (light bulbs, motors); test the electrical conductivity of known and unknown materials by swapping them into the circuit path; and compare renewable versus non-renewable power sources. This is the core electricity and electronics workflow covering all four Electricity benchmark tasks.

## Use Cases

- Power a light bulb or component using a standard battery with connecting wires
- Power a component using a renewable energy source (solar panel, wind turbine) versus a non-renewable source
- Test whether named materials (e.g., aluminum foil, copper wire) are electrical conductors or insulators
- Test the conductivity of unknown substances and classify them as conductive or non-conductive
- Build circuits with multiple components and verify each functions

## Workflow

### Step 1: Read the circuit objective
- **Tool**: `get_task_description`
- **Example**: `get_task_description({})`
- **Purpose**: Determine whether you need to power a component, test conductivity of materials, or compare power sources.

### Step 2: Explore the workspace
- **Tool**: `look_around`
- **Example**: `look_around({})`
- **Purpose**: Find all available electrical components — batteries, wires (black, blue, orange), light bulbs (red, violet, yellow), solar panels, generators, motors, and materials to test for conductivity.

### Step 3: Navigate to the room with electrical equipment
- **Tool**: `go_to_location` / `open_object`
- **Examples**:
  - `open_object({"object": "door to workshop"})`
  - `go_to_location({"location": "workshop"})`
- **Purpose**: The workshop typically contains batteries, wires, and components on a workbench. You may also find components in the lab or living room.

### Step 4: Gather the circuit components
- **Tool**: `pick_up_object`
- **Examples**:
  - `pick_up_object({"object": "battery"})` — take the power source
  - `pick_up_object({"object": "black wire"})` — take a connecting wire
  - `pick_up_object({"object": "red light bulb"})` — take the component to power
- **Purpose**: A basic circuit requires at minimum: one power source, two wires, and one component. For conductivity testing, also pick up the material samples to test.

### Step 5: Connect the power source to the first wire
- **Tool**: `connect_objects`
- **Example**: `connect_objects({"object1": "battery", "object2": "black wire"})`
- **Purpose**: Establish the first electrical connection from the power source to a conductor.

### Step 6: Connect the wire to the target component
- **Tool**: `connect_objects`
- **Example**: `connect_objects({"object1": "black wire", "object2": "red light bulb"})`
- **Purpose**: Link the wire to the component you want to power.

### Step 7: Complete the circuit loop with the second wire
- **Tool**: `connect_objects`
- **Example**: `connect_objects({"object1": "red light bulb", "object2": "battery"})`
- **Purpose**: Close the circuit by creating a return path from the component back to the power source. A circuit must form a complete loop to function.

### Step 8: Verify the circuit works
- **Tool**: `look_around` / `look_at_object`
- **Examples**:
  - `look_around({})` — check if the room description shows the component is lit/powered
  - `look_at_object({"object": "red light bulb"})` — examine the component state
- **Purpose**: Confirm the circuit is complete and the component is receiving power.

### Step 9: For conductivity testing, swap in test materials
- **Tool**: `disconnect_object` / `connect_objects`
- **Examples**:
  - `disconnect_object({"object": "black wire"})` — remove one wire
  - `pick_up_object({"object": "aluminum foil"})` — take the material to test
  - `connect_objects({"object1": "battery", "object2": "aluminum foil"})` — insert test material
  - `connect_objects({"object1": "aluminum foil", "object2": "red light bulb"})` — complete circuit through material
- **Purpose**: Replace a wire in the circuit with the material being tested. If the component powers on, the material is conductive; if not, it is an insulator.

### Step 10: Report the result
- **Tool**: `focus_on_object`
- **Example**: `focus_on_object({"object": "aluminum foil"})`
- **Purpose**: Designate the powered component or the identified conductor/insulator as your answer.

## Tools Involved

`look_around`, `look_at_object`, `look_in_container`, `check_inventory`, `get_task_description`, `go_to_location`, `open_object`, `pick_up_object`, `put_down_object`, `connect_objects`, `disconnect_object`, `activate_device`, `deactivate_device`, `use_object_on_object`, `focus_on_object`

## Tips

- The workshop is the primary location for electrical components — check there first.
- You need exactly TWO wires to build a basic circuit loop — one from battery to component, one from component back to battery.
- For renewable energy tasks, look for a "solar panel" or "wind turbine" to use as the power source instead of a battery.
- When testing multiple materials, disconnect the previous test material before inserting the next one. You cannot connect two materials to the same terminal simultaneously.
- Wires come in different colors (black, blue, orange) — they are functionally identical but named differently. Pick whichever is available.
- `connect_objects` requires both objects to be in your inventory or in the current room.
- A successfully powered component will show a change in `look_around` description — the light bulb will be described as lit, the motor as spinning.
