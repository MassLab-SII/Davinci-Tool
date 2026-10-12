# Protein Expression Profiling

## Description

Use a proteomics meter to measure protein expression levels across multiple animals. Navigate indoor laboratory environments or outdoor field sites to locate specimens, take comparative measurements, identify outliers using statistical clustering, and analyze 2D/3D protein data patterns to characterize expression differences.

## Use Cases

- Compare protein expression across 3 animals in a controlled indoor lab
- Measure and compare protein expression across 10 animals in an outdoor field
- Analyze 3D protein expression data to identify structural patterns
- Identify which animal has significantly different protein expression (outlier detection)
- Cluster animals by their protein expression profiles
- Statistically compare expression levels between groups

## Workflow

### Step 1: Read the scientific objective
- **Tool**: `get_task_description`
- **Example**: `get_task_description({})`
- **Purpose**: Understand how many animals to measure, what environment you're in (indoor/outdoor), and what type of analysis is required.

### Step 2: Survey the environment
- **Tool**: `look_around`
- **Example**: `look_around({})`
- **Purpose**: Identify all accessible objects — proteomics meter, animals to measure, any reference materials. Note the UUIDs of animals and instruments.

### Step 3: Check for teleport locations
- **Tool**: `list_teleport_locations`
- **Example**: `list_teleport_locations({})`
- **Purpose**: In outdoor scenarios, animals may be spread across large areas. Teleport locations help you reach distant specimens quickly.

### Step 4: Locate and collect the proteomics meter
- **Tool**: `move` / `pick_up_object` / `open_object`
- **Examples**:
  - `move({"direction": "east"})` — navigate to the lab bench
  - `open_object({"object_uuid": "<cabinet_uuid>"})` — open storage
  - `pick_up_object({"object_uuid": "<proteomics_meter_uuid>"})` — take the meter
- **Purpose**: The proteomics meter is your primary measurement instrument. It must be in your inventory before you can use it.

### Step 5: Navigate to the first animal
- **Tool**: `move` / `teleport_to_location` / `teleport_to_object`
- **Examples**:
  - `move({"direction": "north"})` — walk to the animal enclosure
  - `teleport_to_object({"object_uuid": "<animal_uuid>"})` — jump directly to an animal
- **Purpose**: Reach the first specimen. In outdoor scenarios, animals may be scattered across a wide area.

### Step 6: Measure protein expression
- **Tool**: `use_object_on_object`
- **Example**: `use_object_on_object({"object_uuid": "<proteomics_meter_uuid>", "target_uuid": "<animal_uuid>"})`
- **Purpose**: Use the proteomics meter on the animal to measure its protein expression levels. Record the result.

### Step 7: Navigate to the next animal
- **Tool**: `move` / `teleport_to_object`
- **Example**: `teleport_to_object({"object_uuid": "<animal2_uuid>"})`
- **Purpose**: Move to the next specimen for measurement. For 10-animal outdoor scenarios, efficient navigation is critical.

### Step 8: Measure next animal (repeat)
- **Tool**: `use_object_on_object`
- **Example**: `use_object_on_object({"object_uuid": "<proteomics_meter_uuid>", "target_uuid": "<animal2_uuid>"})`
- **Purpose**: Take the protein expression measurement. Repeat for all animals in the study.

### Step 9: Compare measurements and identify patterns
- **Tool**: `look_around` / `get_discovery_feed`
- **Examples**:
  - `look_around({})` — check task progress and last measurements
  - `get_discovery_feed({})` — check for synthesized analysis
- **Purpose**: Review all collected measurements. Look for the animal with outlier expression levels or patterns in the data.

### Step 10: Read reference materials if available
- **Tool**: `read_object`
- **Example**: `read_object({"object_uuid": "<lab_manual_uuid>"})`
- **Purpose**: Reference materials may provide expected expression ranges or help interpret 2D/3D data visualizations.

### Step 11: Report the outlier or pattern
- **Tool**: `put_object` / `use_object_on_object`
- **Example**: `put_object({"object_uuid": "<answer_marker_uuid>", "target_uuid": "<report_station_uuid>"})`
- **Purpose**: Submit your finding — which animal has anomalous protein expression, or what the expression pattern is.

## Tools Involved

`look_around`, `check_inventory`, `get_task_description`, `list_teleport_locations`, `get_discovery_feed`, `move`, `rotate`, `teleport_to_location`, `teleport_to_object`, `pick_up_object`, `drop_object`, `put_object`, `open_object`, `activate_device`, `deactivate_device`, `use_object_on_object`, `read_object`

## Tips

- The proteomics meter is your most important tool — locate and pick it up immediately.
- In outdoor scenarios with 10 animals, use `teleport_to_object` to move efficiently between specimens.
- Record each measurement result — you need to compare all values to find the outlier.
- The outlier will have measurements that are statistically different from the rest — look for values that are much higher or lower.
- For 3D protein data, the proteomics meter may return multi-dimensional readings — compare across all dimensions.
- Animals may move between measurements — re-check `look_around` if you can't find an animal.
- The discovery feed may contain hints about which animals have already been measured and their values.
