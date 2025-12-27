"""Atomic persistence for configuration and cursors."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Tuple

import yaml

from tg_keyword_forwarder.config import Config, CursorState, SourceConfig

SourceKey = Tuple[int, Optional[int]]


def ensure_unique_sources(sources: list[SourceConfig]) -> None:
    seen: set[SourceKey] = set()
    for source in sources:
        if source.source_key in seen:
            raise ValueError(f"Duplicate source configuration for chat_id={source.chat_id}, topic_id={source.topic_id}")
        seen.add(source.source_key)


def merge_cursor(existing: CursorState, incoming: CursorState) -> CursorState:
    last_message_id = _max_int(existing.last_message_id, incoming.last_message_id)
    last_timestamp = _max_datetime(existing.last_timestamp, incoming.last_timestamp)
    return CursorState(last_message_id=last_message_id, last_timestamp=last_timestamp)


def apply_cursor_updates(config: Config, cursor_updates: dict[SourceKey, CursorState]) -> dict[str, Any]:
    updated = dict(config.raw)
    sources = list(updated.get("sources", []))
    for source in sources:
        if not isinstance(source, dict):
            continue
        chat_id = source.get("chat_id")
        topic_id = source.get("topic_id")
        if isinstance(chat_id, bool) or not isinstance(chat_id, int):
            continue
        key = (chat_id, topic_id if isinstance(topic_id, int) else None)
        if key not in cursor_updates:
            continue
        existing_cursor = _cursor_from_raw(source.get("cursor"))
        merged = merge_cursor(existing_cursor, cursor_updates[key])
        if merged == existing_cursor:
            continue
        source["cursor"] = _cursor_to_raw(merged)
    updated["sources"] = sources
    return updated


def atomic_write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = yaml.safe_dump(data, sort_keys=False)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _cursor_from_raw(raw: Any) -> CursorState:
    if not isinstance(raw, dict):
        return CursorState(last_message_id=None, last_timestamp=None)
    last_message_id = raw.get("last_message_id")
    if isinstance(last_message_id, bool) or not isinstance(last_message_id, int):
        last_message_id = None
    last_timestamp = raw.get("last_timestamp")
    parsed_timestamp = None
    if isinstance(last_timestamp, str):
        try:
            parsed_timestamp = datetime.fromisoformat(last_timestamp.replace("Z", "+00:00"))
        except ValueError:
            parsed_timestamp = None
    return CursorState(last_message_id=last_message_id, last_timestamp=parsed_timestamp)


def _cursor_to_raw(cursor: CursorState) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    if cursor.last_message_id is not None:
        raw["last_message_id"] = cursor.last_message_id
    if cursor.last_timestamp is not None:
        raw["last_timestamp"] = cursor.last_timestamp.isoformat()
    return raw


def _max_int(current: Optional[int], incoming: Optional[int]) -> Optional[int]:
    if incoming is None:
        return current
    if current is None:
        return incoming
    return max(current, incoming)


def _max_datetime(current: Optional[datetime], incoming: Optional[datetime]) -> Optional[datetime]:
    if incoming is None:
        return current
    if current is None:
        return incoming
    return max(current, incoming)
