# Organism Cultivation and Breeding

## Description

Grow organisms from seed through complete lifecycles — prepare soil, plant seeds, water regularly, provide light, and wait through growth stages to observe development from seedling to mature adult to flowering/fruiting. For genetics tasks, extend the workflow across multiple generations: cross-breed parent plants by transferring pollen, grow offspring, observe inherited traits, and deduce genotypes from trait ratios. This is the longitudinal biology workflow covering plant growth, life stage identification, and Mendelian genetics.

## Use Cases

- Grow a plant from seed through all life stages to maturity
- Grow a fruit-bearing plant from seed to harvestable fruit
- Identify the current life stage of a plant (seed, seedling, vegetative, flowering, fruiting)
- Identify the current life stage of an animal (egg, juvenile, adult)
- Cross-breed two known plants and predict offspring traits using Mendelian genetics
- Determine the genotype of an unknown plant through controlled multi-generational breeding experiments

## Workflow

### Step 1: Read the cultivation or breeding objective
- **Tool**: `get_task_description`
- **Example**: `get_task_description({})`
- **Purpose**: Understand what you need to achieve — grow to maturity, identify a life stage, harvest fruit, or conduct a genetics experiment across generations.

### Step 2: Survey available resources
- **Tool**: `look_around`
- **Example**: `look_around({})`
- **Purpose**: Identify growing supplies — pots, soil, seeds, water source, grow lights, and any existing plants or organisms.

### Step 3: Navigate to the growing area
- **Tool**: `open_object` / `go_to_location`
- **Examples**:
  - `open_object({"object": "door to greenhouse"})`
  - `go_to_location({"location": "greenhouse"})`
- **Purpose**: The greenhouse has soil, pots, seeds, and ideal growing conditions. Outdoor areas may have wild organisms for life stage observation.

### Step 4: Gather planting materials
- **Tool**: `pick_up_object`
- **Examples**:
  - `pick_up_object({"object": "pot"})` — the growing container
  - `pick_up_object({"object": "soil"})` — the growing medium
  - `pick_up_object({"object": "seed"})` — what you will plant
- **Purpose**: Collect the essentials for planting. You need at minimum: a container, soil, a seed, and later water.

### Step 5: Prepare the growing container with soil
- **Tool**: `move_object_to_container`
- **Example**: `move_object_to_container({"object": "soil", "container": "pot"})`
- **Purpose**: Fill the pot with soil to create the growing medium.

### Step 6: Plant the seed in the soil-filled pot
- **Tool**: `move_object_to_container`
- **Example**: `move_object_to_container({"object": "seed", "container": "pot"})`
- **Purpose**: Place the seed into the prepared pot. The seed is now planted and ready for care.

### Step 7: Water the planted seed
- **Tool**: `pour_object_into_container`
- **Example**: `pour_object_into_container({"object": "water", "container": "pot"})`
- **Purpose**: Provide the water essential for germination. Find water from a sink, watering can, or other source first.

### Step 8: Place the pot under a grow light
- **Tool**: `move_object_to_container`
- **Example**: `move_object_to_container({"object": "pot", "container": "grow light"})`
- **Purpose**: Position the pot where it will receive light for photosynthesis.

### Step 9: Activate the grow light
- **Tool**: `activate_device`
- **Example**: `activate_device({"device": "grow light"})`
- **Purpose**: Turn on the light source to provide energy for growth.

### Step 10: Wait for growth to progress
- **Tool**: `wait_time` × multiple cycles
- **Example**: `wait_time({"seconds": 5})`
- **Purpose**: Growth takes many time steps. Wait in increments, checking progress between waits.

### Step 11: Observe the current growth stage
- **Tool**: `look_around` / `look_at_object`
- **Examples**:
  - `look_around({})` — check the room for any visible changes
  - `look_at_object({"object": "pot"})` — examine the plant's current state
- **Purpose**: Determine which life stage the plant has reached. Stages progress: seed → seedling → vegetative → flowering → fruiting.

### Step 12: For life stage identification, observe at the right time
- **Tool**: `focus_on_object`
- **Example**: `focus_on_object({"object": "seedling"})`
- **Purpose**: When you've identified the correct life stage, focus on the organism to report it. Some tasks require identifying multiple stages — repeat Steps 10-11 until all stages are observed.

### Step 13: For fruit tasks, continue waiting until harvestable
- **Tool**: `wait_time` / `look_at_object`
- **Examples**:
  - `wait_time({"seconds": 5})`
  - `look_at_object({"object": "plant"})`
- **Purpose**: Fruiting is the final growth stage — continue the wait/observe cycle until the plant produces mature fruit.

### Step 14: For genetics — cross-breed parent plants
- **Tool**: `pour_object_into_container`
- **Example**: `pour_object_into_container({"object": "pollen from plant A", "container": "flower of plant B"})`
- **Purpose**: Transfer pollen from the male parent to the female parent's flower. This creates hybrid seeds.

### Step 15: Harvest and plant the offspring seeds
- **Tool**: `move_object_to_container` × each offspring
- **Example**: `move_object_to_container({"object": "seed", "container": "pot"})`
- **Purpose**: Collect seeds from the cross-pollinated plant and plant each one in its own pot. Grow offspring following Steps 7-11.

### Step 16: Observe offspring traits and deduce genotype
- **Tool**: `look_at_object` × each offspring plant
- **Example**: `look_at_object({"object": "offspring plant 1"})`
- **Purpose**: Examine each offspring's phenotype (observable traits like color, height). Compare trait ratios against Mendelian predictions (3:1 for dominant:recessive in F2 generation).

### Step 17: Report the final result
- **Tool**: `focus_on_object`
- **Example**: `focus_on_object({"object": "red box"})`
- **Purpose**: Designate the mature plant, identified life stage, harvested fruit, or deduced genotype as your answer.

## Tools Involved

`look_around`, `look_at_object`, `look_in_container`, `check_inventory`, `get_task_description`, `go_to_location`, `open_object`, `close_object`, `pick_up_object`, `put_down_object`, `move_object_to_container`, `pour_object_into_container`, `activate_device`, `deactivate_device`, `use_object_on_object`, `wait_time`, `focus_on_object`, `eat_food`

## Tips

- Growth requires PATIENCE — full plant development takes 20-60+ wait steps. Check progress with `look_around` or `look_at_object` after every 3-5 waits.
- Water is essential for germination. If no water source is visible, check the kitchen sink or look for a watering can.
- The grow light must be both positioned (move the pot under it) AND activated for growth to occur.
- Life stages progress in order: seed → seedling → vegetative adult → flowering → fruiting. You cannot skip stages.
- For genetics: grow the parent generation FIRST, then cross-breed, then grow the offspring. The full genetics cycle takes 100+ steps.
- Mendelian dominant traits show in a 3:1 ratio in the F2 generation — if 3 offspring show the dominant trait and 1 shows recessive, the parent was likely heterozygous.
- For animal life stage observation, look for eggs in terrariums or outdoor areas — eggs hatch into juveniles which grow into adults.
- Deactivate grow lights after the experiment is complete to avoid wasting steps.
- The `close_object` tool is used in genetics tasks to create controlled breeding environments — close doors between plant groups to prevent accidental cross-pollination.
