# Pipeline Orchestration

## Description

Build multi-step data processing pipelines in the workspace with chained commands, intermediate files, error handling, and comprehensive logging. Orchestrate end-to-end workflows that transform raw inputs into final deliverables.

## Use Cases

- Build a log processing pipeline: collect → filter → aggregate → report
- Create a data ETL workflow with staged processing and validation
- Write a backup pipeline with compression, rotation, and cleanup
- Orchestrate a multi-file transformation with dependency ordering
- Implement a scheduled task with logging and error notification

## Workflow

### Step 1: Survey — understand inputs and requirements
- **Tool**: `list_directory`, `read_file`, `get_environment_info`
- **Purpose**: Map all input sources, understand data formats, and define the pipeline stages.

### Step 2: Design — plan pipeline stages
- **Tool**: `write_file` (create pipeline script scaffold)
- **Purpose**: Outline the pipeline stages, intermediate outputs, and error handling.

### Step 3: Implement — write each stage
- **Tool**: `write_file`
- **Purpose**: Write the full pipeline script with stage-by-stage logic.

### Step 4: Test — run with sample data
- **Tool**: `execute_command`
- **Purpose**: Execute the pipeline and verify each stage produces correct output.

### Step 5: Monitor — check logs and outputs
- **Tool**: `read_file`, `list_directory`
- **Purpose**: Review logs, check intermediate files, verify final output.

### Step 6: Harden — add resilience
- **Tool**: `write_file`
- **Purpose**: Add error handling, retries, cleanup of temp files, and logging.

## Tools Involved

`write_file`, `execute_command`, `read_file`, `list_directory`, `search_content`, `get_environment_info`

## Tips

- Structure pipelines with clear stage boundaries: Stage 1 → output_1 → Stage 2 → output_2
- Use `set -e` and `set -o pipefail` for strict error handling
- Log each stage: `echo "[$(date)] Stage N: description"`
- Clean up temp files: `trap "rm -f $TMPDIR/*" EXIT`
- Test each stage independently before running the full pipeline
