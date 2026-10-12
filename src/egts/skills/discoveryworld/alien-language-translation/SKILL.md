# Alien Language Translation

## Description

Talk to NPC aliens to learn their vocabulary through structured dialog interaction. Associate alien words with real-world objects, colors, and quantities by having the NPCs describe items. Collect the correct items matching the alien descriptions and deliver them to prove translation accuracy. Progress from simple object naming to complex multi-attribute descriptions involving both color and quantity.

## Use Cases

- Learn alien names for 5 objects (simple naming, no attributes)
- Learn alien vocabulary including color OR quantity attributes
- Master alien vocabulary with both color AND quantity descriptors simultaneously
- Talk to NPCs to acquire new alien words
- Collect items matching alien descriptions
- Deliver correctly identified items to complete translation tasks

## Workflow

### Step 1: Read the translation objective
- **Tool**: `get_task_description`
- **Example**: `get_task_description({})`
- **Purpose**: Understand what type of translation task this is — simple item naming, single-attribute (color OR quantity), or complex multi-attribute (color AND quantity).

### Step 2: Survey the environment
- **Tool**: `look_around`
- **Example**: `look_around({})`
- **Purpose**: Identify NPCs you can talk to, objects around you, and possible destinations. Note the UUIDs of NPC agents and items.

### Step 3: Check for teleport locations
- **Tool**: `list_teleport_locations`
- **Example**: `list_teleport_locations({})`
- **Purpose**: The alien village may have multiple areas connected by teleporters. Different NPCs may be in different locations.

### Step 4: Approach and talk to an NPC
- **Tool**: `move` / `rotate` then `talk_to_person`
- **Examples**:
  - `move({"direction": "north"})` — approach the NPC
  - `talk_to_person({"agent_uuid": "<npc_uuid>"})` — initiate conversation
- **Purpose**: Start a dialog with an alien. They will speak to you in their language, describing objects or asking questions.

### Step 5: Read the dialog and select a response
- **Tool**: `select_dialog_option`
- **Example**: `select_dialog_option({"option": 1, "memory": "Alien word 'glorb' might mean 'red'"})`
- **Purpose**: Respond to the NPC's dialog. Option 1 is typically the first response. Use the memory parameter to record what you've learned about alien words.

### Step 6: Continue the dialog to learn more words
- **Tool**: `talk_to_person` / `select_dialog_option`
- **Examples**:
  - `talk_to_person({"agent_uuid": "<npc_uuid>"})` — continue conversation
  - `select_dialog_option({"option": 2, "hypothesis": "The alien uses 'blargh' for round objects"})`
- **Purpose**: Continue the conversation to learn additional vocabulary. Each dialog round may teach you new words or test your understanding.

### Step 7: Exit dialog when you have enough vocabulary
- **Tool**: `select_dialog_option`
- **Example**: `select_dialog_option({"option": 9})`
- **Purpose**: Option 9 typically exits the dialog. Exit when you've learned enough words to identify the target items.

### Step 8: Locate items matching the alien descriptions
- **Tool**: `move` / `teleport_to_location` / `look_around`
- **Examples**:
  - `teleport_to_location({"location": "Market"})` — go to where items are
  - `look_around({})` — survey available objects
- **Purpose**: Based on the alien vocabulary you've learned, find objects that match the alien descriptions (e.g., if "glorb" means red, find red objects).

### Step 9: Pick up the matching item
- **Tool**: `pick_up_object`
- **Example**: `pick_up_object({"object_uuid": "<red_object_uuid>"})`
- **Purpose**: Collect the item that matches the alien description.

### Step 10: Deliver the item to the NPC
- **Tool**: `talk_to_person` then `put_object`
- **Examples**:
  - `talk_to_person({"agent_uuid": "<npc_uuid>"})` — re-engage the NPC
  - `put_object({"object_uuid": "<item_uuid>", "target_uuid": "<npc_uuid>"})` — give the item
- **Purpose**: Deliver the item to prove your translation was correct. The NPC will confirm or reject.

### Step 11: Repeat for all required items
- **Tool**: `move` / `pick_up_object` / `put_object`
- **Purpose**: For multi-item tasks, repeat the locate-pickup-deliver cycle for each item described by the aliens.

### Step 12: Check the discovery feed for translation progress
- **Tool**: `get_discovery_feed`
- **Example**: `get_discovery_feed({})`
- **Purpose**: The discovery feed may record successful translations and track your overall progress.

## Tools Involved

`look_around`, `check_inventory`, `get_task_description`, `list_teleport_locations`, `get_discovery_feed`, `move`, `rotate`, `teleport_to_location`, `pick_up_object`, `drop_object`, `put_object`, `open_object`, `read_object`, `talk_to_person`, `select_dialog_option`

## Tips

- Use the `memory` and `hypothesis` parameters in `select_dialog_option` to record what you learn — they serve as your translation notebook.
- Talk to each NPC multiple times — a single conversation may not reveal all vocabulary.
- Exit dialog (option 9) between conversations with different NPCs to reset the dialog context.
- For color AND quantity tasks, pay attention to BOTH attributes — the aliens may describe a "red three" or "two blue" objects.
- Test your translation by picking up an item you think matches and using `check_inventory` to verify.
- NPCs may be in different locations — use `teleport_to_location` to reach them efficiently.
- The alien language is consistent within a scenario — once you learn that "glorb" means "red," it means red everywhere.
- Read signs or documents in the environment — they may provide translation hints or vocabulary references.
