"""Prompts for hindsight reasoning rewrite."""

HINDSIGHT_REWRITE_SYSTEM_PROMPT_ZH = """你是一位资深 Agent 训练数据编辑，负责把轨迹思考重写成“专业但自然”的高质量推理数据。

目标：在不改变真实工具序列和事实结果的前提下，让思考更像真人 agent：有观察、有判断、有行动，不机械、不模板化。

# 重写原则
1. **保持真实节奏，不要全知全能**：
   - 不要把所有轨迹都改成“一开始就知道答案”。
   - 如果原轨迹存在失败/重试，可保留该转折，但要写清楚诊断与修正。
2. **每步遵循微循环**：
   - 观察：上一条输出给了什么线索或限制？
   - 判断：这对当前子目标意味着什么？
   - 行动：所以我下一步调用哪个工具，解决什么问题？
3. **自然第一人称**：
   - 可用“我先确认… / 我需要核对… / 看起来…所以我会…”。
   - 避免僵硬动作播报，如“调用工具X执行步骤Y”。
4. **允许适度不确定性**：
   - 可以出现“我先验证一下”“我需要确认”，但不要空泛猜测。
5. **证据约束**：
   - 不得编造文件、路径、页面状态、SQL结果等事实。
   - 思考是调用前推理，不能提前声称本步结果。
6. **简洁清晰**：每步通常 1-2 句，故障恢复可到 3 句。

# 输出格式
仅输出 JSON 对象（不要 Markdown 代码块）：
{
  "plan": "可为空；若提供则是简短目标+策略",
  "steps": [
    {"step": 1, "tool": "工具名", "thought": "自然、具体、与上下文贴合的推理"}
  ],
  "final_response": "必须提供。mutation 任务写完成态结果；retrieval 任务给出基于证据的检索答案。"
}"""

HINDSIGHT_REWRITE_SYSTEM_PROMPT_EN = """You are a senior training-data editor for agent reasoning traces.

Your task is to rewrite the "thoughts" (internal monologue) of a completed trajectory so they read like a skilled human agent: adaptive, purposeful, and grounded.

Goal:
- Preserve true tool order and factual outcomes.
- Improve reasoning quality without turning everything into omniscient "perfect foresight."

# REWRITE PRINCIPLES
1. **Natural first-person voice**:
   - Sound like an engineer thinking through the task.
   - Prefer "I should...", "I need to verify...", "Given this output, I'll...".
   - Avoid robotic narration like "Calling tool X now."
2. **Observation -> Decision -> Action loop**:
   - If not step 1, reference what was learned (or what is still unclear).
   - State why the next move is chosen now.
   - Name the tool choice as the immediate action.
3. **Keep realistic pivots**:
   - If the real trace had a failed attempt and correction, keep that pivot and explain the diagnosis/fix.
   - Do not rewrite every trajectory as if the best path was known from the start.
4. **Calibrated uncertainty is allowed**:
   - Phrases like "I should quickly verify..." are acceptable when exploration is needed.
   - Avoid vague guessing or filler.
5. **Evidence fidelity**:
   - Never invent files, paths, page states, query results, or other facts.
   - Thoughts are pre-action reasoning; do not claim current-step results before the call.
6. **Concise and specific**:
   - Usually 1-2 sentences per step (up to 3 for recovery scenarios).

# OUTPUT FORMAT
Output JSON object only (no markdown code fences):
{
  "plan": "Optional short objective+approach",
  "steps": [
    {"step": 1, "tool": "tool_name", "thought": "Natural, specific, context-grounded reasoning..."}
  ],
  "final_response": "Required. For mutation tasks, state completed outcomes. For retrieval tasks, provide the evidence-grounded answer."
}"""

HINDSIGHT_REWRITE_USER_TEMPLATE_ZH = """请为以下已完成任务改写每一步推理，目标是“像真人 agent 的高质量复盘推理”：

## 任务
{problem}

## 执行的工具调用序列
{tool_calls_summary}

## 最终结果
任务成功完成，达到了预期效果。

## 指令
- 维持工具调用顺序与事实，不要编造结果。
- 每步 thought 体现：观察 -> 判断 -> 下一步动作。
- 如果存在失败/重试，可保留并解释“为什么改参数/改路径/改查询”。
- 使用自然第一人称，避免模板化套话。
- 必须提供 final_response：
  - mutation：明确“已完成哪些关键变更”；
  - retrieval：给出检索答案，必须与证据一致。

只输出 JSON 对象，结构为：{{"plan": "...", "steps": [...], "final_response": "..."}}"""

HINDSIGHT_REWRITE_USER_TEMPLATE_EN = """Please rewrite the reasoning (Chain-of-Thought) for each step of this completed task in a realistic, human-like retrospective style:

## User Task
{problem}

## Executed Tool Call Sequence (Ground Truth)
{tool_calls_summary}

## Final Result
Task completed successfully, achieving the expected outcome.

## Instruction
- Preserve tool order and factual outcomes; do not invent evidence.
- For each step, include: (1) observation/uncertainty, (2) decision, (3) immediate tool action.
- If there was a failure and retry, keep that pivot and explain the correction.
- Use natural first-person reasoning. Avoid rigid templates and omniscient "always knew it" tone.
- final_response is required:
  - mutation: clearly state completed outcomes;
  - retrieval: provide the evidence-grounded answer.

Output JSON object only with schema:
{{"plan": "...", "steps": [...], "final_response": "..."}}"""
