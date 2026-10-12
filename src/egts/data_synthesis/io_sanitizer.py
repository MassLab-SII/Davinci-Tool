"""Path/content sanitization mixin for data_synthesis outputs."""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List


class IOSanitizerMixin:
    def _sanitize_messages(
        self, messages: List[Dict[str, Any]], episode_dir: str
    ) -> List[Dict[str, Any]]:
        sanitized: List[Dict[str, Any]] = []
        for msg in messages:
            sanitized_msg = dict(msg)
            if "content" in sanitized_msg:
                sanitized_msg["content"] = self._sanitize_content(
                    sanitized_msg.get("content"), episode_dir
                )
            if "tool_calls" in sanitized_msg:
                sanitized_msg["tool_calls"] = self._sanitize_content(
                    sanitized_msg.get("tool_calls"), episode_dir
                )
            sanitized.append(sanitized_msg)
        return sanitized

    def _sanitize_path(self, path: str, episode_dir: str) -> str:
        if not isinstance(path, str):
            return path

        text = path.replace("\\", "/")
        if not text:
            return text
        if text.startswith("/workspace"):
            return text

        ws_idx = text.find("/workspace/")
        if ws_idx >= 0:
            return text[ws_idx:]
        if text.endswith("/workspace"):
            return "/workspace"

        for marker in ("workspaces-filesystem", "workspaces-async"):
            marker_seg = f"/{marker}/"
            if marker_seg in text:
                suffix = text.split(marker_seg, 1)[1].lstrip("/")
                return f"/workspace/{suffix}" if suffix else "/workspace"
            if text.endswith(f"/{marker}"):
                return "/workspace"

        match = re.search(r"(trajs2data_\d+)(/.*)?$", text)
        if match:
            suffix = match.group(2) or ""
            return f"/workspace/{match.group(1)}{suffix}"

        episode_abs = os.path.abspath(episode_dir).replace("\\", "/")
        episode_name = os.path.basename(episode_abs.rstrip("/")) if episode_abs else ""
        if episode_abs and episode_abs in text:
            suffix = text.split(episode_abs, 1)[1]
            if episode_name:
                return f"/workspace/{episode_name}{suffix}"
            return f"/workspace{suffix}" if suffix else "/workspace"

        workspace_root_abs = os.path.dirname(episode_abs) if episode_abs else ""
        if workspace_root_abs and workspace_root_abs in text:
            suffix = text.split(workspace_root_abs, 1)[1]
            if suffix.startswith("/"):
                return f"/workspace{suffix}"
            return "/workspace"

        if re.match(r"^/(Users|home)/", text):
            basename = os.path.basename(text.rstrip("/"))
            if basename and basename not in {"Users", "home"}:
                return f"/workspace/{basename}"
            return "/workspace"

        if re.match(r"^/(private/)?var/folders/", text):
            basename = os.path.basename(text.rstrip("/"))
            if basename:
                return f"/workspace/{basename}"
            return "/workspace"

        return text

    def _sanitize_path_tokens_in_text(self, text: str, episode_dir: str) -> str:
        if not isinstance(text, str) or "/" not in text:
            return text

        token_pattern = re.compile(r"(?<!:)(/[A-Za-z0-9._~/-]+)")

        def _replace(match: re.Match) -> str:
            token = match.group(1)
            sanitized = self._sanitize_path(token, episode_dir)
            return sanitized if isinstance(sanitized, str) else token

        return token_pattern.sub(_replace, text)

    def _sanitize_content(self, content: Any, episode_dir: str) -> Any:
        if isinstance(content, str):
            episode_abs = os.path.abspath(episode_dir)
            episode_name = os.path.basename(episode_abs.rstrip("/"))
            workspace_root_abs = os.path.dirname(episode_abs)

            variants = [
                episode_dir,
                os.path.dirname(episode_dir),
                episode_abs,
                workspace_root_abs,
                episode_abs.replace("\\", "/"),
                workspace_root_abs.replace("\\", "/"),
            ]
            for value in variants:
                if not value:
                    continue
                value_norm = value.replace("\\", "/")
                if value_norm and value_norm in content:
                    if value_norm in {
                        episode_abs.replace("\\", "/"),
                        episode_dir.replace("\\", "/"),
                    }:
                        if episode_name:
                            content = content.replace(
                                value_norm, f"/workspace/{episode_name}"
                            )
                    else:
                        content = content.replace(value_norm, "/workspace")

            return self._sanitize_path_tokens_in_text(content, episode_dir)

        if isinstance(content, dict):
            return {k: self._sanitize_content(v, episode_dir) for k, v in content.items()}

        if isinstance(content, list):
            return [self._sanitize_content(i, episode_dir) for i in content]

        return content

