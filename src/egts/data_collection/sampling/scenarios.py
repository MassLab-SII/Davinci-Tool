"""Scenario Loader for Phase 3 complex scenarios (PRD 3.2).

This module loads predefined scenarios from the scenarios/ directory
for more complex and realistic test cases.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Any, Optional
import yaml

logger = logging.getLogger(__name__)


@dataclass
class Scenario:
    """Represents a predefined scenario for trajectory collection.

    A scenario defines a specific environment setup and expected
    behavior pattern, useful for testing complex tool interactions.
    """

    name: str
    description: str
    setup_commands: List[str] = field(default_factory=list)
    expected_tools: List[str] = field(default_factory=list)
    expected_outcome: Dict[str, Any] = field(default_factory=dict)
    difficulty: str = "medium"  # easy, medium, hard
    tags: List[str] = field(default_factory=list)
    init_files: Dict[str, str] = field(default_factory=dict)  # path -> content

    def to_dict(self) -> Dict[str, Any]:
        """Convert scenario to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "setup_commands": self.setup_commands,
            "expected_tools": self.expected_tools,
            "expected_outcome": self.expected_outcome,
            "difficulty": self.difficulty,
            "tags": self.tags,
            "init_files": self.init_files,
        }


class ScenarioLoader:
    """Loads and manages predefined scenarios from scenarios/ directory.

    Scenarios are defined as directories containing:
    - scenario.yaml: Scenario metadata and configuration
    - files/: Optional directory with files to create
    - setup.sh: Optional setup script (not executed, for documentation)
    """

    def __init__(self, scenarios_dir: Path):
        """Initialize scenario loader.

        Args:
            scenarios_dir: Path to scenarios directory
        """
        self.scenarios_dir = Path(scenarios_dir)
        self._scenarios: Dict[str, Scenario] = {}
        self._load_scenarios()

    def _load_scenarios(self):
        """Load all scenarios from directory."""
        if not self.scenarios_dir.exists():
            logger.warning(f"Scenarios directory not found: {self.scenarios_dir}")
            return

        for item in self.scenarios_dir.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                try:
                    scenario = self._load_scenario(item)
                    if scenario:
                        self._scenarios[scenario.name] = scenario
                        logger.debug(f"Loaded scenario: {scenario.name}")
                except Exception as e:
                    logger.warning(f"Failed to load scenario from {item}: {e}")

        logger.info(
            f"Loaded {len(self._scenarios)} scenarios from {self.scenarios_dir}"
        )

    def _load_scenario(self, scenario_dir: Path) -> Optional[Scenario]:
        """Load a single scenario from directory."""
        # Look for scenario.yaml or scenario.json
        yaml_file = scenario_dir / "scenario.yaml"
        json_file = scenario_dir / "scenario.json"

        if yaml_file.exists():
            with open(yaml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        elif json_file.exists():
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            # Create minimal scenario from directory name
            data = {
                "name": scenario_dir.name,
                "description": f"Scenario: {scenario_dir.name}",
            }

        # Load files from files/ subdirectory
        init_files = {}
        files_dir = scenario_dir / "files"
        if files_dir.exists():
            for file_path in files_dir.rglob("*"):
                if file_path.is_file():
                    rel_path = file_path.relative_to(files_dir)
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            init_files[str(rel_path)] = f.read()
                    except UnicodeDecodeError:
                        # Skip binary files
                        pass

        return Scenario(
            name=data.get("name", scenario_dir.name),
            description=data.get("description", ""),
            setup_commands=data.get("setup_commands", []),
            expected_tools=data.get("expected_tools", []),
            expected_outcome=data.get("expected_outcome", {}),
            difficulty=data.get("difficulty", "medium"),
            tags=data.get("tags", []),
            init_files=init_files,
        )

    def get_scenario(self, name: str) -> Optional[Scenario]:
        """Get a scenario by name."""
        return self._scenarios.get(name)

    def get_all_scenarios(self) -> List[Scenario]:
        """Get all loaded scenarios."""
        return list(self._scenarios.values())

    def get_random_scenario(
        self, difficulty: Optional[str] = None, tags: Optional[List[str]] = None
    ) -> Optional[Scenario]:
        """Get a random scenario, optionally filtered.

        Args:
            difficulty: Optional difficulty filter (easy, medium, hard)
            tags: Optional list of required tags

        Returns:
            Random matching scenario, or None if no matches
        """
        import random

        candidates = list(self._scenarios.values())

        if difficulty:
            candidates = [s for s in candidates if s.difficulty == difficulty]

        if tags:
            tag_set = set(tags)
            candidates = [s for s in candidates if tag_set & set(s.tags)]

        if not candidates:
            return None

        return random.choice(candidates)

    def get_scenarios_by_tag(self, tag: str) -> List[Scenario]:
        """Get all scenarios with a specific tag."""
        return [s for s in self._scenarios.values() if tag in s.tags]

    def get_scenarios_by_tool(self, tool_name: str) -> List[Scenario]:
        """Get all scenarios that expect a specific tool."""
        return [s for s in self._scenarios.values() if tool_name in s.expected_tools]

    async def setup_scenario(
        self, scenario: Scenario, workspace_path: Path, mcp_client=None
    ) -> bool:
        """Set up a scenario in the workspace.

        Creates files and directories defined in the scenario.

        Args:
            scenario: The scenario to set up
            workspace_path: Path to workspace directory
            mcp_client: Optional MCP client for file operations

        Returns:
            True if setup succeeded, False otherwise
        """
        try:
            workspace_path = Path(workspace_path)
            workspace_path.mkdir(parents=True, exist_ok=True)

            # Create init files
            for rel_path, content in scenario.init_files.items():
                file_path = workspace_path / rel_path
                file_path.parent.mkdir(parents=True, exist_ok=True)

                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)

                logger.debug(f"Created scenario file: {rel_path}")

            logger.info(
                f"Set up scenario '{scenario.name}' with {len(scenario.init_files)} files"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to set up scenario: {e}")
            return False


def create_example_scenarios(scenarios_dir: Path):
    """Create example scenario definitions.

    This is a helper function to bootstrap the scenarios directory
    with some example scenarios.
    """
    scenarios_dir = Path(scenarios_dir)

    # Git conflict scenario
    git_conflict_dir = scenarios_dir / "git_conflict"
    git_conflict_dir.mkdir(parents=True, exist_ok=True)

    git_conflict_scenario = {
        "name": "git_conflict",
        "description": "Resolve a simulated git merge conflict in a Python file",
        "expected_tools": ["read_file", "edit_file", "write_file"],
        "difficulty": "medium",
        "tags": ["code", "conflict", "editing"],
    }

    with open(git_conflict_dir / "scenario.yaml", "w") as f:
        yaml.dump(git_conflict_scenario, f)

    # Create example conflict file
    files_dir = git_conflict_dir / "files"
    files_dir.mkdir(exist_ok=True)

    conflict_content = """def calculate_sum(a, b):
<<<<<<< HEAD
    # Use simple addition
    return a + b
=======
    # Use numpy for better performance
    import numpy as np
    return np.add(a, b)
>>>>>>> feature-branch
"""

    with open(files_dir / "calculator.py", "w") as f:
        f.write(conflict_content)

    # Large refactor scenario
    refactor_dir = scenarios_dir / "large_refactor"
    refactor_dir.mkdir(parents=True, exist_ok=True)

    refactor_scenario = {
        "name": "large_refactor",
        "description": "Reorganize a flat project structure into proper packages",
        "expected_tools": ["create_directory", "move_file", "write_file"],
        "difficulty": "hard",
        "tags": ["organization", "refactor", "structure"],
    }

    with open(refactor_dir / "scenario.yaml", "w") as f:
        yaml.dump(refactor_scenario, f)

    logger.info(f"Created example scenarios in {scenarios_dir}")
