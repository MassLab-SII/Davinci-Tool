"""Unified synthesis prompts for executable-world evidence.

These templates are intentionally domain-agnostic. World differences should be
represented in structured evidence fields, not by adding a new prompt module for
each world.
"""

# ============================================================
# Mutation Problem Rewrite
# ============================================================

PROBLEM_REWRITE_SYSTEM_PROMPT_ZH = """你是一位任务合成专家。请根据已观察到的工具调用证据，生成一个自然、可执行、与证据一致的用户任务。

核心要求：
1. 任务必须和证据一致，不能引入未出现的关键要求。
2. 必须使用"用户提需求"的口吻，不能写成助手回复或客服话术。
3. 不要出现"我无法访问/请粘贴内容/发链接给我"等兜底措辞。
4. 若证据体现的是状态变更操作，应明确请求可验证的状态变化。
5. 若证据体现的是信息查询操作，应提出可由证据回答的问题。
6. 描述目标，不写步骤，不提工具名。
7. 禁止元话术（如"根据轨迹重写""ground truth"等）。

仅输出 JSON：
{
  "problem": "用户任务（1-3句）",
  "context": "可选背景（0-1句）",
  "expected_outcome": "完成后应达到的结果（1-2句）"
}"""

PROBLEM_REWRITE_SYSTEM_PROMPT_EN = """You are a task-synthesis expert.
Generate a natural user request from observed tool-call evidence.

Core requirements:
1. The task must be logically consistent with evidence.
2. Do not introduce unsupported major requirements.
3. The output must be written as a direct user request, not an assistant/helpdesk reply.
4. Do not use fallback language such as "I can't access...", "please paste...", or "share a link".
5. For mutation-style evidence, request concrete state changes supported by evidence.
6. For retrieval-style evidence, ask a question answerable from evidence.
7. Keep it user-facing, concise, and executable.
8. Describe goals, not step-by-step instructions; do not mention tool names.
9. Avoid meta wording like "rewrite from trajectory" or "ground truth".

Output JSON only:
{
  "problem": "User task (1-3 sentences)",
  "context": "Optional background (0-1 sentence)",
  "expected_outcome": "Expected completion state (1-2 sentences)"
}"""

PROBLEM_REWRITE_USER_TEMPLATE_ZH = """请根据以下证据生成任务：

## 操作概要
- 主要操作: {primary_action}
- 任务类型: {task_category}
- 涉及操作数: {navigations_count}

## 操作证据
{sample_operations}

## 使用工具
{tools_used}

仅输出 JSON。"""

PROBLEM_REWRITE_USER_TEMPLATE_EN = """Generate a user task from the evidence below.

## Operation Summary
- Primary action: {primary_action}
- Task category: {task_category}
- Operations count: {navigations_count}

## Evidence
{sample_operations}

## Tools Used
{tools_used}

Output JSON only."""

# ============================================================
# Retrieval/QA Rewrite
# ============================================================

RETRIEVAL_REWRITE_SYSTEM_PROMPT_ZH = """你是一位检索任务合成专家。请基于工具调用证据生成"自然问题 + 参考答案"。

要求：
1. 问题必须是用户提问，不是助手回复或兜底话术。
2. 不要出现"我无法访问/请粘贴内容/发链接给我"等表述。
3. 问题像用户真实提问，不提工具名。
4. 参考答案必须基于证据，不能编造。
5. 问答要与检索证据逻辑一致。
6. 若证据是列表/搜索多命中，参考答案必须完整覆盖证据中的命中项。
7. 禁止元话术。

仅输出 JSON：
{
  "problem": "用户问题（1-2句）",
  "reference_answer": "基于证据的答案",
  "context": "可选背景（0-1句）"
}"""

RETRIEVAL_REWRITE_SYSTEM_PROMPT_EN = """You are a retrieval-task synthesis expert.
Create a natural user question and a grounded reference answer from tool evidence.

Requirements:
1. The question must be in user voice, not assistant/helpdesk voice.
2. Do not use fallback language such as "I can't access...", "please paste...", or "share a link".
3. The question must sound user-facing and not mention tool names.
4. The reference answer must be grounded in evidence.
5. Keep QA logically consistent with retrieved content.
6. For list/search-style evidence with multiple hits, the reference answer must cover the full hit set.
7. Avoid meta wording.

Output JSON only:
{
  "problem": "User question (1-2 sentences)",
  "reference_answer": "Evidence-grounded answer",
  "context": "Optional background (0-1 sentence)"
}"""

RETRIEVAL_REWRITE_USER_TEMPLATE_ZH = """请基于以下证据生成自然问答：

## 查询焦点
{query_focus}

## 关键证据
- 工具: {evidence_tool}
- 参数: {evidence_arguments}

## 证据内容
{evidence_snippet}

## 调用摘要
{tool_call_summaries}

仅输出 JSON。"""

RETRIEVAL_REWRITE_USER_TEMPLATE_EN = """Create a natural QA pair from this evidence.

## Query Focus
{query_focus}

## Key Evidence
- Tool: {evidence_tool}
- Arguments: {evidence_arguments}

## Evidence Content
{evidence_snippet}

## Call Summaries
{tool_call_summaries}

Output JSON only."""
