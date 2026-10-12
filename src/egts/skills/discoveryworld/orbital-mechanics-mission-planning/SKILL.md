# Orbital Mechanics Mission Planning

## Description

Use physics instruments (velocimeter, pendulum, load cell) to measure planetary parameters (mass, gravity) and fuel characteristics, read reference materials for orbital mechanics formulas, calculate the correct orbit and fuel requirements for interplanetary missions, and validate calculations against instrument readings. Advanced scenarios involve choosing the optimal fuel type from multiple options.

## Use Cases

- Plan an orbital mission to a fixed planet with known fuel amount
- Calculate orbit and fuel requirements for a randomly selected target planet
- Choose the optimal fuel type from multiple options and calculate precise orbital parameters
- Measure planetary mass using a pendulum
- Measure fuel thrust using a load cell
- Measure exhaust velocity using a velocimeter
- Apply orbital mechanics formulas from reference materials
- Calculate delta-v requirements and fuel mass ratios

## Workflow

### Step 1: Read the mission objective
- **Tool**: `get_task_description`
- **Example**: `get_task_description({})`
- **Purpose**: Understand the mission — what is the target planet, what fuel is available, and what parameters need to be calculated.

### Step 2: Survey the mission control center
- **Tool**: `look_around`
- **Example**: `look_around({})`
- **Purpose**: Identify all accessible objects — velocimeter, pendulum, load cell, fuel tanks, reference books, rocket components. Note UUIDs.

### Step 3: Collect all measurement instruments
- **Tool**: `pick_up_object` / `open_object`
- **Examples**:
  - `open_object({"object_uuid": "<equipment_locker_uuid>"})` — open storage
  - `pick_up_object({"object_uuid": "<velocimeter_uuid>"})` — take velocimeter
  - `pick_up_object({"object_uuid": "<pendulum_uuid>"})` — take pendulum
  - `pick_up_object({"object_uuid": "<load_cell_uuid>"})` — take load cell
- **Purpose**: Gather all physics instruments. Each measures a different parameter needed for the calculation.

### Step 4: Read the orbital mechanics reference
- **Tool**: `read_object`
- **Example**: `read_object({"object_uuid": "<orbital_mechanics_textbook_uuid>"})`
- **Purpose**: Read the reference materials to learn the required formulas. The rocket equation (delta-v = ve * ln(m0/mf)) is fundamental. The reference will tell you what parameters to measure and how to combine them.

### Step 5: Measure exhaust velocity with velocimeter
- **Tool**: `use_object_on_object`
- **Example**: `use_object_on_object({"object_uuid": "<velocimeter_uuid>", "target_uuid": "<fuel_tank_uuid>"})`
- **Purpose**: Measure the exhaust velocity (ve) of the fuel. This is a key parameter in the rocket equation.

### Step 6: Measure fuel mass with load cell
- **Tool**: `use_object_on_object`
- **Example**: `use_object_on_object({"object_uuid": "<load_cell_uuid>", "target_uuid": "<fuel_tank_uuid>"})`
- **Purpose**: Measure the mass of the available fuel (mf). Combined with the rocket's dry mass, this determines your mass ratio.

### Step 7: Measure planetary gravity with pendulum
- **Tool**: `use_object_on_object`
- **Example**: `use_object_on_object({"object_uuid": "<pendulum_uuid>", "target_uuid": "<planet_model_uuid>"})`
- **Purpose**: Measure the gravitational parameter of the target planet. The pendulum period relates to local gravity, which affects orbital requirements.

### Step 8: Collect any additional measurements
- **Tool**: `use_object_on_object` / `activate_device`
- **Examples**:
  - `activate_device({"device_uuid": "<mission_computer_uuid>"})` — power up the computer
  - `use_object_on_object({"object_uuid": "<sensor_uuid>", "target_uuid": "<rocket_uuid>"})` — additional measurement
- **Purpose**: Some missions require additional measurements. Check the reference material for the complete list.

### Step 9: Review all measurements
- **Tool**: `look_around` / `check_inventory`
- **Example**: `look_around({})`
- **Purpose**: Verify you have all required measurements. Compare against the formula in the reference material.

### Step 10: Calculate the orbital parameters
- **Tool**: `read_object` (re-check formulas)
- **Example**: `read_object({"object_uuid": "<orbital_mechanics_textbook_uuid>"})`
- **Purpose**: Apply the formulas using your measurements. Calculate delta-v, check if it's sufficient, determine the transfer orbit.

### Step 11: For fuel selection scenarios, test multiple fuels
- **Tool**: `use_object_on_object` (repeat for each fuel type)
- **Examples**:
  - `use_object_on_object({"object_uuid": "<velocimeter_uuid>", "target_uuid": "<fuel_a_uuid>"})` — measure fuel A
  - `use_object_on_object({"object_uuid": "<load_cell_uuid>", "target_uuid": "<fuel_b_uuid>"})` — measure fuel B
- **Purpose**: If multiple fuel types are available, measure each one. Compare their characteristics to choose the optimal fuel.

### Step 12: Submit the mission plan
- **Tool**: `put_object` / `use_object_on_object`
- **Example**: `put_object({"object_uuid": "<mission_plan_uuid>", "target_uuid": "<launch_console_uuid>"})`
- **Purpose**: Deliver the calculated orbital parameters or selected fuel type. The mission system verifies your calculations.

## Tools Involved

`look_around`, `check_inventory`, `get_task_description`, `list_teleport_locations`, `get_discovery_feed`, `move`, `rotate`, `teleport_to_location`, `pick_up_object`, `drop_object`, `put_object`, `open_object`, `activate_device`, `deactivate_device`, `use_object_on_object`, `read_object`

## Tips

- Read the reference material FIRST — it tells you exactly which measurements to take and the formulas to use.
- The rocket equation is the core formula: delta-v = ve * ln(m0/mf), where ve is exhaust velocity, m0 is initial mass, mf is final mass.
- Each instrument measures a different physical quantity — the velocimeter measures velocity, the load cell measures force/mass, the pendulum measures gravity.
- Take each measurement carefully — instrument readings are the input to your calculation, so accuracy matters.
- For fuel selection, compare ve (efficiency) and mass (total impulse) across all fuel options — the best fuel maximizes delta-v.
- Planetary gravity determines the required delta-v for orbit — heavier planets need more delta-v.
- If your calculated fuel is insufficient, you may need to choose a different fuel or recalculate.
- Reference materials may be books, computer screens, or data terminals — check the environment thoroughly.
- The mission computer may need to be activated before it displays information.
