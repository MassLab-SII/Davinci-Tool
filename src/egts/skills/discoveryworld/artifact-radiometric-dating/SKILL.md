# Artifact Radiometric Dating

## Description

Excavate buried artifacts using a shovel, then use a radiocarbon dater instrument to measure isotope levels and determine artifact ages. Compare dating results across multiple dig sites, establish chronological ordering, and in advanced scenarios perform multi-channel isotope calibration to reconstruct site chronology.

## Use Cases

- Dig up artifacts at a single archaeological site and date each one individually
- Excavate artifacts from multiple sites and compare their ages to establish timeline
- Use a radiocarbon dater to measure C-14 isotope ratios in artifacts
- Perform 4-channel isotope calibration on artifacts for precise dating
- Reconstruct the chronological order of a multi-layer archaeological site
- Correlate artifact ages with known historical periods

## Workflow

### Step 1: Read the scientific objective
- **Tool**: `get_task_description`
- **Example**: `get_task_description({})`
- **Purpose**: Understand what artifacts need to be dated, how many sites to excavate, and what level of precision is required.

### Step 2: Survey the dig site
- **Tool**: `look_around`
- **Example**: `look_around({})`
- **Purpose**: Identify accessible objects — shovel, radiocarbon dater, dig sites, and any reference materials. Note UUIDs of key instruments.

### Step 3: Check available teleport locations
- **Tool**: `list_teleport_locations`
- **Example**: `list_teleport_locations({})`
- **Purpose**: Discover if there are multiple dig sites accessible via teleport. Multi-site scenarios require traveling between locations.

### Step 4: Locate and collect excavation tools
- **Tool**: `move` / `pick_up_object` / `open_object`
- **Examples**:
  - `pick_up_object({"object_uuid": "<shovel_uuid>"})` — take the shovel
  - `open_object({"object_uuid": "<toolbox_uuid>"})` — open a container holding instruments
- **Purpose**: You need a shovel to dig and a radiocarbon dater to measure. Collect both before going to the dig site.

### Step 5: Navigate to the dig site
- **Tool**: `move` / `teleport_to_location`
- **Examples**:
  - `move({"direction": "north"})` — walk to the dig site
  - `teleport_to_location({"location": "Dig Site A"})` — jump to a named dig site
- **Purpose**: Reach the location where artifacts are buried. Different sites may have different artifacts.

### Step 6: Excavate the artifact
- **Tool**: `use_object_on_object`
- **Example**: `use_object_on_object({"object_uuid": "<shovel_uuid>", "target_uuid": "<dig_site_uuid>"})`
- **Purpose**: Use the shovel on the dig site to unearth an artifact. The artifact will appear as a new accessible object.

### Step 7: Pick up the excavated artifact
- **Tool**: `pick_up_object`
- **Example**: `pick_up_object({"object_uuid": "<artifact_uuid>"})`
- **Purpose**: Take the newly excavated artifact into your inventory so you can date it.

### Step 8: Date the artifact with the radiocarbon dater
- **Tool**: `use_object_on_object`
- **Example**: `use_object_on_object({"object_uuid": "<radiocarbon_dater_uuid>", "target_uuid": "<artifact_uuid>"})`
- **Purpose**: Measure the C-14 isotope ratio of the artifact. The measurement result tells you the artifact's age.

### Step 9: Record and compare dating results
- **Tool**: `look_around`
- **Example**: `look_around({})`
- **Purpose**: Check the discovery feed and task progress to see dating results and verify which artifacts have been successfully dated.

### Step 10: Move to next dig site and repeat
- **Tool**: `move` / `teleport_to_location`
- **Example**: `teleport_to_location({"location": "Dig Site B"})`
- **Purpose**: For multi-site scenarios, travel to the next site and repeat steps 5-9 until all required artifacts are dated.

### Step 11: Check the discovery feed for results
- **Tool**: `get_discovery_feed`
- **Example**: `get_discovery_feed({})`
- **Purpose**: The discovery feed may contain synthesized results or hints about the chronological relationship between dated artifacts.

## Tools Involved

`look_around`, `check_inventory`, `get_task_description`, `list_teleport_locations`, `get_discovery_feed`, `move`, `rotate`, `teleport_to_location`, `pick_up_object`, `drop_object`, `put_object`, `open_object`, `activate_device`, `deactivate_device`, `use_object_on_object`, `read_object`, `eat_food`

## Tips

- Always pick up the shovel AND the radiocarbon dater before going to the dig site — you cannot excavate without the shovel or date without the dater.
- The radiocarbon dater must be in your inventory to use it on an artifact.
- artifacts are typically buried at dig sites — use the shovel ON the dig site, not on the ground.
- Multi-site scenarios require systematic recording — date all artifacts at one site before moving to the next.
- For calibration tasks, you may need to date the same artifact multiple times using different isotope channels.
- The discovery feed is your lab notebook — check it periodically to track your dating results.
- If a container holds instruments, open it first with `open_object` before trying to pick up its contents.
