from __future__ import annotations

from typing import Any, Dict, Iterable, Optional


READ_ONLY_KEYWORDS = {
    "list",
    "read",
    "get",
    "search",
    "find",
    "show",
    "display",
    "info",
    "stat",
    "tree",
    "allowed",
}

WRITE_KEYWORDS = {
    "write",
    "edit",
    "create",
    "mkdir",
    "move",
    "delete",
    "remove",
    "rename",
    "copy",
    "append",
    "modify",
    "update",
    "set",
}


class ToolMetadataResolver:
    """Resolve tool metadata from task config, server metadata, and live tools."""

    def __init__(
        self,
        *,
        task_config: Any,
        server_name: str,
        server_metadata: Optional[Dict[str, Any]] = None,
    ):
        self.task_config = task_config
        self.server_name = server_name
        self.server_metadata = server_metadata or {}

    def resolve(self, all_tools: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        tool_names = [self._tool_name(tool) for tool in all_tools]
        tool_names = [name for name in tool_names if name]
        live_tool_set = set(tool_names)
        prefer_server_metadata = bool(self.server_metadata.get("_prefer_server_metadata"))

        task_tool_metadata = getattr(self.task_config, "tool_metadata", {}) or {}
        server_tool_metadata = self._server_tool_metadata()

        read_only_tools = self._resolve_read_only_tools(
            live_tool_set, task_tool_metadata, server_tool_metadata
        )
        read_only_tools_priority = self._resolve_priority_tools(
            live_tool_set,
            task_tool_metadata,
            server_tool_metadata,
            explicit=getattr(self.task_config, "read_only_tools_priority", []) or [],
            default_fallback=read_only_tools,
        )
        base_tools = self._resolve_flagged_tools(
            live_tool_set,
            task_tool_metadata,
            server_tool_metadata,
            explicit=getattr(self.task_config, "base_tools", []) or [],
            flag="base",
        )
        anchor_tools = self._resolve_flagged_tools(
            live_tool_set,
            task_tool_metadata,
            server_tool_metadata,
            explicit=self._task_anchor_tools(),
            flag="anchor",
        )

        if prefer_server_metadata:
            prompt_domain = (
                self.server_metadata.get("prompt_domain")
                or getattr(self.task_config, "prompt_domain", None)
                or self._normalize_prompt_domain(self.server_name)
            )
            output_namespace = (
                self.server_metadata.get("output_namespace")
                or getattr(self.task_config, "output_namespace", None)
                or self.server_name
            )
        else:
            prompt_domain = (
                getattr(self.task_config, "prompt_domain", None)
                or self.server_metadata.get("prompt_domain")
                or self._normalize_prompt_domain(self.server_name)
            )
            output_namespace = (
                getattr(self.task_config, "output_namespace", None)
                or self.server_metadata.get("output_namespace")
                or self.server_name
            )

        mutating_tools = self._resolve_flagged_tools(
            live_tool_set,
            task_tool_metadata,
            server_tool_metadata,
            explicit=getattr(self.task_config, "mutating_tools", None),
            flag="mutating",
        )

        return {
            "server_name": self.server_name,
            "output_namespace": output_namespace,
            "prompt_domain": prompt_domain,
            "read_only_tools": read_only_tools,
            "read_only_tools_priority": read_only_tools_priority,
            "base_tools": base_tools,
            "anchor_tools": anchor_tools,
            "mutating_tools": mutating_tools,
            "tool_names": tool_names,
            "tool_metadata": self._merged_tool_metadata(task_tool_metadata, server_tool_metadata),
        }

    def _task_anchor_tools(self) -> Optional[list[str]]:
        tool_curriculum = getattr(self.task_config, "tool_curriculum", None)
        if tool_curriculum is not None:
            return getattr(tool_curriculum, "anchor_tools", None)
        return None

    def _server_tool_metadata(self) -> Dict[str, Dict[str, Any]]:
        raw = self.server_metadata.get("tool_metadata", {})
        return raw if isinstance(raw, dict) else {}

    def _merged_tool_metadata(
        self,
        task_tool_metadata: Dict[str, Dict[str, Any]],
        server_tool_metadata: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}
        for source in (server_tool_metadata, task_tool_metadata):
            for tool_name, metadata in source.items():
                if not isinstance(metadata, dict):
                    continue
                merged.setdefault(tool_name, {})
                merged[tool_name].update(metadata)
        return merged

    @staticmethod
    def _tool_name(tool: Dict[str, Any]) -> str:
        return tool.get("name") or tool.get("function", {}).get("name", "")

    def _resolve_read_only_tools(
        self,
        live_tool_set: set[str],
        task_tool_metadata: Dict[str, Dict[str, Any]],
        server_tool_metadata: Dict[str, Dict[str, Any]],
    ) -> list[str]:
        explicit = list(getattr(self.task_config, "read_only_tools", []) or [])
        flagged = self._collect_flagged_tools(
            live_tool_set, task_tool_metadata, server_tool_metadata, flag="read_only"
        )

        if explicit:
            return self._filter_live(explicit, live_tool_set)
        if flagged:
            return flagged
        return self._infer_read_only_tools(sorted(live_tool_set))

    def _resolve_priority_tools(
        self,
        live_tool_set: set[str],
        task_tool_metadata: Dict[str, Dict[str, Any]],
        server_tool_metadata: Dict[str, Dict[str, Any]],
        *,
        explicit: list[str],
        default_fallback: list[str],
    ) -> list[str]:
        if explicit:
            return self._filter_live(explicit, live_tool_set)

        priority_pairs = []
        merged = self._merged_tool_metadata(task_tool_metadata, server_tool_metadata)
        for tool_name, metadata in merged.items():
            if tool_name not in live_tool_set:
                continue
            priority = metadata.get("priority")
            if isinstance(priority, int):
                priority_pairs.append((priority, tool_name))

        if priority_pairs:
            priority_pairs.sort(key=lambda item: (item[0], item[1]))
            return [tool_name for _, tool_name in priority_pairs]

        return list(default_fallback)

    def _resolve_flagged_tools(
        self,
        live_tool_set: set[str],
        task_tool_metadata: Dict[str, Dict[str, Any]],
        server_tool_metadata: Dict[str, Dict[str, Any]],
        *,
        explicit: Optional[list[str]],
        flag: str,
    ) -> Optional[list[str]]:
        if explicit:
            return self._filter_live(explicit, live_tool_set)

        flagged = self._collect_flagged_tools(
            live_tool_set, task_tool_metadata, server_tool_metadata, flag=flag
        )
        return flagged or None

    def _collect_flagged_tools(
        self,
        live_tool_set: set[str],
        task_tool_metadata: Dict[str, Dict[str, Any]],
        server_tool_metadata: Dict[str, Dict[str, Any]],
        *,
        flag: str,
    ) -> list[str]:
        merged = self._merged_tool_metadata(task_tool_metadata, server_tool_metadata)
        result = [
            tool_name
            for tool_name, metadata in merged.items()
            if tool_name in live_tool_set and metadata.get(flag) is True
        ]
        return sorted(result)

    @staticmethod
    def _filter_live(tool_names: Iterable[str], live_tool_set: set[str]) -> list[str]:
        result = []
        seen = set()
        for tool_name in tool_names:
            if tool_name in live_tool_set and tool_name not in seen:
                seen.add(tool_name)
                result.append(tool_name)
        return result

    @staticmethod
    def _infer_read_only_tools(tool_names: list[str]) -> list[str]:
        read_only = []
        for name in tool_names:
            lowered = name.lower()
            has_write = any(keyword in lowered for keyword in WRITE_KEYWORDS)
            has_read = any(keyword in lowered for keyword in READ_ONLY_KEYWORDS)
            if has_read and not has_write:
                read_only.append(name)
        return read_only

    @staticmethod
    def _normalize_prompt_domain(server_name: str) -> str:
        lowered = (server_name or "").lower()
        if "playwright" in lowered:
            return "playwright"
        if "postgres" in lowered or lowered == "pg":
            return "postgres"
        return "filesystem"
