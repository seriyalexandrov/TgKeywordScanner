"""Configuration loading and validation."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Tuple

import yaml

DEFAULT_CONFIG_PATH = Path.home() / ".telegram-scrapper-config.yaml"

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CursorState:
    last_message_id: Optional[int]
    last_timestamp: Optional[datetime]


@dataclass(frozen=True)
class SourceConfig:
    chat_id: int
    topic_id: Optional[int]
    keywords: list[str]
    cursor: CursorState

    @property
    def source_key(self) -> Tuple[int, Optional[int]]:
        return (self.chat_id, self.topic_id)


@dataclass(frozen=True)
class Config:
    destination_chat_id: int
    sources: list[SourceConfig]
    raw: dict[str, Any]
    path: Path


def resolve_config_path(path_override: Optional[str]) -> Path:
    if path_override:
        return Path(path_override).expanduser()
    return DEFAULT_CONFIG_PATH


def load_config(path_override: Optional[str]) -> Config:
    path = resolve_config_path(path_override)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found at {path}")

    raw = _read_yaml(path)
    _warn_on_permissions(path)
    return _parse_config(raw, path)


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise OSError(f"Unable to read config file at {path}") from exc

    if not content.strip():
        raise ValueError(f"Config file at {path} is empty")

    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ValueError(f"Config file at {path} is not valid YAML") from exc

    if not isinstance(data, dict):
        raise ValueError("Config root must be a YAML mapping")

    return data


def _parse_config(raw: dict[str, Any], path: Path) -> Config:
    destination_chat_id = _require_int(raw, "destination_chat_id")
    sources_raw = raw.get("sources")
    if not isinstance(sources_raw, list):
        raise ValueError("Config requires a 'sources' list")

    sources: list[SourceConfig] = []
    for idx, item in enumerate(sources_raw):
        if not isinstance(item, dict):
            raise ValueError(f"Source at index {idx} must be a mapping")
        chat_id = _require_int(item, "chat_id", context=f"source[{idx}]")
        topic_id = _optional_int(item.get("topic_id"), context=f"source[{idx}].topic_id")
        keywords = _normalize_keywords(item.get("keywords"), context=f"source[{idx}].keywords")
        cursor = _parse_cursor(item.get("cursor"), context=f"source[{idx}].cursor")
        sources.append(
            SourceConfig(
                chat_id=chat_id,
                topic_id=topic_id,
                keywords=keywords,
                cursor=cursor,
            )
        )

    return Config(destination_chat_id=destination_chat_id, sources=sources, raw=raw, path=path)


def _require_int(raw: dict[str, Any], key: str, context: Optional[str] = None) -> int:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        location = context or "config"
        raise ValueError(f"{location} requires integer '{key}'")
    return value


def _optional_int(value: Any, context: Optional[str] = None) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        location = context or "config"
        raise ValueError(f"{location} must be an integer")
    return value


def _normalize_keywords(raw: Any, context: str) -> list[str]:
    if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes)):
        raise ValueError(f"{context} must be a list of strings")

    normalized: list[str] = []
    seen = set()
    for keyword in raw:
        if not isinstance(keyword, str):
            raise ValueError(f"{context} entries must be strings")
        cleaned = keyword.strip()
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(cleaned)

    if not normalized:
        raise ValueError(f"{context} must contain at least one non-empty keyword")

    return normalized


def _parse_cursor(raw: Any, context: str) -> CursorState:
    if raw is None:
        return CursorState(last_message_id=None, last_timestamp=None)
    if not isinstance(raw, dict):
        LOGGER.warning("%s is not a mapping; ignoring cursor", context)
        return CursorState(last_message_id=None, last_timestamp=None)

    last_message_id = raw.get("last_message_id")
    if isinstance(last_message_id, bool) or not isinstance(last_message_id, int):
        if last_message_id is not None:
            LOGGER.warning("%s.last_message_id is invalid; ignoring", context)
        last_message_id = None

    last_timestamp = raw.get("last_timestamp")
    parsed_timestamp = _parse_timestamp(last_timestamp, context=context)

    return CursorState(last_message_id=last_message_id, last_timestamp=parsed_timestamp)


def _parse_timestamp(value: Any, context: str) -> Optional[datetime]:
    if value is None:
        return None
    if not isinstance(value, str):
        LOGGER.warning("%s.last_timestamp is invalid; ignoring", context)
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        LOGGER.warning("%s.last_timestamp is invalid; ignoring", context)
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _warn_on_permissions(path: Path) -> None:
    if os.name != "posix":
        return
    try:
        mode = path.stat().st_mode
    except OSError:
        return
    if mode & 0o077:
        LOGGER.warning(
            "Config file permissions are broad; consider chmod 600 %s",
            path,
        )
