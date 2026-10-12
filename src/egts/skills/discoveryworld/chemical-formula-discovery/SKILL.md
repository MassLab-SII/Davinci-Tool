# Chemical Formula Discovery

## Description

Systematically mix chemical reagents in beakers, observe reactions (color changes, precipitates, gas evolution), and identify unknown chemical formulas. Use chemical dispensers to add measured amounts of reagents, combine them in beakers, and analyze reactions to deduce the complete formula through iterative hypothesis testing.

## Use Cases

- Identify a single unknown chemical by testing with standard reagents
- Discover the formula of a 2-chemical mixture through systematic combination
- Determine the complete formula of a complex 4-chemical compound
- Use color changes and precipitates as clues to chemical identity
- Test hypotheses by adding specific reagents and observing reactions
- Verify formula predictions through confirmatory tests

## Workflow

### Step 1: Read the experimental objective
- **Tool**: `get_task_description`
- **Example**: `get_task_description({})`
- **Purpose**: Understand how many chemicals need to be identified and what reagents are available for testing.

### Step 2: Survey the laboratory
- **Tool**: `look_around`
- **Example**: `look_around({})`
- **Purpose**: Identify all accessible objects — beakers, chemical dispensers, reagent bottles, unknown samples. Note UUIDs of all instruments and chemicals.

### Step 3: Collect a beaker for mixing
- **Tool**: `pick_up_object` / `open_object`
- **Examples**:
  - `open_object({"object_uuid": "<cabinet_uuid>"})` — open storage
  - `pick_up_object({"object_uuid": "<beaker_uuid>"})` — take a beaker
- **Purpose**: You need a beaker as the reaction vessel. Pick up one before you can add chemicals.

### Step 4: Collect the unknown chemical sample
- **Tool**: `pick_up_object`
- **Example**: `pick_up_object({"object_uuid": "<unknown_chemical_uuid>"})`
- **Purpose**: Take the unknown sample you need to analyze.

### Step 5: Add the unknown to the beaker
- **Tool**: `put_object`
- **Example**: `put_object({"object_uuid": "<unknown_chemical_uuid>", "target_uuid": "<beaker_uuid>"})`
- **Purpose**: Place the unknown chemical into the beaker to prepare for testing.

### Step 6: Add a test reagent to the beaker
- **Tool**: `use_object_on_object`
- **Example**: `use_object_on_object({"object_uuid": "<reagent_a_uuid>", "target_uuid": "<beaker_uuid>"})`
- **Purpose**: Add a specific reagent to the beaker containing the unknown. Observe the reaction — did the color change? Did a precipitate form? Did gas evolve?

### Step 7: Observe the reaction result
- **Tool**: `look_around`
- **Example**: `look_around({})`
- **Purpose**: Check the last action message for the reaction description. Note the result (color, precipitate, no reaction) to form your hypothesis.

### Step 8: Test another reagent (iterate)
- **Tool**: `use_object_on_object`
- **Example**: `use_object_on_object({"object_uuid": "<reagent_b_uuid>", "target_uuid": "<beaker_uuid>"})`
- **Purpose**: Systematically test different reagents. Each reaction provides a clue about the chemical's identity.

### Step 9: Form and verify the formula
- **Tool**: `put_object` / `use_object_on_object`
- **Example**: `put_object({"object_uuid": "<predicted_chemical_uuid>", "target_uuid": "<result_container_uuid>"})`
- **Purpose**: Once you've gathered enough evidence, deliver your answer by putting the identified chemical formula into the designated results container.

### Step 10: Check the discovery feed for confirmation
- **Tool**: `get_discovery_feed`
- **Example**: `get_discovery_feed({})`
- **Purpose**: The discovery feed may confirm whether your formula identification was correct.

## Tools Involved

`look_around`, `check_inventory`, `get_task_description`, `list_teleport_locations`, `get_discovery_feed`, `move`, `rotate`, `teleport_to_location`, `pick_up_object`, `drop_object`, `put_object`, `open_object`, `close_object`, `activate_device`, `deactivate_device`, `use_object_on_object`, `read_object`

## Tips

- Test reagents one at a time — adding multiple reagents simultaneously confuses the analysis.
- Record each reaction result mentally or via memory — the pattern of reactions across reagents is your key to identifying the formula.
- Color changes are the most common indicator — green, blue, red, yellow, or no change each mean something.
- For multi-chemical mixtures, identify components sequentially — isolate one component, then move to the next.
- The beaker can become "contaminated" — you may need a fresh beaker for a new round of testing.
- Chemical dispensers may need to be activated before use — check with `activate_device` if a dispenser isn't working.
- Look for reference materials (books, signs) that may list reagent-color mappings.
