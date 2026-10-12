# EGTS user guide

EGTS (Execution-Grounded Task Synthesis) is the authored-system data engine of Davinci-Tool.

1. **Outcome exploration** — an explorer model interacts with a resettable executable world and
   records actions, observations, and outcome evidence (state transitions for mutation worlds,
   grounded observations for retrieval worlds).
2. **Task synthesis** — user tasks are synthesized *from* the recorded outcome, so every task is
   feasible from the initial state and supported by evidence.
3. **Guided replay and verification** — the world is restored to the same initial state, the task is
   executed again with a replay guide, and the replay is accepted only if it recovers the explored
   outcome. Structural checks, a hard factual judge, and a soft quality judge filter the results.
4. **SFT export** — accepted replays are serialized as `messages` + `tools`. The exploration trace and
   replay guide are construction-only and are not part of the training example.

## Code (`src/egts/`)

| Directory | Contents |
|---|---|
| `data_collection/` | Exploration loop, progressive tool exposure, experience store, world adapters, replay synthesis and verification |
| `data_synthesis/` | Offline task synthesis, judging, dedup, quality gates, SFT export (`trajectory_to_sft.py`) |
| `prompts/` | Exploration, synthesis, judge, and skill-guided prompts |
| `skills/` | Per-world skill guides used for skill-guided exploration |

## Configuration

1. Copy `.env.example` to `.env` and set the OpenAI-compatible endpoints:
   `EXPLORATION_MODEL_*` (explorer), `JUDGE_MODEL_*` (judges), `WRITER_MODEL_*` (task writer).
   World-specific credentials (`GITHUB_TOKENS`, `TOOLATHLON_*`) are optional.
2. Per-world configs are in `configs/egts/`:

| File | Purpose |
|---|---|
| `<world>.yaml` | Collection config for one world: model roles, world endpoint and compose file, exploration budget, output directory, skill directory |
| `synthesis.yaml` | Offline task synthesis / judging config used by `run_synthesis.sh` and the multi-world synthesis launchers |
| `data_synthesis_example.yaml` | Annotated synthesis example |
| `exploration_worlds_config_example.yaml` | Annotated collection example (ToolSandbox) |
| `config.yaml` | Default config loaded when no `--config` is given |

Relative paths in configs (outputs, workspaces, compose files, skills) are resolved from the
repository root.

## Running

```bash
# 1. Serve the executable world at the endpoint in its config
#    (EGTS environments are not included in this release; see docs/environments.md)

# 2. Explore and collect grounded raw trajectories
bash scripts/egts/run_tool_sandbox.sh                 # one world
bash scripts/egts/run_multi_worlds.sh                 # several worlds in batches (edit EXECUTABLE_WORLDS)

# 3. Synthesize tasks, replay, verify, and judge
bash scripts/egts/run_synthesis.sh                    # edit INPUT_DIR / OUTPUT_FILE in the script
bash scripts/egts/run_multi_world_synthesis_parallel.sh

# 4. Export accepted demonstrations to SFT format
bash scripts/egts/convert.sh                          # one experiment
bash scripts/egts/batch_convert.sh                    # all experiments under output/
```

Outputs are written under `output/` and per-run workspaces under `workspaces/` (both ignored by Git).
Construction records (raw context, state evidence, candidate tasks, verification results) are written
next to the collection output for provenance.

### Scripts (`scripts/egts/`)

| Script | Purpose |
|---|---|
| `run_<world>.sh` | Check one world and run collection with its config |
| `run_collection.sh` | Run collection with any config (`CONFIG_PATH` argument) |
| `run_multi_worlds.sh` | Collect several worlds in parallel batches |
| `run_synthesis.sh` | Offline synthesis on one collection output |
| `run_multi_world_synthesis.sh`, `run_multi_world_synthesis_parallel.sh` | Synthesis or replay synthesis over several worlds |
| `convert.sh`, `batch_convert.sh` | Export to SFT (`axolotl` or `llamafactory` format) with quality filters |
| `backfill_experience_store.py`, `backfill_mcpmark_github_experience.sh` | Rebuild the experience store from existing runs |
| `evaluate_pipeline.py` | Summarize an experiment's collection and synthesis statistics |

### Running Python entry points directly

```bash
PYTHONPATH=src/egts python src/egts/data_collection/main.py --config configs/egts/tool_sandbox.yaml
PYTHONPATH=src/egts python -m data_synthesis.trajectory_to_sft --help
```
