# Smart Home Scene Automation

## Description

Create and manage smart-home scenes and timed switches. This skill covers scene creation, scene query, modification, deletion, switch scheduling, cancellation, and final verification.

## Use Cases

- Add a new smart-home scene with multiple devices
- Query scene details before changing them
- Modify device lists for an existing scene
- Schedule and cancel timed device switches
- Delete obsolete scenes

## Workflow

### Step 1: Discover smart-home APIs
- **Tool**: `ToolSearcher`
- **Example**: `ToolSearcher({"keywords": "smart home scene timed switch devices"})`
- **Purpose**: Identify scene and timed switch tools for the workflow.

### Step 2: Add scene
- **Tool**: `AddScene` × 1-n times
- **Example**: `AddScene({"name": "movie night", "devices": ["living room light", "curtain", "speaker"]})`
- **Purpose**: Create a scene with a meaningful device list.

### Step 3: Query scene
- **Tool**: `QueryScene` × 1-n times
- **Example**: `QueryScene({"name": "movie night"})`
- **Purpose**: Verify scene creation and gather device evidence.

### Step 4: Modify scene devices
- **Tool**: `ModifyScene`
- **Example**: `ModifyScene({"name": "movie night", "devices": ["living room light", "curtain", "speaker", "air conditioner"]})`
- **Purpose**: Update automation configuration.

### Step 5: Schedule timed switch
- **Tool**: `TimedSwitch` × 1-n times
- **Example**: `TimedSwitch({"name": "living room light", "time": "2023-04-01 20:00:00", "on": true})`
- **Purpose**: Create a timed device action related to the scene.

### Step 6: Cancel timed switch if needed
- **Tool**: `CancelTimedSwitch`
- **Example**: `CancelTimedSwitch({"name": "living room light", "time": "2023-04-01 20:00:00"})`
- **Purpose**: Exercise cleanup or rescheduling of timed device automation.

### Step 7: Delete scene and verify
- **Tool**: `DeleteScene` then `QueryScene`
- **Examples**:
  - `DeleteScene({"name": "movie night"})`
  - `QueryScene({"name": "movie night"})`
- **Purpose**: Remove obsolete scene state and verify final outcome.

## Tools Involved

`ToolSearcher`, `AddScene`, `QueryScene`, `ModifyScene`, `DeleteScene`, `TimedSwitch`, `CancelTimedSwitch`

## Tips

- `devices` must be an array of strings.
- Use exact scene names across add/query/modify/delete calls.
- Timed switch tools are useful for creating deeper stateful trajectories within the smart-home domain.
