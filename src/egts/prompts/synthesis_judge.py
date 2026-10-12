"""Base synthesis judge prompts — domain-agnostic quality evaluation.

Includes the full dual-judge pipeline (hard factual + soft style) and
polish-fallback pass. Domain-specific modules can override individual
constants if needed, but most domains should use these directly.
"""

# ============================================================
# Problem Judge
# ============================================================

JUDGE_PROBLEM_SYSTEM_PROMPT = """You judge whether a synthesized task is logically consistent with trajectory evidence.

Accept if the task goal is broadly aligned with observed actions and retrieved evidence.
Reject only for clearly unsupported claims.

Acceptance criteria (all must be true):
1. The task goal matches the general direction of observed actions and evidence.
2. The text is a direct user request in user voice (not assistant/helpdesk voice).
3. For task_type=mutation, it requests concrete state changes broadly supported by evidence.
4. For task_type=retrieval, it asks for information broadly answerable from observed evidence.
5. No clearly hallucinated requirement that contradicts the evidence.

Reject only for:
- Clear contradiction with trajectory evidence
- Fabricated requirements not supported by any observed action
- Assistant/helpdesk voice leakage (e.g., "I can't access...", "please paste...", "I can help summarize")
- Meta text about prompts/rewrite/judging

When uncertain, accept if the problem is broadly aligned with evidence direction.
Prefer inclusivity: if the problem could plausibly be answered by the observed actions, accept it.

Return JSON only:
{"consistent": true/false, "reason": "brief reason"}"""

JUDGE_PROBLEM_USER_TEMPLATE = """Evaluate problem consistency.

World context:
{world_context}

Task type: {task_type}

Candidate problem:
{problem}

Trajectory evidence summary:
{trajectory_summary}

Output JSON only."""

# ============================================================
# Problem Refine
# ============================================================

REFINE_PROBLEM_SYSTEM_PROMPT = """Rewrite to one concise, natural user request aligned with evidence.

Rules:
1. Output must be in user voice, not assistant/helpdesk voice.
2. Never output disclaimers like "I can't access", "please paste", or "share a link".
3. For mutation tasks, request concrete state changes supported by evidence.
4. For retrieval tasks, ask an information question answerable from evidence.
5. Do not mention trajectory/ground truth/rewrite/prompt/judge/tool call.
6. Keep only requirements supported by evidence.
7. Keep it realistic, executable, and concise.

Output plain text only."""

REFINE_PROBLEM_USER_TEMPLATE = """Rewrite this problem.

Previous problem:
{original_problem}

Evidence summary:
{trajectory_summary}

Judge feedback:
{critique}"""

# ============================================================
# Trajectory Judge (combined — legacy compatibility)
# ============================================================

JUDGE_TRAJECTORY_SYSTEM_PROMPT = """You judge rewritten trajectories for SFT quality with a human-like agent style.

Use outcome-first evaluation:
- Intermediate failed calls are acceptable if later actions recover.
- A few exploratory reads/checks are acceptable if the final outcome is evidence-consistent.
- However, if the majority of calls are exploration-framed with no clear task connection, reject.

Hard checks (reject if violated):
1. Tool-call facts are respected: preserve order and keep trajectory consistent with shown tool outputs.
2. Every tool-use step has pre-action first-person reasoning.
3. Reasoning is pre-action only (no claiming future/current-step results before execution).
4. If a call fails, later reasoning should acknowledge the failure and show a concrete adjustment.
5. Final assistant response must match observable evidence:
   - retrieval: answer is grounded in retrieved outputs/reference;
   - mutation: completion statement aligns with successful mutation actions.
   - retrieval listing/search questions: when evidence contains many concrete hits, answer must not silently drop most hits.
6. No fabricated evidence, entities, or results.
7. Conversation format must be: one system message, one user task, then assistant/tool turns only.
8. No explicit formatting tags like "[Plan]", "[Step ... Reasoning]", or "[truncated]".
9. Reasoning should frame actions as task execution, not generic exploration:
   - "I need to retrieve X the user asked about" is preferred over "I should gather data to inform the next decision"

Do NOT reject only because of:
- multiple early failed attempts,
- minor verbosity/style imperfections,
- a small number of extra exploratory reads (≤3).

DO reject when the majority of thoughts use generic exploration language with no clear connection to the user's specific task.

Return JSON only:
{"realistic": true/false, "reason": "brief reason"}"""

JUDGE_TRAJECTORY_USER_TEMPLATE = """Evaluate rewritten trajectory.

World context:
{world_context}

Task type: {task_type}
User problem: {problem}

Requirements:
- Expected tool-use steps: {required_tool_steps}
- Planning step required: {require_plan}
- Final answer required: {require_final_answer}
- Reference answer (retrieval tasks): {reference_answer}
- Outcome-first policy: intermediate failures are acceptable if final outcome is evidence-consistent.

Rewritten trajectory:
{trajectory_full}

Output JSON only."""

# ============================================================
# Trajectory Rewrite
# ============================================================

REWRITE_TRAJECTORY_SYSTEM_PROMPT = """Rewrite into a task-execution assistant trace — a human agent directly fulfilling a user request.

Goal:
- Keep tool order and factual evidence unchanged.
- Write first-person reasoning that connects EACH action to a specific part of the user's request.
- Frame every tool call as TASK EXECUTION, not exploration or preparation.

Constraints:
1. Add an initial plan when helpful (required only if specified). Keep it short: identify what the user needs and outline the approach.
2. For each tool-use step, write concise first-person reasoning (1-2 sentences) that names the specific task requirement this action addresses.
3. Thoughts are pre-action only: reference results from PREVIOUS steps, never the CURRENT or FUTURE step.
4. When a call fails, the NEXT thought should note the likely cause and adjustment.
5. Do not output labels/tags like "[Plan]" or "[Step 1 Reasoning]" and no placeholders like "[truncated]".
6. Keep exactly one user question (the provided Problem); do not introduce extra user turns.
7. Preserve original tool order.
8. End with completion text. For retrieval tasks, include an evidence-grounded answer.
9. Never invent evidence, entities, or results.
10. For retrieval listings/search results, provide a complete answer aligned with observed hits.
11. Keep reasoning task-specific: reference the user's request or a concrete entity. Generic connecting phrases ("I have X, now I'll do Y") are fine as long as X and Y are specific.

Output JSON only:
{
  "plan": "planning thought (can be empty only when planning is not required)",
  "steps": [{"step": 1, "thought": "I need to ... to address the user's request"}],
  "final_response": "task completion or retrieval answer"
}"""

REWRITE_TRAJECTORY_USER_TEMPLATE = """Rewrite trajectory with this schema.

Task type: {task_type}
Problem: {problem}
Planning required: {require_plan}
Final answer required: {require_final_answer}

Ordered tool calls (ground truth):
{tool_sequence_json}

Original trajectory excerpt:
{original_trajectory_excerpt}

Reference answer:
{reference_answer}

Previous judge feedback:
{critique}

Style requirements:
- Each thought must connect the action to a specific part of the user's request.
- Use task-grounded language: reference specific entities, data, or requirements the user asked about.
- Natural information gathering ("check the schema", "search for X", "list the directory") is expected and correct — it reflects real task execution.
- Keep each thought concise (usually <=42 words; longer only for error recovery).
- Prefer concrete task-relevant references over generic action descriptions.
- For retrieval list/search questions, make the final answer complete against observed hits.

Output JSON only in the required schema."""

# ============================================================
# Dual-Judge: Hard (factual consistency)
# ============================================================

JUDGE_TRAJECTORY_HARD_SYSTEM_PROMPT = """You judge rewritten trajectories for FACTUAL CONSISTENCY only — verifiable claims against observable evidence.

This is a binary gate. Style, phrasing, and task-framing quality are handled by a separate style judge; do NOT consider them here.

Use outcome-first evaluation:
- Intermediate failed calls are acceptable if later actions recover.
- A few exploratory reads/checks are acceptable if the final outcome remains evidence-consistent.

Binary checks (reject if ANY is violated):
1. FINAL RESPONSE FABRICATION: The final assistant response must report ONLY outcomes explicitly confirmed by tool outputs.
   - Retrieval: answer is grounded in retrieved data / reference answer.
   - Mutation: completion statement aligns with actual successful mutation results.
   - If a tool call failed and was never recovered, the final response must acknowledge the failure — claiming success for a failed call is fabrication.
2. EVIDENCE FABRICATION: The trajectory must not invent concrete entities (phone numbers, names, timestamps, IDs, status values) that do not appear in the tool outputs.
3. PRE-ACTION RESULT FABRICATION: A pre-action thought must not describe the CURRENT step's result before the tool is called. Describing what you *expect* or *intend* is acceptable; claiming a concrete result value before execution is not.
4. FORMAT: Conversation must be: one system message, one user task, then alternating assistant/tool turns. No extra user turns, no formatting tags like "[Plan]" or "[Step N Reasoning]".
5. TOOL CALL ORDER: The tool call sequence must be preserved as shown in the evidence — calls cannot be reordered, added, or removed.

Do NOT reject for:
- Style, wording, or phrasing issues (handled by style judge).
- Whether thoughts are "task-execution framed" or "exploration framed" (handled by style judge).
- Multiple early failed attempts that are later recovered.
- A small number of extra exploratory reads (≤3) if the final outcome is correct.

Return JSON only:
{"consistent": true/false, "reason": "brief reason"}"""

JUDGE_TRAJECTORY_HARD_USER_TEMPLATE = """Evaluate trajectory factual consistency.

World context:
{world_context}

Task type: {task_type}
User problem: {problem}

Requirements:
- Expected tool-use steps: {required_tool_steps}
- Final answer required: {require_final_answer}
- Reference answer (retrieval tasks): {reference_answer}
- Outcome-first policy: intermediate failures are acceptable if final outcome is evidence-consistent.

Rewritten trajectory:
{trajectory_full}

Output JSON only."""

# ============================================================
# Dual-Judge: Soft (style quality)
# ============================================================

JUDGE_TRAJECTORY_SOFT_SYSTEM_PROMPT = """You judge rewritten trajectories for reasoning quality and coherence.

This is a QUALITY GRADING check — it differentiates high-quality training samples from merely acceptable ones. Factual consistency is handled by a separate hard judge; do NOT re-evaluate it here.

IMPORTANT — Natural task-driven information gathering is NOT a flaw:
Multi-step tasks inherently require information-gathering steps. Phrases like
"Let me check the schema first", "I'll search for John to get his number",
"Let me list the directory to see what's there" are NORMAL and CORRECT when
they serve a clear purpose in the task flow. Do NOT flag these as issues.
The question is not whether the thought uses "Let me" or "I'll check" —
it's whether the step contributes to completing the task.

ONLY flag these GENUINE quality problems:

1. CONTEXTLESS STEPS: A step's reasoning has no discernible connection to the
   task goal AND the step's result is never used by any later step. If a step
   gathered information that later steps depend on, it is NOT contextless —
   even if the thought doesn't explicitly say "as the user requested."

2. VERBATIM REPETITION: The same reasoning text is copy-pasted across multiple
   steps. Each step should have contextually distinct reasoning.

3. PRE-ACTION RESULT DESCRIPTION: A thought describes the CURRENT step's
   concrete result before the tool is called. (Describing what you EXPECT or
   INTEND is fine. "Should return the contact list" is fine; "Returned 5 rows"
   before calling the tool is not.)

4. RAW PAYLOAD DUMPS: A thought consists mostly of raw JSON, SQL, or tool
   output data rather than concise reasoning about what to do.

5. FAILURE UNAWARENESS: After a ✗ FAILED step, the next step's reasoning
   shows no awareness of the failure — it proceeds as if nothing went wrong.

6. FORMATTING ARTIFACTS: Explicit tags like "[Plan]", "[Step N Reasoning]",
   "[truncated]", or similar markup in the thought text.

7. INCOHERENT THREAD: The reasoning across steps does not form a logical
   progression. Each step should build on previous results toward the goal.

PASS / FAIL GUIDANCE:
- realistic=true: The majority of steps have purposeful, contextually appropriate
  reasoning. Minor wording issues or 1-2 less-specific thoughts are acceptable
  in longer trajectories.
- realistic=false: Multiple GENUINE problems from the list above are present,
  AND they materially degrade the trajectory's value as training data. Do NOT
  set realistic=false merely because thoughts use "Let me check" or "I'll look
  at" phrasing — that language is natural and harmless.

SEVERITY — set only when realistic=false:
- severity="minor": Issues are isolated (e.g., 1-2 steps have slightly verbose
  reasoning or could be more specific). The trajectory is still usable.
- severity="major": Issues are pervasive AND harmful — verbatim repetition
  across >50% of steps, multiple pre-action result descriptions, reasoning
  consistently disconnected from task goal, or failure unawareness across
  multiple recovery steps. This trajectory would teach bad reasoning patterns.

Return JSON only:
{"realistic": true/false, "severity": "minor"|"major"|"", "reason": "brief reason", "issues": ["issue1", "issue2", ...]}"""

JUDGE_TRAJECTORY_SOFT_USER_TEMPLATE = """Evaluate trajectory style quality.

World context:
{world_context}

Task type: {task_type}
User problem: {problem}

Requirements:
- Planning step required: {require_plan}
- Expected tool-use steps: {required_tool_steps}

Rewritten trajectory:
{trajectory_full}

Output JSON only."""

# ============================================================
# Polish Fallback (refine rule-generated thoughts)
# ============================================================

POLISH_FALLBACK_TRAJECTORY_SYSTEM_PROMPT = """You are refining rule-generated trajectory thoughts into task-execution reasoning that reads like a human agent directly fulfilling a user request.

You are given:
1. A user task (problem statement) — this is your source for WHAT the user asked for
2. A complete tool call sequence with results (ground truth) — this is your source for WHAT ACTUALLY HAPPENED
3. Rule-generated thoughts (structurally correct but may need task grounding)
4. Reference answer (for retrieval tasks)

YOUR PRIMARY GOAL:
Reframe each thought to connect the action directly to the user's specific request. Each thought should answer: "What part of the user's request does THIS specific action fulfill?"

CRITICAL DISTINCTION — Fabrication vs. Task-Context Enrichment:

FABRICATION (FORBIDDEN) — inventing results that don't appear in tool outputs:
  ✗ "The contact's phone number is 555-1234" (when not in tool outputs)
  ✗ "Wi-Fi has been turned off successfully" (when the tool actually failed)
  ✗ Inventing names, timestamps, IDs, or status values not in tool outputs

TASK-CONTEXT ENRICHMENT (ENCOURAGED) — referencing the user's request to ground the thought:
  ✓ "I need to turn off Wi-Fi as the user requested." (the request IS in the problem statement)
  ✓ "I'll search contacts for 'Sarah Chen' to find the colleague the user mentioned." (names from user's request are fair game)
  ✓ "The user wants to check both cellular status and WiFi — let me retrieve each." (summarizing user's stated needs is not fabrication)

The RULE: You may freely reference the user's problem statement to ground your reasoning. You must NOT invent tool outputs, entity values, or outcome claims that are not confirmed by the tool results.

FRAMING TRANSFORMATION EXAMPLES:
- Template: "I should list the directory to understand the workspace structure."
  → Refined: "I need to list the /config directory the user asked about."
- Template: "Let me search to gather relevant information before deciding."
  → Refined: "I'll search for the specific files matching the user's criteria."
- Template: "I should check the current state to inform the next decision."
  → Refined: "I need to retrieve the current settings the user wants to review."
- Template: "I need to turn off wifi as the user requested."
  → Refined: "I need to disable Wi-Fi — the user asked to turn it off to conserve battery."

FINAL RESPONSE RULES:
- Report ONLY outcomes that are explicitly confirmed by tool outputs.
- When the user asked for X but the tool actually did Y, report Y honestly.
- If a tool call failed or returned an error, report that failure — do NOT claim success.
- NEVER invent concrete values (phone numbers, names, timestamps, IDs, status values) not in tool outputs.

CONSTRAINTS:
1. Keep tool call order and factual evidence unchanged.
2. Keep thought count unchanged (one per tool call).
3. Thoughts are strictly pre-action: describe what you're about to do and why. Never describe the current step's result before execution.
4. For failed calls (✗ FAILED), the NEXT thought should note the adjustment or likely cause.
5. Use natural first-person voice. Keep each thought to 1-2 sentences.
6. For retrieval tasks, ensure the final response covers the full hit set from tool outputs.
7. Keep reasoning task-grounded: reference specific entities, data, or requirements from the user's request. Natural information-gathering thoughts ("check the schema", "search for X") are correct — they reflect real task execution. Avoid only the most generic/vacuous forms: "see what's there" or "understand the current state" with no specific target.

Output JSON only:
{
  "plan": "Optional short objective+approach tied to the user's request",
  "steps": [{"step": 1, "thought": "Task-grounded, pre-action reasoning referencing what the user asked for..."}],
  "final_response": "Report ONLY what the tool outputs confirm happened. State actual outcomes, not desired ones."
}"""

POLISH_FALLBACK_TRAJECTORY_USER_TEMPLATE = """Refine these rule-generated thoughts into accurate, evidence-grounded reasoning.

User task: {problem}
Task type: {task_type}
Planning required: {require_plan}
Final answer required: {require_final_answer}

Complete tool call sequence (ground truth):
{tool_sequence_json}

Rule-generated fallback messages (to be refined):
{fallback_messages_json}

Reference answer (for retrieval tasks):
{reference_answer}

Previous critique (if any):
{critique}

Output JSON only in the required schema."""

# ============================================================
# Segmented Trajectory Rewrite (for long trajectories)
# ============================================================

REWRITE_TRAJECTORY_SEGMENT_SYSTEM_PROMPT = """You are rewriting ONE SEGMENT of a longer tool-use trajectory into a clean assistant execution trace.

You will receive:
1. The user's task (Problem)
2. A running context summary from previous segments
3. This segment's tool calls (a subset of the full trajectory)
4. Reference answer (if retrieval task)
5. Previous judge feedback (if any)

Your job for THIS SEGMENT ONLY:
- Write concise pre-action reasoning for each tool call in this segment
- Understand what has already been done (from the running context)
- Focus each thought on what this specific action achieves toward the user's task
- Produce a segment summary so the next segment knows what happened

Segment context: This segment is part {segment_index} of {total_segments}. {"This is the FIRST segment — include a short initial plan." if is_first else ""} {"This is the LAST segment — produce the final_response." if is_last else ""}

Constraints:
1. Each step's thought must reference the user's task goal, not generic exploration.
2. Thoughts are pre-action only — reference results from PREVIOUS steps (including those from earlier segments via the running context), never the current step.
3. When a call fails, the NEXT thought should note the adjustment.
4. Never invent evidence, entities, or results beyond what the tool outputs show.
5. Each thought should be 1-2 sentences.
6. The segment_summary must capture: (a) what tools were called in this segment, (b) key outputs/results, (c) what remains to be done.

Output JSON only:
{
  "steps": [{"step": 1, "thought": "..."}, ...],
  "segment_summary": "Brief summary of what happened in this segment and current state",
  "final_response": "ONLY for the last segment: task completion or retrieval answer"
}"""

REWRITE_TRAJECTORY_SEGMENT_USER_TEMPLATE = """Rewrite this segment of the trajectory.

Task type: {task_type}
Problem: {problem}
Planning required: {require_plan}
Final answer required: {require_final_answer}

Segment {segment_index} of {total_segments} (first={is_first}, last={is_last})

Running context from previous segments:
{running_summary}

Tool calls in this segment (ground truth):
{tool_sequence_json}

Reference answer:
{reference_answer}

Previous judge feedback:
{critique}

Style requirements:
- Each thought should name the specific action and connect it to the user's request
- Prefer concrete references to the task goal over generic exploration language
- Avoid phrases like "to inform the next decision" or "before deciding next steps"
- Use direct task-execution language: "to retrieve/find/create/update the X the user asked about"

Output JSON only in the required schema."""

# ============================================================
# Candidate Selection Judge (parallel LLM scoring)
# ============================================================

JUDGE_CANDIDATE_SYSTEM_PROMPT = """You evaluate a candidate problem statement against trajectory evidence.

Score the candidate on these dimensions, each 0.0-1.0:
1. **consistency** (0.0-1.0): Does the problem faithfully reflect observed tool calls and evidence? No hallucinated requirements.
2. **specificity** (0.0-1.0): Is the problem concrete and actionable, with clear success criteria? Not vague.
3. **naturalness** (0.0-1.0): Is it in natural user voice, concise, and realistic?

Scoring guidelines:
- 0.85-1.0: Excellent — consistent, specific, natural
- 0.70-0.85: Good — minor issues in one dimension
- 0.50-0.70: Fair — noticeable issues but salvageable
- 0.00-0.50: Poor — major inconsistencies or vague

Return JSON only:
{"consistency": 0.XX, "specificity": 0.XX, "naturalness": 0.XX, "overall": 0.XX, "reason": "brief reason"}"""

JUDGE_CANDIDATE_USER_TEMPLATE = """Evaluate this candidate problem.

World context:
{world_context}

Task type: {task_type}

Candidate problem:
{candidate}

Trajectory evidence summary:
{trajectory_evidence}

Output JSON only."""
