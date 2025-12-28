"""Run-mode orchestration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Tuple

from telethon.tl import types

from tg_keyword_forwarder.config import Config, CursorState, SourceConfig
from tg_keyword_forwarder.forwarder import forward_with_fallback
from tg_keyword_forwarder.logging_setup import log_event
from tg_keyword_forwarder.matcher import match_message, normalize_keywords
from tg_keyword_forwarder.storage import apply_cursor_updates, atomic_write_yaml, ensure_unique_sources
from tg_keyword_forwarder.telegram_client import TelegramClientWrapper
from tg_keyword_forwarder.utils import hours_ago

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class FetchWindow:
    min_id: Optional[int]
    since: Optional[datetime]


@dataclass
class SourceStats:
    chat_id: int
    topic_id: Optional[int]
    scanned: int = 0
    matched: int = 0
    forwarded: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class RunSummary:
    sources: list[SourceStats]


async def list_chats(client: TelegramClientWrapper) -> list[str]:
    lines: list[str] = []
    async for dialog in client.iter_dialogs():
        lines.append(_format_chat_line(dialog.chat_id, dialog.chat_type, dialog.title))
        if dialog.is_forum and isinstance(dialog.entity, types.Channel):
            topics = await client.list_forum_topics(dialog.entity)
            if topics:
                for topic in topics:
                    lines.append(_format_topic_line(dialog.chat_id, topic.topic_id, topic.title))
            else:
                topic_ids = await _infer_topic_ids(client, dialog.entity)
                for topic_id in sorted(topic_ids):
                    lines.append(_format_topic_hint(dialog.chat_id, topic_id))
    return lines


def compute_fetch_window(cursor: CursorState) -> FetchWindow:
    if cursor.last_message_id is not None:
        return FetchWindow(min_id=cursor.last_message_id, since=None)
    if cursor.last_timestamp is not None:
        return FetchWindow(min_id=None, since=cursor.last_timestamp)
    return FetchWindow(min_id=None, since=hours_ago(24))


async def run_sources(client: TelegramClientWrapper, config: Config) -> RunSummary:
    ensure_unique_sources(config.sources)
    cursor_updates: dict[Tuple[int, Optional[int]], CursorState] = {}
    source_stats: list[SourceStats] = []

    log_event(LOGGER, "run_start", sources=len(config.sources))
    for source in config.sources:
        stats = SourceStats(chat_id=source.chat_id, topic_id=source.topic_id)
        try:
            update = await _process_source(client, config.destination_chat_id, source, stats)
            if update is not None:
                cursor_updates[source.source_key] = update
        except Exception as exc:  # noqa: BLE001
            stats.errors.append(str(exc))
            LOGGER.exception("Source processing failed for chat_id=%s topic_id=%s", source.chat_id, source.topic_id)
        source_stats.append(stats)
        log_event(
            LOGGER,
            "source_summary",
            chat_id=stats.chat_id,
            topic_id=stats.topic_id,
            scanned=stats.scanned,
            matched=stats.matched,
            forwarded=stats.forwarded,
            errors=len(stats.errors),
        )

    if cursor_updates:
        updated = apply_cursor_updates(config, cursor_updates)
        atomic_write_yaml(config.path, updated)

    log_event(LOGGER, "run_end", sources=len(config.sources))
    return RunSummary(sources=source_stats)


async def _process_source(
    client: TelegramClientWrapper,
    destination_chat_id: int,
    source: SourceConfig,
    stats: SourceStats,
) -> Optional[CursorState]:
    window = compute_fetch_window(source.cursor)
    keywords = normalize_keywords(source.keywords)
    max_message_id: Optional[int] = None
    max_timestamp: Optional[datetime] = None
    header_sent = False

    async for message in client.iter_messages_since(
        source.chat_id,
        min_id=window.min_id,
        since=window.since,
        topic_id=source.topic_id,
    ):
        stats.scanned += 1
        if message.id:
            max_message_id = max(max_message_id or 0, message.id)
        if message.date:
            msg_date = message.date
            if msg_date.tzinfo is None:
                msg_date = msg_date.replace(tzinfo=timezone.utc)
            max_timestamp = _max_datetime(max_timestamp, msg_date)

        match = match_message(message, keywords)
        if not match.matched:
            continue
        stats.matched += 1
        if not header_sent:
            header_text = _format_source_header(source, message)
            try:
                await client.send_text_message(destination_chat_id, header_text)
            except Exception as exc:  # noqa: BLE001
                log_event(
                    LOGGER,
                    "source_header_error",
                    chat_id=source.chat_id,
                    topic_id=source.topic_id,
                    error=str(exc),
                )
                stats.errors.append(f"source_header_error={exc}")
            header_sent = True
        result = await forward_with_fallback(client, destination_chat_id, message)
        if result.forwarded or result.copied:
            stats.forwarded += 1
        elif result.error:
            log_event(
                LOGGER,
                "forward_error",
                chat_id=source.chat_id,
                topic_id=source.topic_id,
                message_id=message.id,
                error=result.error,
            )
            stats.errors.append(f"message_id={message.id} error={result.error}")

    if max_message_id is None and max_timestamp is None:
        return None
    return CursorState(last_message_id=max_message_id, last_timestamp=max_timestamp)


def _max_datetime(current: Optional[datetime], incoming: Optional[datetime]) -> Optional[datetime]:
    if incoming is None:
        return current
    if current is None:
        return incoming
    return max(current, incoming)


async def _infer_topic_ids(client: TelegramClientWrapper, entity: types.Channel) -> set[int]:
    topic_ids: set[int] = set()
    async for message in client.iter_recent_messages(entity, limit=200):
        topic_id = getattr(message, "reply_to_top_id", None)
        if isinstance(topic_id, int):
            topic_ids.add(topic_id)
    return topic_ids


def _format_chat_line(chat_id: int, chat_type: str, title: str) -> str:
    return f"CHAT\t{chat_id}\t{chat_type}\t{title}"


def _format_topic_line(chat_id: int, topic_id: int, title: str) -> str:
    return f"TOPIC\t{chat_id}\t{topic_id}\t{title}"


def _format_topic_hint(chat_id: int, topic_id: int) -> str:
    return f"TOPIC_HINT\t{chat_id}\t{topic_id}"


def _format_source_header(source: SourceConfig, message: types.Message) -> str:
    title = source.chat_name or _extract_message_chat_title(message) or str(source.chat_id)
    return f"Source chat: {title}"


def _extract_message_chat_title(message: types.Message) -> Optional[str]:
    chat = getattr(message, "chat", None)
    if chat is None:
        return None
    title = getattr(chat, "title", None)
    if isinstance(title, str):
        cleaned = title.strip()
        if cleaned:
            return cleaned
    if isinstance(chat, types.User):
        name_parts = [part for part in [chat.first_name, chat.last_name] if part]
        if name_parts:
            return " ".join(name_parts)
        username = getattr(chat, "username", None)
        if isinstance(username, str) and username.strip():
            return username.strip()
    return None
