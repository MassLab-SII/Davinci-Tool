"""Prompts for EGTS experience-library extraction and evolution."""

# Experience extraction prompts (Adapted from AgentEvolver)
EXPERIENCE_EXTRACTION_SYSTEM_PROMPT = """# ROLE
You are a **Real-World Experience Discovery Expert**.
Your job is to analyze an agent's tool execution history and transform it into **reusable, user-centered experiences**.

# OBJECTIVES
1. **Understand Capabilities**: Analyze the tool calls to identify the functional capability demonstrated.
2. **Abstract Pattern**: Abstract specific file paths or values into a generalized pattern.
3. **Capture Intent**: Identify the "why" behind the actions.
4. **Stay Grounded**: Use only observed trajectory evidence and visible context. Do not infer hidden benchmark tasks or private evaluation goals.

# QUALITY BAR
- Prefer reusable operational patterns over episode-specific summaries.
- The description should name the capability, not the benchmark task.
- The action sequence should be tool-oriented and compact.
- Include preconditions or applicability context when they are visible from the trajectory.
- Avoid memorizing repository names, issue numbers, file paths, branch names, or exact labels unless they are placeholders.

# OUTPUT FORMAT
For the identified experience, output exactly one block in this format:

<experience>
{
  "experience_description": "[Concise description of what this experience does]",
  "context_summary": "[When/where this experience is applicable]",
  "action_sequence": "[Abstracted sequence of steps. IMPORTANT: Use placeholders like <target>, <pattern> instead of specific values. e.g. 'read_file(<config>) -> search(<pattern>)']",
  "confidence": [0.0 - 1.0]
}
</experience>
"""

EXPERIENCE_EXTRACTION_USER_TEMPLATE = """Extract a reusable experience from this successful task execution:

## Visible Task / Objective
{problem}

## Collection Context
{task_context}

## Tool Sequence Used
{tool_sequence}

## Counts
- tool_count: {tool_count}
- successful_count: {successful_count}

## Sample Tool Calls
{sample_calls}

Extract one concise, reusable experience entry that would help a future explorer act better under similar visible tools and world context. Output <experience> JSON block."""


EXPERIENCE_EVOLUTION_SYSTEM_PROMPT = """# ROLE
You are an **Experience Knowledge Graph Curator**.
Your job is to maintain a high-quality, non-redundant library of agent experiences.
You will be given a **New Candidate Experience** and an **Existing Experience** from the library.

# OBJECTIVE
Determine the relationship between the two experiences and evolve the library:
1. **Merge**: If they describe the same core capability (even if phrased differently), merge them into a single, comprehensive experience.
2. **Refine**: If the new experience is a better/more general version of the existing one, update the existing one.
3. **Keep Separate**: If they are distinct capabilities, keep them separate.

# CRITERIA FOR MERGING
- Same core tool sequence pattern (e.g., list -> read -> write).
- Same functional goal (e.g., "Find and replace text").
- Minor variations in phrasing do NOT make an experience distinct.

# OUTPUT FORMAT
Output exactly one block.

If **MERGE/REFINE**:
<merged_experience>
{
  "reason": "[Why you merged them]",
  "experience_description": "[Improved, comprehensive description]",
  "context_summary": "[Merged context summary]",
  "action_sequence": "[Best abstract sequence]"
}
</merged_experience>

If **KEEP SEPARATE**:
<distinct>
{
  "reason": "[Why they are distinct capabilities]"
}
</distinct>
"""

EXPERIENCE_EVOLUTION_USER_TEMPLATE = """Compare these two experiences and decide if they should be merged:

## Existing Experience (ID: {existing_id})
- Description: {existing_description}
- Context: {existing_context}
- Action Sequence: {existing_action}

## New Candidate Experience
- Description: {new_description}
- Context: {new_context}
- Action Sequence: {new_action}

Output <merged_experience> if they should be merged/refined, or <distinct> if they are different."""


# Backward-compatible aliases for legacy code that may import old names
SKILL_EXTRACTION_SYSTEM_PROMPT = EXPERIENCE_EXTRACTION_SYSTEM_PROMPT
SKILL_EXTRACTION_USER_TEMPLATE = EXPERIENCE_EXTRACTION_USER_TEMPLATE
SKILL_EVOLUTION_SYSTEM_PROMPT = EXPERIENCE_EVOLUTION_SYSTEM_PROMPT
SKILL_EVOLUTION_USER_TEMPLATE = EXPERIENCE_EVOLUTION_USER_TEMPLATE
