"""Experience Manager module for experience extraction and retrieval (PRD 4.7).

This module provides functionality for:
- Extracting reusable experiences from successful trajectories
- Storing experiences with deduplication
- Retrieving relevant experience for exploration prompts
"""

from .experience_store import Experience, ExperienceStore
from .experience_extractor import ExperienceExtractor
from .experience_manager import ExperienceManager

__all__ = ["Experience", "ExperienceStore", "ExperienceExtractor", "ExperienceManager"]
