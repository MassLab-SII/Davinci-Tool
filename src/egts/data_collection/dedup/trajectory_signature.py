"""Trajectory signature computation for deduplication.

Computes a signature that captures the essential "shape" of a trajectory,
allowing us to determine if two trajectories are meaningfully different
even if they solve the same problem.

Different trajectories for the same problem = valuable data diversity.
Same problem + same trajectory = true duplicate, should be filtered.
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Set, Tuple


@dataclass
class TrajectorySignature:
    """Signature capturing the essential characteristics of a trajectory.
    
    Two trajectories with different signatures are considered meaningfully
    different, even if they address the same problem.
    """
    # Tool sequence: ordered list of tool names called
    tool_sequence: List[str] = field(default_factory=list)
    
    # Key argument patterns: what types of arguments were used
    # Format: tool_name -> sorted list of argument keys
    argument_patterns: Dict[str, List[str]] = field(default_factory=dict)
    
    # Diff summary: what kind of changes were made
    # e.g., ["create_file", "edit_file", "delete"]
    diff_actions: List[str] = field(default_factory=list)
    
    # Affected paths (normalized): relative paths affected
    affected_paths: List[str] = field(default_factory=list)
    
    # Success pattern: sequence of success/failure
    success_pattern: List[bool] = field(default_factory=list)
    
    # Computed hash for quick comparison
    _hash: Optional[str] = None
    
    @classmethod
    def from_trajectory(
        cls, 
        trajectory: Dict[str, Any],
        diff: Optional[Dict[str, Any]] = None,
        normalize_paths: bool = True
    ) -> "TrajectorySignature":
        """Create signature from trajectory data.
        
        Args:
            trajectory: Trajectory dict with tool_calls, messages, etc.
            diff: Optional filesystem diff for change analysis
            normalize_paths: Whether to normalize paths (remove root prefix)
            
        Returns:
            TrajectorySignature instance
        """
        sig = cls()
        
        # Extract tool call information
        tool_calls = trajectory.get("tool_calls", [])
        
        for tc in tool_calls:
            if isinstance(tc, dict):
                name = tc.get("tool_name", tc.get("name", "unknown"))
                args = tc.get("arguments", {})
                success = tc.get("success", True)
                
                sig.tool_sequence.append(name)
                sig.success_pattern.append(success)
                
                # Capture argument pattern
                if isinstance(args, dict):
                    arg_keys = sorted(args.keys())
                    if name not in sig.argument_patterns:
                        sig.argument_patterns[name] = []
                    # Only add unique patterns
                    pattern_str = ",".join(arg_keys)
                    if pattern_str not in sig.argument_patterns[name]:
                        sig.argument_patterns[name].append(pattern_str)
        
        # Sort argument patterns for consistency
        for name in sig.argument_patterns:
            sig.argument_patterns[name] = sorted(set(sig.argument_patterns[name]))
        
        # Extract diff information if available
        if diff:
            sig.diff_actions = cls._extract_diff_actions(diff)
            sig.affected_paths = cls._extract_affected_paths(diff, normalize_paths)
        
        return sig
    
    @staticmethod
    def _extract_diff_actions(diff: Dict[str, Any]) -> List[str]:
        """Extract action types from diff."""
        actions = []
        
        if diff.get("created"):
            # Check if files or directories
            for entry in diff["created"]:
                if isinstance(entry, dict):
                    info = entry.get("new_info", {})
                    if info.get("is_directory"):
                        actions.append("create_dir")
                    else:
                        actions.append("create_file")
                else:
                    actions.append("create")
        
        if diff.get("deleted"):
            actions.append("delete")
        
        if diff.get("modified"):
            actions.append("edit")
        
        if diff.get("moved"):
            actions.append("move")
        
        return sorted(set(actions))
    
    @staticmethod
    def _extract_affected_paths(
        diff: Dict[str, Any], 
        normalize: bool = True
    ) -> List[str]:
        """Extract affected paths from diff."""
        paths = set()
        
        for change_type in ["created", "deleted", "modified", "moved"]:
            entries = diff.get(change_type, [])
            for entry in entries:
                if isinstance(entry, dict):
                    path = entry.get("path", "")
                    if path:
                        if normalize:
                            # Just keep filename or last path component
                            path = path.split("/")[-1] if "/" in path else path
                        paths.add(path)
        
        return sorted(paths)[:20]  # Limit to prevent huge signatures
    
    def compute_hash(self) -> str:
        """Compute a hash representing this signature."""
        if self._hash is not None:
            return self._hash
        
        # Build canonical string representation
        parts = [
            # Tool sequence
            "|".join(self.tool_sequence),
            # Argument patterns
            json.dumps(self.argument_patterns, sort_keys=True),
            # Diff actions
            ",".join(self.diff_actions),
            # Success pattern (compact)
            "".join("1" if s else "0" for s in self.success_pattern)
        ]
        
        signature_str = "||".join(parts)
        self._hash = hashlib.md5(signature_str.encode('utf-8')).hexdigest()
        return self._hash
    
    def is_similar_to(
        self, 
        other: "TrajectorySignature",
        tool_sequence_threshold: float = 0.7
    ) -> bool:
        """Check if this signature is similar to another.
        
        Args:
            other: Another signature to compare
            tool_sequence_threshold: Jaccard similarity threshold for tool sequences
            
        Returns:
            True if signatures are similar (should be deduplicated)
        """
        # Quick check: if hashes are equal, definitely similar
        if self.compute_hash() == other.compute_hash():
            return True
        
        # Check tool sequence similarity
        set1 = set(self.tool_sequence)
        set2 = set(other.tool_sequence)
        
        if not set1 or not set2:
            return False
        
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        jaccard = intersection / union if union > 0 else 0.0
        
        if jaccard < tool_sequence_threshold:
            return False
        
        # Check if same diff actions
        if set(self.diff_actions) != set(other.diff_actions):
            return False
        
        # If same tools, same actions, consider similar
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "tool_sequence": self.tool_sequence,
            "argument_patterns": self.argument_patterns,
            "diff_actions": self.diff_actions,
            "affected_paths": self.affected_paths,
            "success_pattern": self.success_pattern,
            "hash": self.compute_hash()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrajectorySignature":
        """Create from dictionary."""
        sig = cls(
            tool_sequence=data.get("tool_sequence", []),
            argument_patterns=data.get("argument_patterns", {}),
            diff_actions=data.get("diff_actions", []),
            affected_paths=data.get("affected_paths", []),
            success_pattern=data.get("success_pattern", [])
        )
        sig._hash = data.get("hash")
        return sig


def compute_trajectory_similarity(
    sig1: TrajectorySignature,
    sig2: TrajectorySignature
) -> float:
    """Compute similarity score between two trajectory signatures.
    
    Returns a score from 0.0 (completely different) to 1.0 (identical).
    """
    # Hash match = identical
    if sig1.compute_hash() == sig2.compute_hash():
        return 1.0
    
    # Tool sequence Jaccard
    set1 = set(sig1.tool_sequence)
    set2 = set(sig2.tool_sequence)
    
    if not set1 or not set2:
        tool_sim = 0.0
    else:
        tool_sim = len(set1 & set2) / len(set1 | set2)
    
    # Diff action match
    action_sim = 1.0 if set(sig1.diff_actions) == set(sig2.diff_actions) else 0.5
    
    # Affected path overlap
    path_set1 = set(sig1.affected_paths)
    path_set2 = set(sig2.affected_paths)
    
    if not path_set1 or not path_set2:
        path_sim = 0.0
    else:
        path_sim = len(path_set1 & path_set2) / len(path_set1 | path_set2)
    
    # Success pattern match
    if len(sig1.success_pattern) == len(sig2.success_pattern):
        matches = sum(1 for a, b in zip(sig1.success_pattern, sig2.success_pattern) if a == b)
        success_sim = matches / len(sig1.success_pattern) if sig1.success_pattern else 0.0
    else:
        success_sim = 0.0
    
    # Weighted combination
    return (
        0.4 * tool_sim +
        0.2 * action_sim +
        0.2 * path_sim +
        0.2 * success_sim
    )
