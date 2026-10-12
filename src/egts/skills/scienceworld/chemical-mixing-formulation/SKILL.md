# Chemical Mixing Formulation

## Description

Mix substances and paints to create new colors or chemical products. Pour liquids and pigments into a common vessel, combine primary colors to make secondary and tertiary colors, mix chemicals to trigger reactions, and verify the resulting product. This is the core chemistry workflow covering all three Chemistry benchmark tasks.

## Use Cases

- Mix two chemical substances and observe the resulting reaction
- Combine primary paint colors (red + blue) to create a secondary color (purple)
- Combine primary and secondary paints to create a specific tertiary color
- Create a specific paint color on demand for an artistic or experimental task
- Mix substances in precise combinations and verify the product

## Workflow

### Step 1: Read the formulation objective
- **Tool**: `get_task_description`
- **Example**: `get_task_description({})`
- **Purpose**: Determine what color or chemical product you need to create, and what source substances are available.

### Step 2: Survey available substances
- **Tool**: `look_around` / `look_in_container`
- **Examples**:
  - `look_around({})` — check visible items in the room
  - `look_in_container({"container": "cupboard"})` — check storage
- **Purpose**: Find all available paint colors, chemicals, mixing vessels (beakers, cups, jugs), and any other supplies.

### Step 3: Navigate to the room with the materials
- **Tool**: `go_to_location` / `open_object`
- **Examples**:
  - `open_object({"object": "door to art studio"})`
  - `go_to_location({"location": "art studio"})`
- **Purpose**: Paint mixing tasks are typically in the art studio. Chemical mixing may be in the kitchen or lab. Open doors to access these rooms.

### Step 4: Gather the source substances
- **Tool**: `pick_up_object`
- **Examples**:
  - `pick_up_object({"object": "red paint"})` — take the first color
  - `pick_up_object({"object": "blue paint"})` — take the second color
  - `pick_up_object({"object": "cup"})` — take a mixing vessel
- **Purpose**: Collect all source substances and a container to mix them in. You need both paints/chemicals and a vessel in your inventory.

### Step 5: Pour the first substance into the mixing vessel
- **Tool**: `pour_object_into_container`
- **Example**: `pour_object_into_container({"object": "red paint", "container": "cup"})`
- **Purpose**: Transfer the first component into the mixing container. The substance is now in the vessel but not yet combined with the second.

### Step 6: Pour the second substance into the same vessel
- **Tool**: `pour_object_into_container`
- **Example**: `pour_object_into_container({"object": "blue paint", "container": "cup"})`
- **Purpose**: Add the second component. Both substances are now in the same container, layered but not yet mixed.

### Step 7: Mix the combined substances
- **Tool**: `mix_objects`
- **Example**: `mix_objects({})`
- **Purpose**: Mix the contents of the container to combine the substances. This triggers the color blend or chemical reaction. The result is a new substance (e.g., purple paint from red + blue).

### Step 8: For tertiary colors, add a third substance and mix again
- **Tool**: `pour_object_into_container` / `mix_objects`
- **Examples**:
  - `pour_object_into_container({"object": "yellow paint", "container": "cup"})`
  - `mix_objects({})`
- **Purpose**: Tertiary colors require three components (e.g., purple + yellow = brown). Add the third substance to the already-mixed result and mix again.

### Step 9: Verify the result
- **Tool**: `look_in_container` / `look_at_object`
- **Examples**:
  - `look_in_container({"container": "cup"})` — check the color inside
  - `look_at_object({"object": "cup"})`
- **Purpose**: Confirm the mixture produced the expected color or chemical product.

### Step 10: Report the created product
- **Tool**: `focus_on_object`
- **Example**: `focus_on_object({"object": "green paint"})`
- **Purpose**: Designate the created color or chemical as your answer. The task system verifies it matches the target.

## Tools Involved

`look_around`, `look_at_object`, `look_in_container`, `check_inventory`, `get_task_description`, `go_to_location`, `open_object`, `pick_up_object`, `pour_object_into_container`, `mix_objects`, `focus_on_object`

## Tips

- Standard color mixing: Red + Blue = Purple, Blue + Yellow = Green, Red + Yellow = Orange (secondary colors). Add a third primary for tertiary colors.
- All substances must be poured into the SAME container before mixing — `mix_objects` acts on whatever container holds the combined contents.
- The mixing vessel (cup, beaker, jug) must be in your inventory or the current room before you can pour into it.
- Each `pour_object_into_container` transfers one substance — you need one pour per source substance.
- Always verify the result with `look_in_container` or `look_at_object` after mixing before reporting — the color description confirms the mix was successful.
- Paint containers may be labeled by color (e.g., "red paint", "blue paint") — match the label, not just the appearance.
- For chemical mixing (non-paint), some reactions may require activation (heating) — check the task description for additional steps.
