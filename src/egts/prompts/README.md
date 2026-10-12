# EGTS Prompts

This directory contains the prompt templates used by the EGTS data engine.

## Design

Runtime prompts are unified directly under `prompts/`. New executable worlds
should not require a new prompt package. World differences should be represented
as structured context and evidence:

- `world_context`
- tool names and tool schemas
- state evidence / diff summaries
- trajectory tool calls and outputs
- anchor usage metadata

`PromptLoader` keeps the old `mcp_server` argument for compatibility, but all
worlds route to the shared function-oriented templates in this package.

## Runtime Modules

```text
prompts/
├── exploration.py            # collection-time executable-world exploration
├── synthesis.py              # trajectory-to-problem rewrite prompts
├── self_questioning.py       # Stage-1 candidate problem generation
├── synthesis_judge.py        # problem/trajectory judge and rewrite loops
├── hindsight.py              # optional retrospective thought rewriting
├── skill_guided.py           # Stage-2 skill workflow injection
├── experience.py             # experience-library extraction/evolution
├── skills.py                 # compatibility alias for experience.py
├── trajectory_fallback.py    # rule-based trajectory thought fallback text
└── loader.py                 # PromptLoader shared API
```

Domain folders such as `filesystem/`, `playwright/`, and
`postgres/` should not be used for runtime EGTS prompt construction.

## Prompt File Responsibilities

- `exploration.py`: the system/user guidance used while collecting grounded
  trajectories from executable worlds. It receives `tool_names` and
  `world_context`.
- `synthesis.py`: mutation/retrieval problem synthesis prompts that turn
  trajectory evidence into natural user tasks.
- `self_questioning.py`: diverse candidate-problem generation before selecting
  the strongest task description.
- `synthesis_judge.py`: offline quality loops for problem consistency,
  trajectory rewriting, hard factual judging, soft style judging, and fallback
  polish.
- `hindsight.py`: optional rewriting of reasoning traces after the trajectory is
  already known.
- `skill_guided.py`: formatting wrappers for injecting selected `SKILL.md`
  workflows into exploration. This is the "use an existing workflow skill"
  path.
- `experience.py`: prompts for extracting reusable experience from successful
  episodes and merging/refining the experience library. This is the paper's
  experience-library path, not the exploration workflow-skill injector.
- `skills.py`: backward-compatible alias for `experience.py`; new code should
  import from `prompts.experience`.
- `trajectory_fallback.py`: deterministic fallback phrases and intent templates
  used when LLM trajectory rewriting is disabled or rejected.

## Adding a New Executable World

Do this:

1. Add world/tool metadata in config or the world admin reset response.
2. Ensure raw contexts include world identity, state evidence, and tool exposure.
3. Reuse `PromptLoader(...).get_exploration_prompt(...)` and synthesis APIs.

Avoid this:

1. Creating a new `prompts/<world>/` package for normal operation.
2. Encoding world-specific hidden task assumptions in prompts.
3. Falling back to filesystem-specific wording for non-filesystem worlds.
