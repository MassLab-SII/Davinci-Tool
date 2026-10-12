"""Exploration state recording for anti-repetition prompting.

Implements PRD 4.1.2: "维护'相似上下文下已尝试动作/工具调用'的记录，
在 prompt 中提示：优先选择未尝试过的工具/动作"
"""

import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Set, Optional, Tuple

from prompts.exploration import (
    EXPLORATION_GUIDANCE_HEADER,
    EXPLORATION_GUIDANCE_AVOID,
    EXPLORATION_GUIDANCE_CONSIDER,
)

logger = logging.getLogger(__name__)


@dataclass
class ToolAttempt:
    """Record of a tool call attempt."""

    tool_name: str
    args_signature: str  # Hash of key arguments
    success: bool
    context_hash: str  # Hash of context when attempted


class ExplorationStateRecorder:
    """Records tool usage to enable anti-repetition prompting.

    PRD 4.1.2: "反重复探索提示 (State Recorder Inspired)"
    """

    def __init__(self, max_repetitions: int = 2):
        """Initialize state recorder.

        Args:
            max_repetitions: Max times a tool+context combo can repeat
        """
        self.max_repetitions = max_repetitions

        # tool_name -> list of attempts
        self._attempts: Dict[str, List[ToolAttempt]] = defaultdict(list)

        # (tool_name, context_hash) -> count
        self._repetition_counts: Dict[Tuple[str, str], int] = defaultdict(int)

        # Track all unique context hashes seen
        self._context_hashes: Set[str] = set()

    def record_attempt(
        self,
        tool_name: str,
        arguments: Dict,
        success: bool,
        context_messages: List[Dict],
    ):
        """Record a tool call attempt.

        Args:
            tool_name: Name of the tool
            arguments: Tool arguments
            success: Whether the call succeeded
            context_messages: Current message context
        """
        context_hash = self._hash_context(context_messages)
        args_sig = self._hash_arguments(arguments)

        attempt = ToolAttempt(
            tool_name=tool_name,
            args_signature=args_sig,
            success=success,
            context_hash=context_hash,
        )

        self._attempts[tool_name].append(attempt)
        self._repetition_counts[(tool_name, context_hash)] += 1
        self._context_hashes.add(context_hash)

    def get_exploration_hints(
        self, available_tools: List[str], context_messages: List[Dict]
    ) -> str:
        """Generate exploration hints for the prompt.

        Args:
            available_tools: List of available tool names
            context_messages: Current message context

        Returns:
            Hint text to append to system prompt
        """
        context_hash = self._hash_context(context_messages)

        hints = []

        # Find tools that have been overused in this context
        overused = []
        underused = []

        for tool in available_tools:
            count = self._repetition_counts.get((tool, context_hash), 0)

            if count >= self.max_repetitions:
                overused.append(tool)
            elif count == 0:
                underused.append(tool)

        if overused:
            hints.append(
                EXPLORATION_GUIDANCE_AVOID.format(
                    tools=", ".join(overused), count=self.max_repetitions
                )
            )

        if underused:
            hints.append(
                EXPLORATION_GUIDANCE_CONSIDER.format(tools=", ".join(underused[:3]))
            )

        if not hints:
            return ""

        return EXPLORATION_GUIDANCE_HEADER + "\n".join(hints)

    def get_tool_usage_summary(self) -> Dict[str, int]:
        """Get summary of tool usage counts."""
        return {tool: len(attempts) for tool, attempts in self._attempts.items()}

    def get_overused_tools(self, context_messages: List[Dict]) -> List[str]:
        """Get list of tools overused in this context.

        Args:
            context_messages: Current message context

        Returns:
            List of overused tool names
        """
        context_hash = self._hash_context(context_messages)

        overused = []
        for (tool, ctx_hash), count in self._repetition_counts.items():
            if ctx_hash == context_hash and count >= self.max_repetitions:
                overused.append(tool)

        return overused

    def get_unused_tools(
        self, available_tools: List[str], context_messages: List[Dict]
    ) -> List[str]:
        """Get list of tools not yet used in this context.

        Args:
            available_tools: List of available tool names
            context_messages: Current message context

        Returns:
            List of unused tool names
        """
        context_hash = self._hash_context(context_messages)

        unused = []
        for tool in available_tools:
            if self._repetition_counts.get((tool, context_hash), 0) == 0:
                unused.append(tool)

        return unused

    def _hash_context(self, messages: List[Dict]) -> str:
        """Create a hash of the message context."""
        # Use last 3 messages for context similarity
        recent = messages[-3:] if len(messages) > 3 else messages

        content = ""
        for msg in recent:
            role = msg.get("role", "")
            text = str(msg.get("content", ""))[:200]
            content += f"{role}:{text}"

        return hashlib.md5(content.encode()).hexdigest()[:8]

    def _hash_arguments(self, arguments: Dict) -> str:
        """Create a hash of tool arguments."""
        # Only hash key argument names for similarity
        keys = sorted(arguments.keys())
        return hashlib.md5(str(keys).encode()).hexdigest()[:8]

    def reset(self):
        """Reset all recorded state."""
        self._attempts.clear()
        self._repetition_counts.clear()
        self._context_hashes.clear()

    def get_stats(self) -> Dict:
        """Get statistics about recorded state."""
        return {
            "total_attempts": sum(len(a) for a in self._attempts.values()),
            "unique_tools": len(self._attempts),
            "unique_contexts": len(self._context_hashes),
            "tool_counts": self.get_tool_usage_summary(),
        }
