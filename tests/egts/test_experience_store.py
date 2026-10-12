from pathlib import Path

from data_collection.experience.experience_store import Experience, ExperienceStore


def test_retrieve_skills_uses_available_tool_subset(tmp_path: Path):
    store = ExperienceStore(store_path=tmp_path / "experience_store.json")
    store.add_experience(
        Experience(
            experience_id="issue_triage",
            description="Inspect an issue and add a useful follow-up comment",
            tool_sequence=["get_issue", "add_issue_comment"],
            context_summary="GitHub issue triage",
        )
    )
    store.add_experience(
        Experience(
            experience_id="release_flow",
            description="Create a release from repository state",
            tool_sequence=["get_latest_release", "create_release"],
            context_summary="GitHub release workflow",
        )
    )

    matches = store.retrieve_experiences(
        query="GitHub issue triage",
        top_k=5,
        required_tools=["get_issue", "add_issue_comment", "list_issues"],
    )

    assert [exp.experience_id for exp in matches] == ["issue_triage"]
