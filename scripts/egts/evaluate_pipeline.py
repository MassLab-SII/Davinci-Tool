#!/usr/bin/env python3
"""Pipeline evaluation script for mcp-trajs2data.

Evaluates data synthesis quality across multiple dimensions:
1. Yield Rate: saved_episodes / attempted_episodes
2. Tool Coverage: % of tools successfully used at least min_success times
3. Problem Diversity: unique_problems / total_saved (inverse repetition rate)
4. Failure Analysis: failure distribution by tool and reason

Usage:
    python scripts/egts/evaluate_pipeline.py --exp-dir output/trajs2data_exp
    python scripts/egts/evaluate_pipeline.py --exp-dir output/trajs2data_exp --phase phase1
"""

import argparse
import json
import logging
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_statistics(exp_dir: Path) -> Optional[Dict[str, Any]]:
    """Load statistics.json from experiment directory."""
    stats_path = exp_dir / "statistics.json"
    if not stats_path.exists():
        logger.warning(f"No statistics.json found at {stats_path}")
        return None
    
    with open(stats_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _find_namespace_dirs(exp_dir: Path) -> List[Path]:
    """Return namespace directories that contain trajs2data artifacts."""
    namespaces: List[Path] = []
    if not exp_dir.exists():
        return namespaces

    for child in exp_dir.iterdir():
        if not child.is_dir():
            continue
        if any((child / subdir).exists() for subdir in ["trajs2data", "trajs2data_raw", "trajs2data_filtered"]):
            namespaces.append(child)
    return namespaces
def load_coverage(exp_dir: Path) -> Optional[Dict[str, Any]]:
    """Load coverage.json from experiment directory or namespace subdirectories."""
    candidate_paths = [exp_dir / "coverage.json"]
    candidate_paths.extend(ns / "coverage.json" for ns in _find_namespace_dirs(exp_dir))

    for coverage_path in candidate_paths:
        if coverage_path.exists():
            with open(coverage_path, 'r', encoding='utf-8') as f:
                return json.load(f)

    logger.warning(f"No coverage.json found in {exp_dir}")
    return None


def load_quality_report(exp_dir: Path) -> Optional[Dict[str, Any]]:
    """Load quality_report.json if available."""
    report_path = exp_dir / "quality_report.json"
    if report_path.exists():
        with open(report_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def analyze_trajectories(exp_dir: Path, phase_filter: Optional[str] = None) -> Dict[str, Any]:
    """Analyze saved trajectories for diversity and patterns across all namespaces."""
    namespace_dirs = _find_namespace_dirs(exp_dir)

    if not namespace_dirs:
        logger.warning(f"No trajs2data namespace directories found at {exp_dir}")
        return {}

    problems: List[str] = []
    problem_hashes: List[str] = []
    task_types: Counter = Counter()
    tool_sequences: List[List[str]] = []
    phases: Counter = Counter()
    target_ns: List[int] = []
    actual_ns: List[int] = []
    namespace_counts: Counter = Counter()

    for namespace_dir in namespace_dirs:
        trajs_dir = namespace_dir / "trajs2data"
        if not trajs_dir.exists():
            continue

        for entry_dir in trajs_dir.iterdir():
            if not entry_dir.is_dir():
                continue

            metadata_path = entry_dir / "metadata.json"
            problem_path = entry_dir / "problem.json"
            trajectory_path = entry_dir / "trajectory.json"

            if not all(p.exists() for p in [metadata_path, problem_path, trajectory_path]):
                continue

            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                with open(problem_path, 'r', encoding='utf-8') as f:
                    problem_data = json.load(f)
                with open(trajectory_path, 'r', encoding='utf-8') as f:
                    trajectory = json.load(f)
            except Exception as e:
                logger.warning(f"Error loading {entry_dir}: {e}")
                continue

            entry_phase = metadata.get("phase", "")
            if phase_filter and phase_filter not in entry_phase:
                continue

            problems.append(problem_data.get("problem", ""))
            task_types[problem_data.get("task_type", "unknown")] += 1
            phases[entry_phase] += 1
            namespace_counts[metadata.get("output_namespace") or namespace_dir.name] += 1

            tool_calls = trajectory.get("tool_calls", [])
            tool_seq = [tc.get("tool_name", tc.get("name", "unknown")) for tc in tool_calls]
            tool_sequences.append(tool_seq)

            target_n = metadata.get("target_n", 0)
            actual_n = len([tc for tc in tool_calls if tc.get("success", True)])
            target_ns.append(target_n)
            actual_ns.append(actual_n)

    unique_problems = len(set(problems))
    total_problems = len(problems)

    import hashlib
    for p in problems:
        normalized = " ".join(p.lower().strip().split())
        h = hashlib.md5(normalized.encode()).hexdigest()[:16]
        problem_hashes.append(h)

    hash_counts = Counter(problem_hashes)

    tool_counts: Counter = Counter()
    for seq in tool_sequences:
        tool_counts.update(seq)

    return {
        "total_saved": total_problems,
        "unique_problems": unique_problems,
        "diversity_ratio": unique_problems / total_problems if total_problems > 0 else 0.0,
        "repetition_rate": 1 - (unique_problems / total_problems) if total_problems > 0 else 0.0,
        "task_type_distribution": dict(task_types),
        "phase_distribution": dict(phases),
        "output_namespace_distribution": dict(namespace_counts),
        "avg_target_n": sum(target_ns) / len(target_ns) if target_ns else 0.0,
        "avg_actual_n": sum(actual_ns) / len(actual_ns) if actual_ns else 0.0,
        "n_achievement_rate": (
            sum(1 for t, a in zip(target_ns, actual_ns) if a >= t) / len(target_ns)
            if target_ns else 0.0
        ),
        "top_repeated_problems": hash_counts.most_common(10),
        "tool_usage_distribution": dict(tool_counts.most_common(20)),
        "total_tool_calls": sum(len(seq) for seq in tool_sequences),
        "avg_tools_per_trajectory": (
            sum(len(seq) for seq in tool_sequences) / len(tool_sequences)
            if tool_sequences else 0.0
        )
    }


def compute_coverage_metrics(coverage_data: Dict[str, Any]) -> Dict[str, Any]:
    """Compute coverage metrics from coverage.json."""
    tools = coverage_data.get("tools", {})
    min_success = coverage_data.get("min_success_per_tool", 10)
    
    total_tools = len(tools)
    covered_tools = sum(
        1 for t in tools.values()
        if t.get("success_count", 0) >= min_success
    )
    
    success_counts = [t.get("success_count", 0) for t in tools.values()]
    failure_counts = [t.get("failure_count", 0) for t in tools.values()]
    
    # Identify underused tools
    underused = [
        name for name, data in tools.items()
        if data.get("success_count", 0) < min_success
    ]
    
    # Identify never-used tools
    never_used = [
        name for name, data in tools.items()
        if data.get("success_count", 0) == 0
    ]
    
    return {
        "total_tools": total_tools,
        "covered_tools": covered_tools,
        "coverage_rate": covered_tools / total_tools if total_tools > 0 else 0.0,
        "min_success_threshold": min_success,
        "total_successes": sum(success_counts),
        "total_failures": sum(failure_counts),
        "avg_successes_per_tool": sum(success_counts) / total_tools if total_tools > 0 else 0.0,
        "underused_tools": underused[:10],
        "underused_count": len(underused),
        "never_used_tools": never_used[:10],
        "never_used_count": len(never_used),
        "success_distribution": {
            "min": min(success_counts) if success_counts else 0,
            "max": max(success_counts) if success_counts else 0,
            "median": sorted(success_counts)[len(success_counts)//2] if success_counts else 0
        }
    }


def generate_report(
    exp_dir: Path,
    phase_filter: Optional[str] = None
) -> Dict[str, Any]:
    """Generate comprehensive evaluation report."""
    report = {
        "experiment_dir": str(exp_dir),
        "phase_filter": phase_filter,
        "generated_at": datetime.now().isoformat()
    }
    
    # Load and process statistics
    stats = load_statistics(exp_dir)
    if stats:
        report["statistics"] = {
            "total_attempted": stats.get("trajs2data_total", 0),
            "valid_saved": stats.get("trajs2data_valid", 0),
            "filtered_out": stats.get("trajs2data_filtered", 0),
            "deduplicated": stats.get("trajs2data_deduplicated", 0),
            "salvaged": stats.get("trajs2data_salvaged", 0),
            "yield_rate": stats.get("trajs2data_success_rate", 0.0),
            "unique_problems": stats.get("unique_problems", 0)
        }
        
        # Failure analysis if available
        if "failure_by_tool" in stats:
            report["failure_analysis"] = {
                "total_tool_failures": stats.get("total_tool_failures", 0),
                "avg_failures_per_episode": stats.get("avg_failures_per_episode", 0.0),
                "top_failing_tools": sorted(
                    stats.get("failure_by_tool", {}).items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:10],
                "failure_reasons": stats.get("failure_by_reason", {})
            }
    
    # Load and process coverage
    coverage = load_coverage(exp_dir)
    if coverage:
        report["coverage"] = compute_coverage_metrics(coverage)
    
    # Analyze trajectories
    trajectory_analysis = analyze_trajectories(exp_dir, phase_filter)
    if trajectory_analysis:
        report["trajectory_analysis"] = trajectory_analysis
    
    # Load quality report if available
    quality = load_quality_report(exp_dir)
    if quality:
        report["quality_report"] = quality
    
    # Compute summary scores
    report["summary_scores"] = compute_summary_scores(report)
    
    return report


def compute_summary_scores(report: Dict[str, Any]) -> Dict[str, Any]:
    """Compute summary scores from report data."""
    scores = {}
    
    # Yield score (0-100)
    stats = report.get("statistics", {})
    yield_rate = stats.get("yield_rate", 0.0)
    scores["yield_score"] = min(100, yield_rate * 100)
    
    # Coverage score (0-100)
    coverage = report.get("coverage", {})
    coverage_rate = coverage.get("coverage_rate", 0.0)
    scores["coverage_score"] = coverage_rate * 100
    
    # Diversity score (0-100)
    traj = report.get("trajectory_analysis", {})
    diversity_ratio = traj.get("diversity_ratio", 0.0)
    scores["diversity_score"] = diversity_ratio * 100
    
    # Efficiency score (based on n achievement)
    n_achievement = traj.get("n_achievement_rate", 0.0)
    scores["efficiency_score"] = n_achievement * 100
    
    # Overall score (weighted average)
    scores["overall_score"] = (
        0.3 * scores["yield_score"] +
        0.3 * scores["coverage_score"] +
        0.2 * scores["diversity_score"] +
        0.2 * scores["efficiency_score"]
    )
    
    return scores


def print_report(report: Dict[str, Any]):
    """Print report to console."""
    print("\n" + "="*70)
    print("MCP-TRAJS2DATA PIPELINE EVALUATION REPORT")
    print("="*70)
    print(f"Experiment: {report['experiment_dir']}")
    print(f"Phase Filter: {report.get('phase_filter', 'None')}")
    print(f"Generated: {report['generated_at']}")
    
    # Statistics
    stats = report.get("statistics", {})
    if stats:
        print("\n--- YIELD METRICS ---")
        print(f"Total Attempted: {stats.get('total_attempted', 0)}")
        print(f"Valid Saved: {stats.get('valid_saved', 0)}")
        print(f"Filtered Out: {stats.get('filtered_out', 0)}")
        print(f"Deduplicated: {stats.get('deduplicated', 0)}")
        print(f"Salvaged: {stats.get('salvaged', 0)}")
        print(f"Yield Rate: {stats.get('yield_rate', 0.0):.2%}")
    
    # Coverage
    coverage = report.get("coverage", {})
    if coverage:
        print("\n--- COVERAGE METRICS ---")
        print(f"Total Tools: {coverage.get('total_tools', 0)}")
        print(f"Covered Tools: {coverage.get('covered_tools', 0)}")
        print(f"Coverage Rate: {coverage.get('coverage_rate', 0.0):.2%}")
        print(f"Never Used: {coverage.get('never_used_count', 0)}")
        if coverage.get('never_used_tools'):
            print(f"  Examples: {coverage['never_used_tools'][:5]}")
    
    # Trajectory Analysis
    traj = report.get("trajectory_analysis", {})
    if traj:
        print("\n--- DIVERSITY METRICS ---")
        print(f"Total Saved: {traj.get('total_saved', 0)}")
        print(f"Unique Problems: {traj.get('unique_problems', 0)}")
        print(f"Diversity Ratio: {traj.get('diversity_ratio', 0.0):.2%}")
        print(f"Repetition Rate: {traj.get('repetition_rate', 0.0):.2%}")
        print(f"Avg Tools per Trajectory: {traj.get('avg_tools_per_trajectory', 0.0):.1f}")
        print(f"Target N Achievement: {traj.get('n_achievement_rate', 0.0):.2%}")
        
        if traj.get("task_type_distribution"):
            print(f"Task Types: {traj['task_type_distribution']}")
        if traj.get("phase_distribution"):
            print(f"Phase Distribution: {traj['phase_distribution']}")
    
    # Failure Analysis
    failure = report.get("failure_analysis", {})
    if failure:
        print("\n--- FAILURE ANALYSIS ---")
        print(f"Total Tool Failures: {failure.get('total_tool_failures', 0)}")
        print(f"Avg Failures per Episode: {failure.get('avg_failures_per_episode', 0.0):.2f}")
        if failure.get("top_failing_tools"):
            print("Top Failing Tools:")
            for tool, count in failure["top_failing_tools"][:5]:
                print(f"  - {tool}: {count}")
    
    # Summary Scores
    scores = report.get("summary_scores", {})
    if scores:
        print("\n--- SUMMARY SCORES (0-100) ---")
        print(f"Yield Score: {scores.get('yield_score', 0):.1f}")
        print(f"Coverage Score: {scores.get('coverage_score', 0):.1f}")
        print(f"Diversity Score: {scores.get('diversity_score', 0):.1f}")
        print(f"Efficiency Score: {scores.get('efficiency_score', 0):.1f}")
        print(f"Overall Score: {scores.get('overall_score', 0):.1f}")
    
    print("\n" + "="*70)


def main():
    parser = argparse.ArgumentParser(description="Evaluate mcp-trajs2data pipeline output")
    parser.add_argument(
        "--exp-dir", 
        type=str, 
        required=True,
        help="Path to experiment directory"
    )
    parser.add_argument(
        "--phase",
        type=str,
        default=None,
        help="Filter by phase (e.g., 'phase1', 'phase2')"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output path for JSON report (optional)"
    )
    
    args = parser.parse_args()
    
    exp_dir = Path(args.exp_dir)
    if not exp_dir.exists():
        logger.error(f"Experiment directory not found: {exp_dir}")
        sys.exit(1)
    
    # Generate report
    report = generate_report(exp_dir, args.phase)
    
    # Print to console
    print_report(report)
    
    # Save to file if requested
    if args.output:
        output_path = Path(args.output)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        logger.info(f"Report saved to {output_path}")


if __name__ == "__main__":
    main()
