"""Filesystem initialization generator for mcp-trajs2data.

Generates realistic initial filesystem environments with seed-based reproducibility.
"""

import logging
import random
import string
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)


class SizeProfile(str, Enum):
    """Size profiles for generated environments."""

    TINY = "tiny"  # 5-10 files, 1-2 dirs
    SMALL = "small"  # 10-20 files, 2-4 dirs
    MEDIUM = "medium"  # 20-40 files, 4-8 dirs
    LARGE = "large"  # 40-80 files, 8-16 dirs


@dataclass
class FileSpec:
    """Specification for a file to be created."""

    path: str
    content: str

    def to_init_operation(self) -> Dict[str, Any]:
        """Convert to initialization operation format."""
        return {
            "tool": "write_file",
            "arguments": {"path": self.path, "content": self.content},
        }


@dataclass
class DirectorySpec:
    """Specification for a directory to be created."""

    path: str

    def to_init_operation(self) -> Dict[str, Any]:
        """Convert to initialization operation format."""
        return {"tool": "create_directory", "arguments": {"path": self.path}}


@dataclass
class InitPlan:
    """Plan for initializing a filesystem environment."""

    root: str
    directories: List[DirectorySpec] = field(default_factory=list)
    files: List[FileSpec] = field(default_factory=list)
    seed: int = 0
    size_profile: SizeProfile = SizeProfile.SMALL
    scenario_ops: List[Dict[str, Any]] = field(
        default_factory=list
    )  # Phase 3 Scenario Ops

    def to_operations(self) -> List[Dict[str, Any]]:
        """Convert to list of initialization operations.

        Returns operations in correct order: directories first, then files, then scenario ops.
        """
        operations = []

        # Sort directories by depth (parent dirs first)
        sorted_dirs = sorted(self.directories, key=lambda d: d.path.count("/"))
        for dir_spec in sorted_dirs:
            operations.append(dir_spec.to_init_operation())

        for file_spec in self.files:
            operations.append(file_spec.to_init_operation())

        # Append scenario operations (Phase 3)
        if self.scenario_ops:
            operations.extend(self.scenario_ops)

        return operations

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of the init plan."""
        return {
            "root": self.root,
            "seed": self.seed,
            "size_profile": self.size_profile.value,
            "num_directories": len(self.directories),
            "num_files": len(self.files),
            "total_operations": len(self.directories) + len(self.files),
        }


# Realistic file/folder name templates
FOLDER_THEMES = {
    "documents": ["documents", "docs", "papers", "reports", "notes"],
    "projects": ["projects", "work", "assignments", "tasks"],
    "media": ["images", "photos", "pictures", "screenshots", "media"],
    "data": ["data", "datasets", "exports", "downloads", "archives"],
    "code": ["src", "code", "scripts", "lib"],
    "misc": ["misc", "temp", "backup", "old", "archive"],
}

FILE_TEMPLATES = {
    "text": {
        "extensions": [".txt", ".md", ".log"],
        "name_patterns": ["notes", "readme", "todo", "draft", "summary", "report"],
        "content_generator": "_generate_text_content",
    },
    "data": {
        "extensions": [".csv", ".json", ".yaml"],
        "name_patterns": ["data", "config", "settings", "export", "records"],
        "content_generator": "_generate_data_content",
    },
    "code": {
        "extensions": [".py", ".js", ".sh"],
        "name_patterns": ["main", "utils", "helper", "script", "process"],
        "content_generator": "_generate_code_content",
    },
    "media": {
        "extensions": [".png", ".jpg", ".svg"],
        "name_patterns": ["logo", "icon", "banner", "screenshot", "diagram", "photo"],
        "content_generator": "_generate_media_content",
    },
}

# Sample realistic content snippets
TEXT_SNIPPETS = [
    "Meeting notes from {date}",
    "TODO: Review the quarterly report",
    "Project update - Phase {num} complete",
    "Draft document for review",
    "Summary of findings",
    "Important: Please review before {date}",
    "Notes on {topic}",
    "Research findings and analysis",
]

DATA_TOPICS = [
    "users",
    "products",
    "sales",
    "inventory",
    "logs",
    "metrics",
    "events",
    "transactions",
    "reports",
    "analytics",
]

CODE_SNIPPETS = [
    '# Script for processing {topic}\n\ndef main():\n    print("Processing {topic}")\n\nif __name__ == "__main__":\n    main()',
    '#!/bin/bash\n# {topic} script\necho "Running {topic} task"',
    '// {topic} utilities\nfunction process{topic}() {{\n    console.log("Processing {topic}");\n}}',
]


class FilesystemInitGenerator:
    """Generator for creating realistic filesystem initialization plans."""

    def __init__(self, seed: Optional[int] = None):
        """Initialize the generator.

        Args:
            seed: Random seed for reproducibility
        """
        self.seed = seed if seed is not None else random.randint(0, 2**32 - 1)
        self.rng = random.Random(self.seed)

    def generate_init_plan(
        self, root: str, size_profile: SizeProfile = SizeProfile.SMALL
    ) -> InitPlan:
        """Generate an initialization plan for a filesystem environment.

        Args:
            root: Root directory path
            size_profile: Size profile for the environment

        Returns:
            InitPlan with directories and files to create
        """
        plan = InitPlan(root=root, seed=self.seed, size_profile=size_profile)

        # Determine sizes based on profile
        size_config = self._get_size_config(size_profile)

        # Generate directory structure
        directories = self._generate_directories(root, size_config)
        plan.directories = directories

        # Generate files
        all_dirs = [root] + [d.path for d in directories]
        files = self._generate_files(all_dirs, size_config)
        plan.files = files

        logger.info(f"Generated init plan: {plan.get_summary()}")
        return plan

    def _get_size_config(self, profile: SizeProfile) -> Dict[str, Tuple[int, int]]:
        """Get size configuration for a profile."""
        configs = {
            SizeProfile.TINY: {"dirs": (1, 2), "files_per_dir": (2, 4), "max_depth": 1},
            SizeProfile.SMALL: {
                "dirs": (2, 4),
                "files_per_dir": (3, 6),
                "max_depth": 2,
            },
            SizeProfile.MEDIUM: {
                "dirs": (4, 8),
                "files_per_dir": (4, 8),
                "max_depth": 3,
            },
            SizeProfile.LARGE: {
                "dirs": (8, 16),
                "files_per_dir": (5, 10),
                "max_depth": 4,
            },
        }
        return configs[profile]

    def _generate_directories(
        self, root: str, size_config: Dict[str, Any]
    ) -> List[DirectorySpec]:
        """Generate directory structure."""
        directories = []

        min_dirs, max_dirs = size_config["dirs"]
        num_dirs = self.rng.randint(min_dirs, max_dirs)
        max_depth = size_config["max_depth"]

        # Select themes for this environment
        available_themes = list(FOLDER_THEMES.keys())
        self.rng.shuffle(available_themes)
        themes_to_use = available_themes[: min(num_dirs, len(available_themes))]

        current_dirs = [root]

        for i in range(num_dirs):
            # Choose parent directory
            parent = self.rng.choice(current_dirs)
            parent_depth = parent.count("/") - root.count("/")

            # Limit depth
            if parent_depth >= max_depth:
                parent = root

            # Generate directory name
            if i < len(themes_to_use):
                theme = themes_to_use[i]
                name = self.rng.choice(FOLDER_THEMES[theme])
            else:
                # Use random name
                name = f"folder_{self.rng.randint(1, 99):02d}"

            # Avoid duplicates
            dir_path = str(Path(parent) / name)
            if dir_path not in [d.path for d in directories]:
                directories.append(DirectorySpec(path=dir_path))
                current_dirs.append(dir_path)

        return directories

    def _generate_files(
        self, directories: List[str], size_config: Dict[str, Any]
    ) -> List[FileSpec]:
        """Generate files across directories."""
        files = []

        min_files, max_files = size_config["files_per_dir"]

        for directory in directories:
            num_files = self.rng.randint(min_files, max_files)

            for _ in range(num_files):
                file_spec = self._generate_single_file(directory)

                # Avoid duplicate paths
                if file_spec.path not in [f.path for f in files]:
                    files.append(file_spec)

        return files

    def _generate_single_file(self, directory: str) -> FileSpec:
        """Generate a single file specification."""
        # Choose file type
        file_type = self.rng.choice(list(FILE_TEMPLATES.keys()))
        template = FILE_TEMPLATES[file_type]

        # Generate name
        name_base = self.rng.choice(template["name_patterns"])
        # Add optional suffix for uniqueness
        if self.rng.random() > 0.5:
            name_base += f"_{self.rng.randint(1, 99):02d}"

        extension = self.rng.choice(template["extensions"])
        filename = name_base + extension

        # Generate content
        content = self._generate_content(file_type)

        return FileSpec(path=str(Path(directory) / filename), content=content)

    def _generate_content(self, file_type: str) -> str:
        """Generate realistic file content."""
        if file_type == "text":
            return self._generate_text_content()
        elif file_type == "data":
            return self._generate_data_content()
        elif file_type == "code":
            return self._generate_code_content()
        elif file_type == "media":
            return self._generate_media_content()
        else:
            return "Sample content"

    def _generate_text_content(self) -> str:
        """Generate text file content."""
        num_lines = self.rng.randint(3, 15)
        lines = []

        for _ in range(num_lines):
            template = self.rng.choice(TEXT_SNIPPETS)
            line = template.format(
                date=f"2024-{self.rng.randint(1, 12):02d}-{self.rng.randint(1, 28):02d}",
                num=self.rng.randint(1, 5),
                topic=self.rng.choice(DATA_TOPICS),
            )
            lines.append(line)

        return "\n".join(lines)

    def _generate_data_content(self) -> str:
        """Generate data file content (CSV or JSON)."""
        if self.rng.random() > 0.5:
            # CSV
            headers = ["id", "name", "value", "status"]
            rows = [",".join(headers)]

            for i in range(self.rng.randint(5, 20)):
                row = [
                    str(i + 1),
                    f"item_{i + 1}",
                    str(self.rng.randint(10, 1000)),
                    self.rng.choice(["active", "pending", "completed"]),
                ]
                rows.append(",".join(row))

            return "\n".join(rows)
        else:
            # JSON
            import json

            data = {
                "name": f"dataset_{self.rng.randint(1, 100)}",
                "version": f"1.{self.rng.randint(0, 9)}",
                "items": [
                    {"id": i, "value": self.rng.randint(10, 100)}
                    for i in range(self.rng.randint(3, 10))
                ],
            }
            return json.dumps(data, indent=2)

    def _generate_code_content(self) -> str:
        """Generate code file content."""
        template = self.rng.choice(CODE_SNIPPETS)
        topic = self.rng.choice(DATA_TOPICS).capitalize()
        return template.format(topic=topic)

    def _generate_media_content(self) -> str:
        """Generate media file content (base64 encoded minimal valid images)."""
        media_type = self.rng.choice(["png", "svg"])

        if media_type == "svg":
            colors = ["#3498db", "#e74c3c", "#2ecc71", "#f39c12", "#9b59b6", "#1abc9c"]
            color = self.rng.choice(colors)
            size = self.rng.randint(50, 200)
            shape = self.rng.choice(["rect", "circle"])

            if shape == "circle":
                return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}">
  <circle cx="{size // 2}" cy="{size // 2}" r="{size // 2 - 5}" fill="{color}"/>
</svg>'''
            else:
                return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}">
  <rect width="{size}" height="{size}" fill="{color}"/>
</svg>'''
        else:
            import base64

            png_1x1_red = base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
            )
            return base64.b64encode(png_1x1_red).decode("ascii")


def generate_seed_env(
    root: str, seed: Optional[int] = None, size_profile: SizeProfile = SizeProfile.SMALL
) -> InitPlan:
    """Convenience function to generate an initialization plan.

    Args:
        root: Root directory path
        seed: Random seed for reproducibility (None for random)
        size_profile: Size profile for the environment

    Returns:
        InitPlan with directories and files
    """
    generator = FilesystemInitGenerator(seed=seed)
    return generator.generate_init_plan(root, size_profile)


def init_plan_to_operations(init_plan: InitPlan) -> List[Dict[str, Any]]:
    """Convert InitPlan to list of MCP tool operations.

    This is the format used in problem.json.initialization.
    """
    return init_plan.to_operations()


async def execute_init_plan(init_plan: InitPlan, mcp_client) -> List[Dict[str, Any]]:
    """Execute an initialization plan using MCP tools.

    Args:
        init_plan: The initialization plan to execute
        mcp_client: MCP client for tool execution

    Returns:
        List of execution results
    """
    results = []
    operations = init_plan.to_operations()

    for i, op in enumerate(operations):
        tool_name = op["tool"]
        arguments = op["arguments"]

        logger.debug(
            f"Init {i + 1}/{len(operations)}: {tool_name} - {arguments.get('path', '')}"
        )

        try:
            result = await mcp_client.call_tool(tool_name, arguments)
            results.append({"operation": op, "success": True, "result": str(result)})
            logger.debug(f"✓ Init {i + 1} succeeded")
        except Exception as e:
            logger.error(f"✗ Init {i + 1} failed: {e}")
            results.append({"operation": op, "success": False, "error": str(e)})
            # Continue with other operations

    success_count = sum(1 for r in results if r["success"])
    logger.info(
        f"Init plan executed: {success_count}/{len(operations)} operations succeeded"
    )

    return results
