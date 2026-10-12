"""Base skill-guided exploration prompts.

These templates drive the skill-guided exploration pipeline stage. They are
domain-agnostic — the transition template uses a generic "review current state"
instruction instead of hardcoding filesystem-specific tool names.
"""

# Skill workflow guidance header (for first skill in system prompt)
SKILL_WORKFLOW_HEADER = """
## Professional Workflow Guidance

You are given a professional skill workflow below. Follow the steps in order to accomplish a coherent, high-quality task.

**Important:**
- Start by discovering the current environment state, then adapt all subsequent operations to what you actually observe — do NOT copy example values from the workflow verbatim
- At key decision points, briefly explain your reasoning before acting
- Read the workflow carefully and execute each step in sequence
- Each step builds on the results of the previous one
- Use the exact tool call format shown in the examples (tool arguments must be JSON objects)
- Output [SKILL_COMPLETED: {skill_id}] exactly once, only after ALL steps are finished — do not output it early or repeat it

"""

# Template for formatting a single skill workflow
SKILL_WORKFLOW_TEMPLATE = """
### Skill: {skill_id}

{skill_content}
"""

# Template for mid-conversation skill transition (injected as user message)
SKILL_TRANSITION_TEMPLATE = """You have completed the previous workflow. Before starting the next task, briefly review the current environment state using available read/listing tools to understand what has changed.

Then proceed with the following workflow:

{skill_content}

Output [SKILL_COMPLETED: {skill_id}] exactly once, only after ALL steps are finished.
"""

# Separator between multiple skills
SKILL_WORKFLOW_SEPARATOR = "\n\n---\n\n"

# ---------------------------------------------------------------------------
# Skill guidance / off-track nudge templates
# ---------------------------------------------------------------------------
# Injected as user messages during skill-guided exploration when the model
# repeatedly uses tools outside the expected skill workflow. Three tiers:
#   2+ steps off-track → mild nudge
#   4+ steps off-track → moderate reminder
#   6+ steps off-track → force re-injection of full SKILL.md

SKILL_GUIDANCE_MILD_TEMPLATE = """[Workflow Hint] Your recent tool usage appears to deviate from the '{skill_id}' workflow. Expected upcoming tools include: {remaining_tools}. If the workflow is substantially complete, you may output [SKILL_COMPLETED: {skill_id}]."""

SKILL_GUIDANCE_MEDIUM_TEMPLATE = """[Workflow Reminder] You have deviated from the '{skill_id}' workflow for {off_track_count} consecutive steps. Expected upcoming tools: {remaining_tools}. Please return to the workflow steps or output [SKILL_COMPLETED: {skill_id}] if the workflow is substantially complete."""

SKILL_GUIDANCE_FORCE_TEMPLATE = """[Workflow Re-Injection] You have been off-track for {off_track_count} consecutive steps. Below is the complete '{skill_id}' workflow for your review.

Steps whose tools have already been used: {completed_tools}
Remaining expected tools: {remaining_tools}

--- BEGIN WORKFLOW: {skill_id} ---
{skill_content}
--- END WORKFLOW ---

Based on what you have already accomplished and the current environment state, please EITHER:
1. Continue from where you left off in the remaining steps, OR
2. Output [SKILL_COMPLETED: {skill_id}] if the workflow is substantially complete."""
