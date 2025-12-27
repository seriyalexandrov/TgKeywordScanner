"""Keyword normalization and matching."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from telethon.tl import types


@dataclass(frozen=True)
class MatchResult:
    matched: bool
    keyword: Optional[str]


def normalize_keywords(keywords: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for keyword in keywords:
        cleaned = keyword.strip()
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(cleaned)
    return normalized


def match_message(message: types.Message, keywords: Iterable[str]) -> MatchResult:
    content = _extract_content(message)
    if not content:
        return MatchResult(matched=False, keyword=None)
    lowered = content.lower()
    for keyword in keywords:
        if keyword.lower() in lowered:
            return MatchResult(matched=True, keyword=keyword)
    return MatchResult(matched=False, keyword=None)


def _extract_content(message: types.Message) -> Optional[str]:
    text = getattr(message, "message", None)
    if text:
        return text
    return None
