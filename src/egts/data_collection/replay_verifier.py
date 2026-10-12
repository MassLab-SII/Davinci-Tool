"""Replay verifier for Phase4 quality assurance.

Implements the Replay Loop:
1. Reset environment to S0
2. Agent receives synthesized problem P
3. Execute to get T_replay
4. Compare T_replay final state with T_origin final state

This provides a quality gate by verifying that the synthesized problem
description is clear enough for an agent to reproduce the original outcome.
"""

import logging
import time
import shutil
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, TYPE_CHECKING
from pathlib import Path
from enum import Enum

if TYPE_CHECKING:
    from .state.filesystem_snapshot import FilesystemSnapshot, FilesystemDiff
    from .trajs2data_collector import Trajs2DataCollector, StrictTrajectory

logger = logging.getLogger(__name__)


class ReplayResult(str, Enum):
    """Result of replay verification."""
    PASSED = "passed"                          # Replay achieved same outcome
    FAILED_DIFF_MISMATCH = "failed_diff_mismatch"  # Different final state
    FAILED_TIMEOUT = "failed_timeout"          # Replay didn't complete
    FAILED_ERROR = "failed_error"              # Error during replay
    SKIPPED = "skipped"                        # Skipped (e.g., retrieval mode)


@dataclass
class ReplayVerification:
    """Result of a replay verification attempt."""
    result: ReplayResult
    similarity_score: float = 0.0       # 0-1, how similar are outcomes
    diff_match: bool = False            # Whether filesystem diffs match
    tool_sequence_similarity: float = 0.0  # Tool call sequence similarity
    
    # Details
    origin_diff_summary: Dict[str, int] = field(default_factory=dict)
    replay_diff_summary: Dict[str, int] = field(default_factory=dict)
    mismatch_details: List[str] = field(default_factory=list)
    
    # Timing
    replay_time_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "result": self.result.value,
            "similarity_score": self.similarity_score,
            "diff_match": self.diff_match,
            "tool_sequence_similarity": self.tool_sequence_similarity,
            "origin_diff_summary": self.origin_diff_summary,
            "replay_diff_summary": self.replay_diff_summary,
            "mismatch_details": self.mismatch_details[:5],  # Truncate
            "replay_time_ms": self.replay_time_ms
        }


class ReplayVerifier:
    """Verifies synthesized problems by replaying them.
    
    The replay loop works as follows:
    1. Reset workspace to S0 state (using init_plan)
    2. Present the synthesized problem to the agent
    3. Let agent execute to produce T_replay and S1'
    4. Compare S1' with original S1 (via diff comparison)
    5. Pass if similarity >= threshold, fail otherwise
    
    This helps filter out:
    - Ambiguous problem descriptions
    - Underspecified tasks
    - Problems that don't capture the true intent
    """
    
    def __init__(
        self,
        collector: "Trajs2DataCollector",
        similarity_threshold: float = 0.8,
        max_replay_steps: int = 15
    ):
        """Initialize the replay verifier.
        
        Args:
            collector: Trajs2DataCollector for executing replay
            similarity_threshold: Minimum diff similarity for passing (0-1)
            max_replay_steps: Maximum steps allowed for replay attempt
        """
        self.collector = collector
        self.similarity_threshold = similarity_threshold
        self.max_replay_steps = max_replay_steps
    
    async def verify(
        self,
        problem_json: Dict[str, Any],
        original_trajectory: Dict[str, Any],
        original_diff: "FilesystemDiff",
        mcp_client,
        workspace_path: Path,
        init_plan  # FilesystemInitPlan for re-initializing S0
    ) -> ReplayVerification:
        """Verify a synthesized problem by replaying it.
        
        Args:
            problem_json: The synthesized problem (with 'problem', 'tools', etc.)
            original_trajectory: Original trajectory data
            original_diff: Original S0→S1 diff
            mcp_client: MCP client for tool execution
            workspace_path: Workspace path
            init_plan: Init plan for resetting to S0
            
        Returns:
            ReplayVerification with result and details
        """
        start_time = time.time()
        
        # Skip retrieval mode (no meaningful diff to compare)
        task_type = problem_json.get("task_type", "mutation")
        if task_type == "retrieval":
            return ReplayVerification(
                result=ReplayResult.SKIPPED,
                similarity_score=1.0,
                mismatch_details=["Retrieval mode - replay verification skipped"]
            )
        
        try:
            from .state.filesystem_snapshot import snapshot_filesystem, diff_snapshots
            from .state.filesystem_init_generator import execute_init_plan
            
            # Step 1: Reset to S0
            await self._reset_to_s0(mcp_client, workspace_path, init_plan)
            
            # Take S0 snapshot
            s0 = await snapshot_filesystem(
                mcp_client, 
                str(workspace_path), 
                include_content_hash=True
            )
            
            # Step 2: Execute with synthesized problem as prompt
            problem_text = problem_json.get("problem", "")
            tools = problem_json.get("tools", [])
            
            replay_trajectory = await self.collector.collect_trajectory(
                allowed_tools=tools,
                mcp_client=mcp_client,
                max_steps=self.max_replay_steps,
                system_prompt=self._build_replay_prompt(),
                initial_user_message=problem_text,
                target_n_tool_calls=None  # Let it run naturally
            )
            
            # Check if replay completed with any tool calls
            if replay_trajectory.num_successful_tool_calls == 0:
                return ReplayVerification(
                    result=ReplayResult.FAILED_TIMEOUT,
                    similarity_score=0.0,
                    mismatch_details=["Replay produced no successful tool calls"],
                    replay_time_ms=(time.time() - start_time) * 1000
                )
            
            # Step 3: Take S1' snapshot and compute diff
            s1_replay = await snapshot_filesystem(
                mcp_client, 
                str(workspace_path), 
                include_content_hash=True
            )
            replay_diff = diff_snapshots(s0, s1_replay)
            
            # Step 4: Compare diffs
            verification = self._compare_diffs(
                original_diff, 
                replay_diff, 
                replay_trajectory
            )
            verification.replay_time_ms = (time.time() - start_time) * 1000
            
            return verification
            
        except Exception as e:
            logger.error(f"Replay verification failed: {e}", exc_info=True)
            return ReplayVerification(
                result=ReplayResult.FAILED_ERROR,
                mismatch_details=[str(e)],
                replay_time_ms=(time.time() - start_time) * 1000
            )
    
    def _compare_diffs(
        self,
        origin_diff: "FilesystemDiff",
        replay_diff: "FilesystemDiff",
        replay_trajectory
    ) -> ReplayVerification:
        """Compare original and replay diffs.
        
        Args:
            origin_diff: Original S0→S1 diff
            replay_diff: Replay S0→S1' diff
            replay_trajectory: The replay trajectory
            
        Returns:
            ReplayVerification with comparison results
        """
        origin_summary = origin_diff.get_change_summary()
        replay_summary = replay_diff.get_change_summary()
        
        mismatches = []
        
        # Compare change counts
        for key in ["created", "deleted", "modified", "moved"]:
            origin_val = origin_summary.get(key, 0)
            replay_val = replay_summary.get(key, 0)
            if origin_val != replay_val:
                mismatches.append(
                    f"{key}: origin={origin_val}, replay={replay_val}"
                )
        
        # Compare affected paths (Jaccard similarity)
        origin_paths = origin_diff.get_affected_paths()
        replay_paths = replay_diff.get_affected_paths()
        
        path_intersection = origin_paths & replay_paths
        path_union = origin_paths | replay_paths
        
        if path_union:
            path_similarity = len(path_intersection) / len(path_union)
        else:
            # Both empty = perfect match
            path_similarity = 1.0 if not origin_paths and not replay_paths else 0.0
        
        # Determine result
        if not mismatches and path_similarity >= self.similarity_threshold:
            return ReplayVerification(
                result=ReplayResult.PASSED,
                similarity_score=path_similarity,
                diff_match=True,
                origin_diff_summary=origin_summary,
                replay_diff_summary=replay_summary
            )
        else:
            return ReplayVerification(
                result=ReplayResult.FAILED_DIFF_MISMATCH,
                similarity_score=path_similarity,
                diff_match=False,
                origin_diff_summary=origin_summary,
                replay_diff_summary=replay_summary,
                mismatch_details=mismatches
            )
    
    async def _reset_to_s0(self, mcp_client, workspace_path: Path, init_plan):
        """Reset workspace to S0 state.
        
        Args:
            mcp_client: MCP client for tool execution
            workspace_path: Path to workspace
            init_plan: Init plan to re-execute
        """
        from .state.filesystem_init_generator import execute_init_plan
        
        # Clear workspace
        for item in workspace_path.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        
        # Re-execute init plan
        await execute_init_plan(init_plan, mcp_client)
    
    def _build_replay_prompt(self) -> str:
        """Build system prompt for replay execution."""
        return """You are a helpful assistant that uses filesystem tools to accomplish tasks.
Please complete the task described by the user using the available tools.
Focus on achieving the goal efficiently and accurately.
Each response should include tool calls to make progress on the task."""


def compute_tool_sequence_similarity(
    origin_tools: List[str],
    replay_tools: List[str]
) -> float:
    """Compute similarity between two tool call sequences.
    
    Uses a simple set-based Jaccard similarity.
    More sophisticated methods could use edit distance or LCS.
    
    Args:
        origin_tools: List of tool names from original trajectory
        replay_tools: List of tool names from replay trajectory
        
    Returns:
        Similarity score between 0 and 1
    """
    if not origin_tools and not replay_tools:
        return 1.0
    
    origin_set = set(origin_tools)
    replay_set = set(replay_tools)
    
    intersection = origin_set & replay_set
    union = origin_set | replay_set
    
    return len(intersection) / len(union) if union else 0.0
