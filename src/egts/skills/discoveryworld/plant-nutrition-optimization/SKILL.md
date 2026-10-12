# Plant Nutrition Optimization

## Description

Plant seeds in soil, apply varying levels of NPK (Nitrogen, Phosphorus, Potassium) nutrients, activate grow lights to provide light energy, and wait for multiple growth cycles to complete. Measure plant growth outcomes with NPK meters, compare results across different nutrient combinations, and discover the optimal formula for maximum plant yield. Advanced scenarios involve Boolean nutrient interaction rules.

## Use Cases

- Test whether a single nutrient (N, P, or K) affects plant growth (binary presence/absence)
- Experiment with 3 levels of nutrient concentration to find the optimal concentration
- Discover Boolean nutrient interaction rules (e.g., N helps only when P is present)
- Measure soil nutrient levels with NPK meter before and after growth
- Grow plants from seed through full growth cycle
- Optimize plant yield through systematic factorial experiments

## Workflow

### Step 1: Read the experimental objective
- **Tool**: `get_task_description`
- **Example**: `get_task_description({})`
- **Purpose**: Understand what nutrients to test, how many levels to try, and what the success criteria are.

### Step 2: Survey the greenhouse
- **Tool**: `look_around`
- **Example**: `look_around({})`
- **Purpose**: Identify all accessible objects — soil, seeds, NPK nutrient dispensers, grow lights, pots, NPK meter. Note UUIDs.

### Step 3: Collect planting materials
- **Tool**: `pick_up_object` / `open_object`
- **Examples**:
  - `open_object({"object_uuid": "<storage_uuid>"})` — open seed storage
  - `pick_up_object({"object_uuid": "<seeds_uuid>"})` — take seeds
  - `pick_up_object({"object_uuid": "<soil_uuid>"})` — take soil
- **Purpose**: Gather seeds and soil — the basic materials needed for planting.

### Step 4: Prepare the planting pot
- **Tool**: `put_object`
- **Example**: `put_object({"object_uuid": "<soil_uuid>", "target_uuid": "<pot_uuid>"})`
- **Purpose**: Place soil into a planting pot to create a growing medium.

### Step 5: Plant the seeds
- **Tool**: `put_object`
- **Example**: `put_object({"object_uuid": "<seeds_uuid>", "target_uuid": "<pot_uuid>"})`
- **Purpose**: Place seeds into the prepared pot with soil.

### Step 6: Apply nutrients to the planted pot
- **Tool**: `use_object_on_object` / `put_object`
- **Examples**:
  - `use_object_on_object({"object_uuid": "<nitrogen_dispenser_uuid>", "target_uuid": "<pot_uuid>"})` — add nitrogen
  - `put_object({"object_uuid": "<fertilizer_uuid>", "target_uuid": "<pot_uuid>"})` — add solid fertilizer
- **Purpose**: Apply the specific nutrient combination you want to test. For systematic experiments, vary only one nutrient at a time.

### Step 7: Activate the grow light
- **Tool**: `activate_device`
- **Example**: `activate_device({"device_uuid": "<grow_light_uuid>"})`
- **Purpose**: Turn on the light source — plants need light to grow. Without it, no growth will occur.

### Step 8: Wait for growth cycles
- **Tool**: `move` (any action that advances the world)
- **Example**: `move({"direction": "north"})` — each step advances the simulation
- **Purpose**: Plants grow over multiple world steps. Each action advances the simulation by one tick. Use navigation or wait actions to let time pass.

### Step 9: Check growth progress
- **Tool**: `look_around`
- **Example**: `look_around({})`
- **Purpose**: After several steps, check if the plant has grown. The observation will describe the plant's current stage.

### Step 10: Measure plant health with NPK meter
- **Tool**: `pick_up_object` then `use_object_on_object`
- **Examples**:
  - `pick_up_object({"object_uuid": "<npk_meter_uuid>"})` — take the NPK meter
  - `use_object_on_object({"object_uuid": "<npk_meter_uuid>", "target_uuid": "<plant_uuid>"})` — measure
- **Purpose**: Take a quantitative measurement of the plant's nutrient levels and health.

### Step 11: Iterate with different nutrient combinations
- **Tool**: `put_object` (new seeds + soil) → apply different nutrients → grow → measure
- **Purpose**: Systematically test different nutrient levels. For binary experiments, test with and without each nutrient. For factorial experiments, test all combinations.

### Step 12: Report the optimal formula
- **Tool**: `put_object`
- **Example**: `put_object({"object_uuid": "<result_formula_uuid>", "target_uuid": "<report_station_uuid>"})`
- **Purpose**: Once you've determined the optimal nutrient combination, deliver your findings.

## Tools Involved

`look_around`, `check_inventory`, `get_task_description`, `list_teleport_locations`, `get_discovery_feed`, `move`, `rotate`, `teleport_to_location`, `pick_up_object`, `drop_object`, `put_object`, `open_object`, `activate_device`, `deactivate_device`, `use_object_on_object`, `read_object`, `eat_food`

## Tips

- Growth takes multiple steps — plan to wait at least 5-10 steps between planting and measuring.
- Change only one variable at a time — if testing nitrogen, keep phosphorus and potassium constant.
- Take baseline measurements — measure soil nutrient levels BEFORE planting to know the starting state.
- The NPK meter must be in your inventory to use it on a plant.
- Deactivate grow lights between experiments to reset conditions.
- For Boolean interaction rules, you need a full factorial design (all combinations of nutrient presence/absence).
- Plants may die if nutrient levels are too high — toxicity is a real phenomenon in the simulation.
- Use a fresh pot for each experiment — residual nutrients from previous tests can contaminate results.
