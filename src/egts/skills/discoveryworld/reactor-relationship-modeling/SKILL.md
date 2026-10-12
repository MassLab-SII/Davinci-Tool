# Reactor Relationship Modeling

## Description

Configure nuclear reactor parameters and measure outputs using multiple scientific instruments (spectrometer, density meter, pH meter, and others). Collect data points across different reactor settings, perform curve-fitting to discover mathematical relationships between variables (linear, polynomial, quadratic), and predict reactor behavior under new conditions.

## Use Cases

- Model a linear relationship between 3 reactor parameters with 1 instrument
- Discover mathematical relationships between 4 reactor variables using 5 instruments
- Fit a quadratic curve to 5 reactor variables with noisy instrument readings
- Collect systematic data points by varying reactor control settings
- Predict reactor output for an untested configuration
- Validate mathematical model by testing predictions

## Workflow

### Step 1: Read the experimental objective
- **Tool**: `get_task_description`
- **Example**: `get_task_description({})`
- **Purpose**: Understand how many reactors to model, what instruments are available, and what type of relationship to find (linear, quadratic, etc.).

### Step 2: Survey the reactor lab
- **Tool**: `look_around`
- **Example**: `look_around({})`
- **Purpose**: Identify all accessible objects — reactor control panels, measurement instruments (spectrometer, density meter, pH meter, etc.), and data logging stations. Note all UUIDs.

### Step 3: Collect all measurement instruments
- **Tool**: `pick_up_object` / `open_object`
- **Examples**:
  - `open_object({"object_uuid": "<instrument_cabinet_uuid>"})` — open storage
  - `pick_up_object({"object_uuid": "<spectrometer_uuid>"})` — take spectrometer
  - `pick_up_object({"object_uuid": "<density_meter_uuid>"})` — take density meter
  - `pick_up_object({"object_uuid": "<ph_meter_uuid>"})` — take pH meter
- **Purpose**: Gather all available instruments. Different instruments measure different reactor parameters — you need all of them for complete modeling.

### Step 4: Activate the reactor
- **Tool**: `activate_device`
- **Example**: `activate_device({"device_uuid": "<reactor_control_uuid>"})`
- **Purpose**: Turn on the reactor so it can be configured and measured. An inactive reactor gives no readings.

### Step 5: Configure reactor parameter and measure
- **Tool**: `put_object` (configure) then `use_object_on_object` (measure)
- **Examples**:
  - `put_object({"object_uuid": "<control_rod_uuid>", "target_uuid": "<reactor_uuid>"})` — set a parameter
  - `use_object_on_object({"object_uuid": "<spectrometer_uuid>", "target_uuid": "<reactor_uuid>"})` — measure
- **Purpose**: Set one reactor parameter to a specific value, then measure the output with each instrument. Record the data point.

### Step 6: Vary the parameter and measure again
- **Tool**: `put_object` (change setting) → `use_object_on_object` (measure)
- **Example**: Change the control rod position to a different setting, then measure again with all instruments.
- **Purpose**: Collect multiple data points across a range of parameter values. For linear relationships, 3-5 points suffice. For quadratic, you need at least 5-6 points.

### Step 7: Measure with each instrument at each setting
- **Tool**: `use_object_on_object` (repeat with each instrument)
- **Examples**:
  - `use_object_on_object({"object_uuid": "<spectrometer_uuid>", "target_uuid": "<reactor_uuid>"})`
  - `use_object_on_object({"object_uuid": "<density_meter_uuid>", "target_uuid": "<reactor_uuid>"})`
  - `use_object_on_object({"object_uuid": "<ph_meter_uuid>", "target_uuid": "<reactor_uuid>"})`
- **Purpose**: At each reactor setting, take readings with every available instrument. Cross-referencing multiple instruments reveals the underlying relationship.

### Step 8: Analyze the data pattern
- **Tool**: `look_around` / `get_discovery_feed`
- **Example**: `look_around({})`
- **Purpose**: Review the collected data. Is there a linear trend? A quadratic curve? An inverse relationship? Identify the mathematical pattern.

### Step 9: Fit the mathematical model
- **Tool**: `read_object` (check reference) / `look_around` (review data)
- **Example**: `read_object({"object_uuid": "<lab_notebook_uuid>"})`
- **Purpose**: Reference materials may describe the expected relationship form. Use the data to determine coefficients.

### Step 10: Validate with a prediction
- **Tool**: `put_object` → `use_object_on_object`
- **Example**: Set the reactor to a previously untested configuration and measure to see if the output matches your model's prediction.
- **Purpose**: Test your mathematical model by making a prediction and verifying it experimentally.

### Step 11: Report the discovered relationship
- **Tool**: `put_object`
- **Example**: `put_object({"object_uuid": "<answer_formula_uuid>", "target_uuid": "<report_station_uuid>"})`
- **Purpose**: Submit the mathematical relationship you've discovered (e.g., "output = 2.3 * input + 1.7" or the quadratic coefficients).

## Tools Involved

`look_around`, `check_inventory`, `get_task_description`, `list_teleport_locations`, `get_discovery_feed`, `move`, `rotate`, `teleport_to_location`, `pick_up_object`, `drop_object`, `put_object`, `open_object`, `close_object`, `activate_device`, `deactivate_device`, `use_object_on_object`, `read_object`

## Tips

- Collect all instruments first — you cannot carry too many, but you need at least the key ones for each measurement round.
- Systematic data collection is critical — vary one parameter at a time while keeping others constant.
- Record instrument readings mentally — the relationship emerges from the pattern across data points, not from a single measurement.
- For quadratic relationships, you need data points that span the curve — include low, medium, and high parameter settings.
- Noisy readings are normal — take multiple measurements at the same setting and look at the trend, not individual values.
- Deactivate the reactor between experiments to reset conditions if readings seem inconsistent.
- Reference materials (lab notebook, manual) may provide the expected equation form — read them before fitting.
- A graph in your mind helps: plot the parameter setting on one axis and the measurement on the other to visualize the relationship.
