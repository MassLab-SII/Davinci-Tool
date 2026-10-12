# Thermodynamic Phase Transitions

## Description

Heat or cool substances to trigger phase transitions (melt ice, boil water, freeze liquid), then measure temperature with a thermometer to determine melting points or boiling points of known and unknown substances. This is the core thermodynamics workflow that unifies Matter and Measurement benchmark tasks — you cannot measure a phase transition without controlling heat, and you cannot verify a state change without measuring temperature.

## Use Cases

- Boil water or other liquid by heating on a stove until it reaches its boiling point
- Melt ice or frozen substances by applying heat and monitoring the phase transition
- Freeze water by placing it in a freezer or cooling device
- Change the state of matter of a named substance to a target state
- Use a thermometer to measure the temperature of a specific substance
- Determine the melting point of a known substance (e.g., ice, wax, metal)
- Measure the melting point of an unknown substance to identify it

## Workflow

### Step 1: Read the experimental objective
- **Tool**: `get_task_description`
- **Example**: `get_task_description({})`
- **Purpose**: Understand what substance to work with, what state change or measurement is required, and what the target outcome is.

### Step 2: Survey the starting environment
- **Tool**: `look_around`
- **Example**: `look_around({})`
- **Purpose**: Identify all visible objects — heat sources (stove, burner), cooling devices (freezer), containers (beaker, pot, metal pot), the target substance, and any measurement tools.

### Step 3: Locate and collect the target substance
- **Tool**: `look_in_container` / `open_object` / `pick_up_object`
- **Examples**:
  - `look_in_container({"container": "fridge"})` — find cold substances
  - `open_object({"object": "cupboard"})` — access stored containers
  - `pick_up_object({"object": "beaker"})` — take the container holding the substance
- **Purpose**: The substance may be in a container, on a counter, or inside an appliance. Open closed containers first, then pick up what you need.

### Step 4: Move to the room with the thermal apparatus
- **Tool**: `go_to_location` / `open_object`
- **Examples**:
  - `open_object({"object": "door to kitchen"})`
  - `go_to_location({"location": "kitchen"})`
- **Purpose**: Stoves and burners are typically in the kitchen. Freezers may be in the kitchen or lab. Doors between rooms must be opened before you can pass through.

### Step 5: Place the substance on or in the thermal device
- **Tool**: `move_object_to_container` / `pour_object_into_container`
- **Examples**:
  - `move_object_to_container({"object": "beaker", "container": "stove"})` — place container on stove
  - `pour_object_into_container({"object": "water", "container": "metal pot"})` — transfer liquid to a heat-safe container
- **Purpose**: The substance must be in a suitable container on the thermal device before heating or cooling can begin.

### Step 6: Activate the thermal device
- **Tool**: `activate_device`
- **Example**: `activate_device({"device": "stove"})`
- **Purpose**: Turn on the heat source to begin the state change process, or activate the freezer to start cooling.

### Step 7: Wait for the process to progress
- **Tool**: `wait_time`
- **Example**: `wait_time({"seconds": 3})`
- **Purpose**: Phase transitions take multiple time steps. Wait in increments, checking state between each wait rather than waiting too long at once.

### Step 8: Monitor temperature with a thermometer
- **Tool**: `use_object_on_object`
- **Example**: `use_object_on_object({"object": "thermometer", "target": "water"})`
- **Purpose**: Measure the current temperature. The thermometer must be in your inventory first (pick it up if you haven't already). Take readings periodically — the phase transition temperature is your key data point.

### Step 9: Examine the substance to verify the state change
- **Tool**: `look_at_object`
- **Example**: `look_at_object({"object": "water"})`
- **Purpose**: Check whether the substance has visibly changed state (liquid → gas, solid → liquid). The visual description confirms the phase transition.

### Step 10: Deactivate the device when done
- **Tool**: `deactivate_device`
- **Example**: `deactivate_device({"device": "stove"})`
- **Purpose**: Turn off the heat or cooling source. Leaving devices on wastes steps and may affect subsequent actions.

### Step 11: Report your result
- **Tool**: `focus_on_object`
- **Example**: `focus_on_object({"object": "steam"})`
- **Purpose**: Designate the transformed substance or the substance whose temperature you measured as your answer. The task system verifies the correct state change or measurement.

## Tools Involved

`look_around`, `look_at_object`, `look_in_container`, `check_inventory`, `get_task_description`, `go_to_location`, `open_object`, `pick_up_object`, `put_down_object`, `move_object_to_container`, `pour_object_into_container`, `activate_device`, `deactivate_device`, `use_object_on_object`, `wait_time`, `focus_on_object`

## Tips

- Always pick up a thermometer before starting the heating process — you cannot use it on a target unless it is in your inventory.
- Phase transitions do not happen instantly — wait 3-5 steps between each temperature check.
- Take the temperature reading WHILE the phase transition is happening (when melting/boiling begins), not after it completes — the reading is most accurate at the transition point.
- For unknown substance identification, compare the measured melting/boiling point against known values. Different substances have distinct phase transition temperatures.
- The metal pot is typically required for stove-top heating — glass beakers may not be heat-safe in the simulation.
- Water and ice are often found in the kitchen (sink, fridge) but the thermometer may be in the lab or workshop.
- If a door is closed, you must open it before `go_to_location` will succeed — the observation will tell you "The door is not open."
