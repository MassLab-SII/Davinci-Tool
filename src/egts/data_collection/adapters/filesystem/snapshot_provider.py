from typing import Any
from data_collection.adapters.base.interfaces import SnapshotProvider


class FilesystemSnapshotProvider(SnapshotProvider):
    """Filesystem implementation of SnapshotProvider.

    Delegates to existing snapshot_filesystem function.
    """

    def __init__(self, mcp_client, root: str):
        self.mcp_client = mcp_client
        self.root = root

    async def create_snapshot(self, identifier: str) -> Any:
        from ...state.filesystem_snapshot import snapshot_filesystem

        return await snapshot_filesystem(
            self.mcp_client, self.root, include_content_hash=True
        )

    def restore_snapshot(self, snapshot: Any) -> None:
        pass

    def cleanup(self) -> None:
        pass
