# Pathogen Identification & Containment

## Description

Investigate a disease outbreak on a space station by collecting biological samples (mushrooms and other specimens), using microscopes and spectrometers to analyze pathogens, identifying which specific organism is causing the illness through causal diagnosis, and containing the outbreak by isolating or eliminating the source. Systematic sampling and elimination logic are key to solving the mystery.

## Use Cases

- Identify which of 3 mushroom species is causing illness in a single room colony
- Diagnose the pathogenic mushroom affecting 5 colonists across a full space station
- Solve probabilistic color-based pathogen logic puzzles with conditional effects
- Collect and analyze biological samples from multiple locations
- Use microscopes and spectrometers to identify pathogen characteristics
- Trace the causal chain from infection source to affected colonists

## Workflow

### Step 1: Read the medical objective
- **Tool**: `get_task_description`
- **Example**: `get_task_description({})`
- **Purpose**: Understand the outbreak scenario — how many potential pathogens, how many affected colonists, and what type of diagnosis is needed.

### Step 2: Survey the space station
- **Tool**: `look_around`
- **Example**: `look_around({})`
- **Purpose**: Identify all accessible objects — microscope, spectrometer, sample jars, mushroom specimens, affected colonists, and medical supplies. Note UUIDs.

### Step 3: Check teleport locations
- **Tool**: `list_teleport_locations`
- **Example**: `list_teleport_locations({})`
- **Purpose**: The space station has multiple rooms. Different mushroom specimens and colonists may be in different areas. Teleport to reach them.

### Step 4: Locate and collect sampling tools
- **Tool**: `pick_up_object` / `open_object`
- **Examples**:
  - `open_object({"object_uuid": "<medical_cabinet_uuid>"})` — open supply storage
  - `pick_up_object({"object_uuid": "<sample_jar_uuid>"})` — take a sample jar
  - `pick_up_object({"object_uuid": "<microscope_uuid>"})` — take microscope
- **Purpose**: Gather the tools needed for pathogen analysis. The microscope and spectrometer are essential.

### Step 5: Navigate to mushroom specimens
- **Tool**: `move` / `teleport_to_location`
- **Examples**:
  - `teleport_to_location({"location": "Hydroponics Bay"})`
  - `move({"direction": "east"})`
- **Purpose**: Reach the locations where mushroom specimens are growing. There may be multiple species in different rooms.

### Step 6: Collect a mushroom sample
- **Tool**: `pick_up_object`
- **Example**: `pick_up_object({"object_uuid": "<mushroom_a_uuid>"})`
- **Purpose**: Take a sample of the first mushroom species to analyze.

### Step 7: Analyze the sample with microscope
- **Tool**: `use_object_on_object`
- **Example**: `use_object_on_object({"object_uuid": "<microscope_uuid>", "target_uuid": "<mushroom_a_uuid>"})`
- **Purpose**: Examine the mushroom under the microscope to identify its characteristics — spore shape, color, structure. Record what you observe.

### Step 8: Analyze with spectrometer (if available)
- **Tool**: `use_object_on_object`
- **Example**: `use_object_on_object({"object_uuid": "<spectrometer_uuid>", "target_uuid": "<mushroom_a_uuid>"})`
- **Purpose**: Get chemical composition data for the mushroom. Different species will have different spectral signatures.

### Step 9: Repeat sampling and analysis for all mushrooms
- **Tool**: `move` / `teleport_to_location` → `pick_up_object` → `use_object_on_object`
- **Purpose**: Collect and analyze every mushroom species in the station. You need complete data to identify the pathogen.

### Step 10: Check on affected colonists
- **Tool**: `move` / `talk_to_person`
- **Examples**:
  - `move({"direction": "north"})` — go to the medical bay
  - `talk_to_person({"agent_uuid": "<colonist_uuid>"})` — ask about symptoms
- **Purpose**: Talk to colonists to learn their symptoms. This provides clues about which mushroom is causing illness.

### Step 11: Correlate mushroom data with colonist symptoms
- **Tool**: `look_around` / `get_discovery_feed`
- **Example**: `look_around({})`
- **Purpose**: Review all collected data. Which mushroom's characteristics match the disease pattern? Use elimination — if mushrooms A and B are benign, mushroom C must be the pathogen.

### Step 12: Contain the pathogen
- **Tool**: `put_object` / `close_object`
- **Examples**:
  - `put_object({"object_uuid": "<pathogen_mushroom_uuid>", "target_uuid": "<containment_unit_uuid>"})` — isolate
  - `close_object({"object_uuid": "<containment_door_uuid>"})` — seal the area
- **Purpose**: Once identified, contain or destroy the pathogenic mushroom to stop the outbreak.

### Step 13: Report the pathogen
- **Tool**: `use_object_on_object` / `put_object`
- **Example**: `put_object({"object_uuid": "<sample_label_uuid>", "target_uuid": "<report_station_uuid>"})`
- **Purpose**: Submit your diagnosis — which mushroom species is the pathogen.

## Tools Involved

`look_around`, `check_inventory`, `get_task_description`, `list_teleport_locations`, `get_discovery_feed`, `move`, `rotate`, `teleport_to_location`, `teleport_to_object`, `pick_up_object`, `drop_object`, `put_object`, `open_object`, `close_object`, `activate_device`, `deactivate_device`, `use_object_on_object`, `read_object`, `talk_to_person`, `select_dialog_option`

## Tips

- Collect ALL mushroom samples before starting analysis — you need complete data to use elimination logic.
- The microscope gives structural/morphological data; the spectrometer gives chemical data — both are useful.
- Talk to every affected colonist — their symptoms are clues that narrow down the pathogen.
- For probabilistic color logic (Challenge), mushroom color alone doesn't determine pathogenicity — certain colors cause disease only under specific conditions.
- Elimination is your friend — if you can prove mushrooms A and B are safe, mushroom C must be the pathogen.
- The sample jar may be required to collect certain specimens — pick it up before sampling.
- Deactivate instruments between measurements to ensure clean readings.
- The discovery feed may contain medical reports or outbreak updates — check it periodically.
