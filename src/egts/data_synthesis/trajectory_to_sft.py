"""Convert synthesized review records into SFT training format.

Input: data_synthesis/pipeline.py output (episode-level review records)
Output: flattened SFT samples in llamafactory or axolotl format

Supports recursive directory scanning: pass a directory as --input and all
synthesized_review_records.json files underneath will be discovered.
"""

import argparse
import glob
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

SYSTEM_PROMPT = "You are a helpful agent that uses tools iteratively to complete the user's task."

logger = logging.getLogger(__name__)


def _parse_bool_flag(value: str) -> bool:
    v = str(value).strip().lower()
    if v in {"1", "true", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"Invalid bool value: {value}")


# ── Content sanitization helpers ──────────────────────────────────────────

def sanitize_content(content: Any) -> str:
    """Sanitize message content to prevent JSON parsing issues.

    - Converts non-string content to string
    - Removes control characters except newline/tab
    - Ensures content is valid UTF-8

    Args:
        content: Message content (string, dict, list, etc.)

    Returns:
        Sanitized string content
    """
    # Convert to string
    if content is None:
        return ""
    if isinstance(content, (dict, list)):
        try:
            content = json.dumps(content, ensure_ascii=False)
        except Exception:
            content = str(content)
    else:
        content = str(content)

    # Remove control characters except \n, \r, \t
    # This prevents issues with null bytes, form feeds, etc.
    import re
    content = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', '', content)

    # Ensure valid UTF-8
    content = content.encode('utf-8', errors='ignore').decode('utf-8')

    return content


def validate_message_schema(msg: Dict[str, Any]) -> bool:
    """Validate message has required fields and valid structure.

    Args:
        msg: Message dict

    Returns:
        True if valid, False otherwise
    """
    if not isinstance(msg, dict):
        return False

    # Must have role
    role = msg.get("role")
    if role not in ("system", "user", "assistant", "tool"):
        return False

    # Must have content (can be empty string)
    if "content" not in msg:
        return False

    # Assistant with tool_calls must have valid structure
    if role == "assistant" and msg.get("tool_calls"):
        tool_calls = msg["tool_calls"]
        if not isinstance(tool_calls, list):
            return False
        for tc in tool_calls:
            if not isinstance(tc, dict):
                return False
            func = tc.get("function")
            if not isinstance(func, dict):
                return False
            if not func.get("name"):
                return False
            # arguments can be string or dict
            args = func.get("arguments")
            if args is not None and not isinstance(args, (str, dict)):
                return False

    return True


class TrajectoryToSFTConverter:
    def __init__(self, system_prompt: str = SYSTEM_PROMPT):
        self.system_prompt = system_prompt

    # ── IO helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _load_json_list(path: str) -> List[Dict[str, Any]]:
        """Load records from a JSON array file or a JSONL file.

        Auto-detects format by reading the first non-blank character:
        - ``[``  → JSON array (one-shot parse)
        - ``{``  → JSONL, one JSON object per line
        """
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read().lstrip()
            if raw.startswith("["):
                data = json.loads(raw)
                return data if isinstance(data, list) else []
            # JSONL — one object per line
            records: List[Dict[str, Any]] = []
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        records.append(obj)
                except json.JSONDecodeError:
                    logger.warning("Skipping malformed JSONL line in %s", path)
            return records
        except Exception:
            return []

    @staticmethod
    def _save_json_atomic(path: str, data: Any) -> None:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix=".tmp_sft_", suffix=".json", dir=parent or ".")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, path)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    @staticmethod
    def _discover_record_files(input_path: str) -> List[str]:
        """Discover synthesis output files (review records or train data).

        If *input_path* is a file, return it directly.
        If it is a directory, recursively glob for both
        ``**/synthesized_review_records.json`` and
        ``**/synthesized_review_train_data.json`` underneath.
        """
        if os.path.isfile(input_path):
            return [input_path]
        found: List[str] = []
        for name in ("synthesized_review_records.json", "synthesized_review_train_data.json", "replay_data.jsonl"):
            pattern = os.path.join(input_path, "**", name)
            found.extend(glob.glob(pattern, recursive=True))
        return sorted(set(found))

    # ── difficulty helpers ──────────────────────────────────────────────

    DIFFICULTY_LEVELS = ("easy", "medium", "hard", "expert")

    @staticmethod
    def _count_tool_steps(record: Dict[str, Any]) -> int:
        """Count tool steps from record, using statistics or messages."""
        stats = record.get("statistics")
        if isinstance(stats, dict) and stats.get("num_tool_calls") is not None:
            return int(stats["num_tool_calls"])
        return sum(
            1 for m in record.get("messages", [])
            if m.get("role") == "assistant" and m.get("tool_calls")
        )

    @staticmethod
    def _difficulty_from_tool_steps(tool_steps: int) -> Tuple[str, int]:
        steps = max(0, int(tool_steps or 0))
        if steps <= 0:
            return "unknown", 0
        if steps <= 3:
            return "easy", 1
        if steps <= 7:
            return "medium", 2
        if steps <= 12:
            return "hard", 3
        return "expert", 4

    @classmethod
    def _annotate_difficulty(cls, records: List[Dict[str, Any]]) -> None:
        """Add difficulty_level and difficulty_rank to each record in-place."""
        for r in records:
            steps = cls._count_tool_steps(r)
            level, rank = cls._difficulty_from_tool_steps(steps)
            r["_difficulty_level"] = level
            r["_difficulty_rank"] = rank
            r["_difficulty_tool_steps"] = steps

    @classmethod
    def _filter_by_difficulty(
        cls, records: List[Dict[str, Any]], difficulty: str,
    ) -> List[Dict[str, Any]]:
        """Filter records by difficulty. Supports comma-separated levels, e.g. 'easy,medium'."""
        cls._annotate_difficulty(records)
        if difficulty == "all":
            return records
        levels = set(difficulty.split(","))
        return [r for r in records if r["_difficulty_level"] in levels]

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _build_meta_quality_indexes(
        meta_file: Optional[str],
    ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
        by_record_id: Dict[str, Dict[str, Any]] = {}
        by_episode_dir: Dict[str, Dict[str, Any]] = {}
        if not meta_file or (not os.path.exists(meta_file)):
            return by_record_id, by_episode_dir
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                entries = json.load(f)
        except Exception:
            return by_record_id, by_episode_dir
        if not isinstance(entries, list):
            return by_record_id, by_episode_dir

        for item in entries:
            if not isinstance(item, dict):
                continue
            rid = str(item.get("record_id", "") or item.get("id", "") or "").strip()
            if rid:
                by_record_id[rid] = item
            ep = str(item.get("episode_dir", "") or "").strip()
            if ep:
                by_episode_dir[ep] = item
        return by_record_id, by_episode_dir

    def _extract_quality_fields(
        self,
        record: Dict[str, Any],
        meta_by_record_id: Dict[str, Dict[str, Any]],
        meta_by_episode_dir: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        quality_obj = record.get("quality")
        tier = ""
        score = None
        selected = record.get("selected_for_training")

        if isinstance(quality_obj, dict):
            tier = str(quality_obj.get("quality_tier", "") or "").strip()
            score = self._safe_float(quality_obj.get("quality_score"))
            if selected is None:
                selected = quality_obj.get("selected_for_training")

        if not tier:
            tier = str(record.get("quality_tier", "") or "").strip()
        if score is None:
            score = self._safe_float(record.get("quality_score"))
        if selected is None:
            selected = record.get("selected_for_training")

        record_id = str(record.get("record_id", "") or "").strip()
        episode_dir = str(record.get("episode_dir", "") or "").strip()
        meta = {}
        if record_id and record_id in meta_by_record_id:
            meta = meta_by_record_id[record_id]
        elif episode_dir and episode_dir in meta_by_episode_dir:
            meta = meta_by_episode_dir[episode_dir]

        if isinstance(meta, dict):
            if not tier:
                tier = str(meta.get("quality_tier", "") or "").strip()
            if score is None:
                score = self._safe_float(meta.get("quality_score"))
            if selected is None:
                selected = meta.get("selected_for_training")

        is_fallback = tier == "fallback_based"
        if not is_fallback:
            accept_mode = str(record.get("trajectory_accept_mode", "") or "")
            if not accept_mode and isinstance(meta, dict):
                accept_mode = str(meta.get("trajectory_accept_mode", "") or "")
            is_fallback = "fallback" in accept_mode.lower()

        return {
            "quality_tier": tier or "unknown",
            "quality_score": score,
            "selected_for_training": bool(selected) if selected is not None else None,
            "is_fallback": is_fallback,
        }

    def _filter_by_quality(
        self,
        records: List[Dict[str, Any]],
        *,
        quality_tier: str,
        min_quality_score: Optional[float],
        exclude_fallback: bool,
        meta_file: Optional[str],
    ) -> List[Dict[str, Any]]:
        tiers = {
            t.strip() for t in str(quality_tier or "").split(",")
            if t and t.strip()
        }
        active_tier_filter = bool(tiers)
        active_score_filter = min_quality_score is not None
        if (not active_tier_filter) and (not active_score_filter) and (not exclude_fallback):
            return records

        meta_by_record_id, meta_by_episode_dir = self._build_meta_quality_indexes(meta_file)
        kept: List[Dict[str, Any]] = []
        drop_counts = {
            "tier": 0,
            "score": 0,
            "fallback": 0,
        }
        for r in records:
            q = self._extract_quality_fields(r, meta_by_record_id, meta_by_episode_dir)
            r["_quality_tier"] = q["quality_tier"]
            r["_quality_score"] = q["quality_score"]
            r["_is_fallback"] = q["is_fallback"]
            if q["selected_for_training"] is not None:
                r["_selected_for_training"] = q["selected_for_training"]

            if exclude_fallback and bool(q["is_fallback"]):
                drop_counts["fallback"] += 1
                continue
            if active_tier_filter and q["quality_tier"] not in tiers:
                drop_counts["tier"] += 1
                continue
            if active_score_filter:
                score = q["quality_score"]
                if score is None or score < float(min_quality_score):
                    drop_counts["score"] += 1
                    continue
            kept.append(r)

        logger.info(
            "Quality filter: tiers=%s min_score=%s exclude_fallback=%s => kept=%d/%d (drop tier=%d score=%d fallback=%d)",
            ",".join(sorted(tiers)) if tiers else "all",
            f"{float(min_quality_score):.2f}" if min_quality_score is not None else "disabled",
            exclude_fallback,
            len(kept),
            len(records),
            drop_counts["tier"],
            drop_counts["score"],
            drop_counts["fallback"],
        )
        return kept

    # ── llamafactory format helpers ───────────────────────────────────────

    def _format_tool_xml(self, tool_call: Dict[str, Any]) -> str:
        name = tool_call.get("function", {}).get("name", "unknown")
        args = tool_call.get("function", {}).get("arguments", {})

        if isinstance(args, str):
            try:
                arg_dict = json.loads(args)
            except Exception:
                arg_dict = {"args": args}
        elif isinstance(args, dict):
            arg_dict = args
        else:
            arg_dict = {}

        params_str = ""
        for key, value in arg_dict.items():
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            params_str += f"<parameter={key}>\n{value}\n</parameter>\n"

        return f"<tool_call>\n<function={name}>\n{params_str}</function>\n</tool_call>"

    def _convert_record_llamafactory(self, record: Dict[str, Any]) -> List[Dict[str, Any]]:
        problem = record.get("problem", "")
        tools = record.get("tools", [])
        messages = record.get("messages", [])
        episode_dir = record.get("episode_dir", "")

        samples: List[Dict[str, Any]] = []
        history: List[List[str]] = []

        current_instruction = problem
        first_user_message_found = False

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")

            if role == "system":
                continue

            if role == "user":
                if not first_user_message_found:
                    current_instruction = problem
                    first_user_message_found = True
                else:
                    current_instruction = content
                continue

            if role == "tool":
                if isinstance(content, (dict, list)):
                    content = json.dumps(content, ensure_ascii=False)
                current_instruction = f"<tool_response>\n{content}\n</tool_response>"
                continue

            if role != "assistant":
                continue

            output = ""
            tool_calls = msg.get("tool_calls") or []
            if tool_calls:
                if content:
                    output += f"{content}\n\n"
                for tc in tool_calls:
                    output += self._format_tool_xml(tc)
            else:
                output += str(content)

            sample = {
                "instruction": current_instruction,
                "input": "",
                "output": output,
                "system": self.system_prompt,
                "history": list(history),
                "meta": {
                    "record_id": record.get("record_id"),
                    "episode_dir": episode_dir,
                    "mcp_server": record.get("mcp_server"),
                    "task_type": record.get("task_type"),
                },
            }
            if tools:
                sample["tools"] = tools
            samples.append(sample)
            history.append([current_instruction, output])

        return samples

    # ── axolotl format helpers ────────────────────────────────────────────

    @staticmethod
    def _extract_tool_result(content: str) -> str:
        """Extract actual tool result from MCP-formatted response wrapper.

        MCP servers return results wrapped in:
            {"meta": ..., "content": [{"type": "text", "text": "..."}],
             "structuredContent": {"result": "..."}, "isError": false}

        We unwrap to just the result string so the training data matches
        standard OpenAI tool response format.
        """
        if not content:
            return content
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return content

        if not isinstance(data, dict):
            return content

        # Prefer structuredContent.result (most MCP servers set this)
        sc = data.get("structuredContent")
        if isinstance(sc, dict) and "result" in sc:
            result = sc["result"]
            # result may itself be a JSON string; pass through as-is
            return str(result) if not isinstance(result, str) else result

        # Fallback: first text block in content array
        content_arr = data.get("content")
        if isinstance(content_arr, list) and len(content_arr) > 0:
            first = content_arr[0]
            if isinstance(first, dict) and "text" in first:
                return str(first["text"])

        return content

    def _convert_record_axolotl(self, record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert a single record to axolotl-compatible chat format.

        Output matches the reference format:
          {"messages": [...], "tools": [...]}
        """
        messages = record.get("messages")
        if not messages:
            return None

        sanitized_messages = []
        for i, m in enumerate(messages):
            if not validate_message_schema(m):
                logger.warning(
                    "Record %s: message %d has invalid schema, skipping record",
                    record.get("record_id", "unknown"), i
                )
                return None

            content = sanitize_content(m.get("content", ""))

            sanitized_msg: Dict[str, Any] = {
                "role": m["role"],
                "content": content,
            }

            # assistant message with tool_calls: strip id/type, keep only function
            if m.get("tool_calls"):
                sanitized_tool_calls = []
                for tc in m["tool_calls"]:
                    func = tc.get("function", {})
                    args = func.get("arguments", "{}")

                    if isinstance(args, dict):
                        try:
                            args = json.dumps(args, ensure_ascii=False)
                        except Exception:
                            args = "{}"
                    elif not isinstance(args, str):
                        args = str(args)

                    # Validate JSON
                    try:
                        json.loads(args)
                    except json.JSONDecodeError:
                        logger.warning(
                            "Record %s: tool_call has invalid JSON arguments, skipping record",
                            record.get("record_id", "unknown")
                        )
                        return None

                    sanitized_tool_calls.append({
                        "function": {
                            "name": func.get("name", "unknown"),
                            "arguments": args,
                        }
                    })
                sanitized_msg["tool_calls"] = sanitized_tool_calls

            # tool message: extract result from MCP wrapper, drop tool_call_id
            if m.get("role") == "tool":
                sanitized_msg["content"] = self._extract_tool_result(content)

            sanitized_messages.append(sanitized_msg)

        # Replace system prompt
        sanitized_messages = [
            {**m, "content": self.system_prompt} if m.get("role") == "system" else m
            for m in sanitized_messages
        ]

        # Normalize tools: parameters serialized to JSON string (matching reference format)
        tools = record.get("tools", [])
        norm_tools = []
        for t in tools:
            func = t.get("function", {})
            name = func.get("name") or t.get("name", "")
            desc = func.get("description") or t.get("description", "")
            params = func.get("parameters") or t.get("inputSchema")

            # Serialize parameters dict to JSON string for axolotl format
            if isinstance(params, dict):
                params = json.dumps(params, ensure_ascii=False)
            elif isinstance(params, str):
                # Already a string — validate it's parseable JSON
                try:
                    json.loads(params)
                except json.JSONDecodeError:
                    params = "{}"
            else:
                params = "{}"

            norm_tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": desc,
                    "parameters": params,
                },
            })

        return {
            "messages": sanitized_messages,
            "tools": norm_tools,
        }

    # ── main entry point ──────────────────────────────────────────────────

    @staticmethod
    def _apply_difficulty_suffix(output_file: str, difficulty: str) -> str:
        """Insert difficulty suffix before file extension: foo.jsonl -> foo_easy.jsonl."""
        if difficulty == "all":
            return output_file
        base, ext = os.path.splitext(output_file)
        return f"{base}_{difficulty}{ext}"

    def convert(
        self,
        input_path: str,
        output_file: str,
        framework: str = "llamafactory",
        progress_file: Optional[str] = None,
        difficulty: str = "all",
        quality_tier: str = "",
        min_quality_score: Optional[float] = None,
        exclude_fallback: bool = False,
        meta_file: Optional[str] = None,
    ) -> None:
        record_files = self._discover_record_files(input_path)
        if not record_files:
            logger.warning("No synthesized_review_records.json found under %s", input_path)
            return
        logger.info("Discovered %d record file(s) under %s", len(record_files), input_path)

        # Merge all records
        all_records: List[Dict[str, Any]] = []
        for rf in record_files:
            loaded = self._load_json_list(rf)
            logger.info("  %s: %d records", rf, len(loaded))
            all_records.extend(loaded)

        if not all_records:
            logger.warning("No records found")
            return

        # Difficulty filtering / sorting
        before_count = len(all_records)
        all_records = self._filter_by_difficulty(all_records, difficulty)
        logger.info(
            "Difficulty=%s: %d -> %d records",
            difficulty, before_count, len(all_records),
        )
        if difficulty == "all":
            from collections import Counter
            dist = Counter(r["_difficulty_level"] for r in all_records)
            for lvl in ("easy", "medium", "hard", "expert"):
                logger.info("  %s: %d", lvl, dist.get(lvl, 0))
        if not all_records:
            logger.warning("No records after difficulty filtering")
            return

        # Quality filtering / sorting
        quality_before = len(all_records)
        all_records = self._filter_by_quality(
            all_records,
            quality_tier=quality_tier,
            min_quality_score=min_quality_score,
            exclude_fallback=exclude_fallback,
            meta_file=meta_file,
        )
        if not all_records:
            logger.warning(
                "No records after quality filtering (before=%d, after=0)",
                quality_before,
            )
            return

        # Apply difficulty suffix to output filename
        output_file = self._apply_difficulty_suffix(output_file, difficulty)

        # Resume support
        if not progress_file:
            progress_file = f"{output_file}.progress.json"
        progress_entries = self._load_json_list(progress_file)
        done_ids: Set[str] = {
            item.get("record_id")
            for item in progress_entries
            if isinstance(item, dict) and item.get("record_id")
        }

        logger.info(
            "Total %d records, %d already converted, framework=%s",
            len(all_records), len(done_ids), framework,
        )

        if framework == "axolotl":
            self._convert_axolotl_pipeline(all_records, output_file, progress_file, progress_entries, done_ids)
        else:
            self._convert_llamafactory_pipeline(all_records, output_file, progress_file, progress_entries, done_ids)

    def _convert_llamafactory_pipeline(
        self, records, output_file, progress_file, progress_entries, done_ids,
    ):
        converted_samples = self._load_json_list(output_file)

        for idx, record in enumerate(records, start=1):
            record_id = record.get("record_id") or f"row_{idx}"
            record["record_id"] = record_id
            if record_id in done_ids:
                continue

            samples = self._convert_record_llamafactory(record)
            converted_samples.extend(samples)
            progress_entries.append({
                "record_id": record_id,
                "episode_dir": record.get("episode_dir"),
                "num_samples": len(samples),
            })
            done_ids.add(record_id)
            self._save_json_atomic(output_file, converted_samples)
            self._save_json_atomic(progress_file, progress_entries)

        logger.info("SFT (llamafactory) done: %d samples -> %s", len(converted_samples), output_file)

    def _convert_axolotl_pipeline(
        self, records, output_file, progress_file, progress_entries, done_ids,
    ):
        # For axolotl we write JSONL
        parent = os.path.dirname(output_file)
        if parent:
            os.makedirs(parent, exist_ok=True)

        # Load existing lines for resume
        existing_lines = []
        if os.path.exists(output_file):
            with open(output_file, "r", encoding="utf-8") as f:
                existing_lines = f.readlines()

        count = len(existing_lines)
        with open(output_file, "a", encoding="utf-8") as fout:
            for idx, record in enumerate(records, start=1):
                record_id = record.get("record_id") or f"row_{idx}"
                record["record_id"] = record_id
                if record_id in done_ids:
                    continue

                entry = self._convert_record_axolotl(record)
                if entry is None:
                    continue

                fout.write(json.dumps(entry, ensure_ascii=False) + "\n")
                count += 1
                progress_entries.append({
                    "record_id": record_id,
                    "episode_dir": record.get("episode_dir"),
                    "num_samples": 1,
                })
                done_ids.add(record_id)
                self._save_json_atomic(progress_file, progress_entries)

        logger.info("SFT (axolotl) done: %d entries -> %s", count, output_file)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(
        description="Convert synthesized review records to SFT training format."
    )
    parser.add_argument(
        "--input", required=True,
        help="Input file or directory (recursively discovers synthesized_review_records.json)",
    )
    parser.add_argument(
        "--output", required=True,
        help="Output file path (.json for llamafactory, .jsonl for axolotl)",
    )
    parser.add_argument(
        "--framework", choices=["llamafactory", "axolotl"], default="llamafactory",
        help="Training framework format (default: llamafactory)",
    )
    parser.add_argument(
        "--progress", default="",
        help="Optional progress file for resumable conversion",
    )
    parser.add_argument(
        "--system-prompt", default="You are a helpful agent that uses tools iteratively to complete the user's task.",
        help="Override system prompt in output data",
    )
    parser.add_argument(
        "--difficulty", default="all",
        help="Difficulty filter: easy/medium/hard/expert, comma-separated combo "
             "(e.g. easy,medium), or all (default: all)",
    )
    parser.add_argument(
        "--quality-tier",
        default="",
        help=(
            "Optional quality tier filter, comma-separated "
            "(e.g. high_quality,acceptable). Empty means no tier filter."
        ),
    )
    parser.add_argument(
        "--min-quality-score",
        type=float,
        default=-1.0,
        help="Optional minimum quality score threshold (0~1). Negative disables.",
    )
    parser.add_argument(
        "--exclude-fallback",
        type=_parse_bool_flag,
        default=False,
        help="Whether to exclude fallback_based trajectories (true/false).",
    )
    parser.add_argument(
        "--meta",
        default="",
        help="Optional synthesis meta JSON path for quality field backfill.",
    )
    args = parser.parse_args()

    converter = TrajectoryToSFTConverter(system_prompt=args.system_prompt)
    converter.convert(
        input_path=args.input,
        output_file=args.output,
        framework=args.framework,
        progress_file=args.progress or None,
        difficulty=args.difficulty,
        quality_tier=args.quality_tier,
        min_quality_score=(
            args.min_quality_score if args.min_quality_score is not None and args.min_quality_score >= 0 else None
        ),
        exclude_fallback=bool(args.exclude_fallback),
        meta_file=args.meta or None,
    )
