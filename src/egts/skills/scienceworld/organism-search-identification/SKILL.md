# Organism Search and Identification

## Description

Navigate the environment to find and identify organisms by their observable characteristics. Distinguish living from non-living things, plants from animals, and compare organisms by specific traits — including identifying the longest-lived or shortest-lived species from a set of candidates. This is a pure observation and navigation workflow — you are searching and classifying, not manipulating or experimenting.

## Use Cases

- Find a living thing in the environment (animal, plant, or other organism)
- Find a non-living (inanimate) object
- Locate and identify a specific plant among the environment's flora
- Locate and identify a specific animal
- Determine which organism has the longest lifespan from a group
- Determine which organism has the shortest lifespan from a group
- Find both the longest-lived and shortest-lived organisms in a single investigation

## Workflow

### Step 1: Read the search objective
- **Tool**: `get_task_description`
- **Example**: `get_task_description({})`
- **Purpose**: Understand exactly what you need to find — the organism type, the comparison criterion (longest-lived, shortest-lived), or the classification target (living, plant, animal).

### Step 2: Survey the current room
- **Tool**: `look_around`
- **Example**: `look_around({})`
- **Purpose**: Observe all visible entities in the starting room. Note any organisms, containers that might hold them, and doors to other rooms.

### Step 3: Explore connected rooms
- **Tool**: `open_object` / `go_to_location` / `look_around`
- **Examples**:
  - `open_object({"object": "door to greenhouse"})`
  - `go_to_location({"location": "greenhouse"})`
  - `look_around({})`
- **Purpose**: Organisms are distributed across the environment. The greenhouse contains plants; outdoor areas may have animals; labs may have specimens. Open doors before passing through them.

### Step 4: Examine promising candidates in detail
- **Tool**: `look_at_object`
- **Example**: `look_at_object({"object": "potted plant"})`
- **Purpose**: Inspect each candidate to determine its category — living vs non-living, plant vs animal. The detailed description reveals the organism's type and characteristics.

### Step 5: Check inside containers
- **Tool**: `look_in_container` / `open_object`
- **Examples**:
  - `open_object({"object": "terrarium"})`
  - `look_in_container({"container": "terrarium"})`
- **Purpose**: Organisms may be inside aquariums, terrariums, cages, or boxes. Open these containers first, then look inside.

### Step 6: Collect the identified organism if needed
- **Tool**: `pick_up_object` / `move_object_to_container`
- **Example**: `pick_up_object({"object": "butterfly egg"})`
- **Purpose**: Some tasks require you to move the organism to a specific container (e.g., "red box") as part of the answer. Check `get_task_description` to see if collection is needed.

### Step 7: For lifespan comparisons, observe each candidate
- **Tool**: `look_at_object` × multiple organisms
- **Examples**:
  - `look_at_object({"object": "baby brown bear"})`
  - `look_at_object({"object": "adult turtle"})`
- **Purpose**: When comparing organisms by lifespan or other traits, examine each candidate and note the relevant attribute from the description.

### Step 8: Designate your answer
- **Tool**: `focus_on_object`
- **Example**: `focus_on_object({"object": "adult turtle"})`
- **Purpose**: Focus on the organism that matches your search criteria. The task system verifies you identified the correct organism type or the correct comparison result.

## Tools Involved

`look_around`, `look_at_object`, `look_in_container`, `check_inventory`, `get_task_description`, `go_to_location`, `open_object`, `pick_up_object`, `focus_on_object`

## Tips

- The greenhouse is the best room for finding plants; outdoor areas and labs for animals.
- Living things show signs of life in their descriptions (growing, moving, biological terms). Non-living things are described as objects, tools, or furniture.
- You must open doors before `go_to_location` will let you pass — if the move fails, check whether the door is open.
- For lifespan tasks, examine each organism individually — the lifespan information is in the detailed `look_at_object` description.
- Some organisms are inside containers (terrariums, cages, aquariums) — open the container before you can look at or pick up the organism inside.
- The "red box" or "green box" mentioned in some task descriptions is where you must place the identified specimen — use `move_object_to_container` to transfer it there before focusing.
- If you cannot find the target in one room, systematically explore all connected rooms — organisms are always present somewhere.
