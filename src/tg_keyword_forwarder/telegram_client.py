"""Telegram client wrapper."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncIterator, Optional

from telethon import TelegramClient
from telethon.errors import FloodWaitError, RPCError
from telethon.sessions import StringSession
from telethon.tl import functions, types

from tg_keyword_forwarder.utils import retry_async

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DialogInfo:
    title: str
    chat_id: int
    chat_type: str
    is_forum: bool
    entity: Any


@dataclass(frozen=True)
class TopicInfo:
    topic_id: int
    title: str


class TelegramClientWrapper:
    def __init__(self, api_id: int, api_hash: str, session_string: str) -> None:
        self._client = TelegramClient(StringSession(session_string), api_id, api_hash)

    async def __aenter__(self) -> "TelegramClientWrapper":
        await self._client.connect()
        if not await self._client.is_user_authorized():
            raise RuntimeError("Telegram session is not authorized")
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self._client.disconnect()

    @staticmethod
    def from_environment() -> "TelegramClientWrapper":
        api_id_raw = os.environ.get("TELEGRAM_API_ID")
        api_hash = os.environ.get("TELEGRAM_API_HASH")
        session_string = os.environ.get("TELEGRAM_SESSION_STRING")
        if not api_id_raw or not api_hash or not session_string:
            raise RuntimeError("Missing TELEGRAM_API_ID/TELEGRAM_API_HASH/TELEGRAM_SESSION_STRING environment vars")
        try:
            api_id = int(api_id_raw)
        except ValueError as exc:
            raise RuntimeError("TELEGRAM_API_ID must be an integer") from exc
        return TelegramClientWrapper(api_id=api_id, api_hash=api_hash, session_string=session_string)

    async def iter_dialogs(self) -> AsyncIterator[DialogInfo]:
        dialogs = await retry_async(lambda: self._client.get_dialogs())
        for dialog in dialogs:
            entity = dialog.entity
            title = dialog.title or ""
            chat_id = dialog.id
            chat_type, is_forum = _resolve_chat_type(entity)
            yield DialogInfo(
                title=title,
                chat_id=chat_id,
                chat_type=chat_type,
                is_forum=is_forum,
                entity=entity,
            )

    async def list_forum_topics(self, entity: types.Channel, limit: int = 50) -> list[TopicInfo]:
        if not getattr(entity, "forum", False):
            return []

        async def _fetch() -> types.messages.ForumTopics:
            return await self._client(
                functions.channels.GetForumTopicsRequest(
                    channel=entity,
                    offset_date=None,
                    offset_id=0,
                    offset_topic=0,
                    limit=limit,
                )
            )

        try:
            result = await retry_async(_fetch)
        except (RPCError, FloodWaitError):
            LOGGER.warning("Unable to fetch forum topics for %s", entity.id)
            return []

        topics: list[TopicInfo] = []
        for topic in result.topics:
            if isinstance(topic, types.ForumTopic):
                topics.append(TopicInfo(topic_id=topic.id, title=topic.title))
        return topics

    async def iter_messages_since(
        self,
        entity: Any,
        *,
        min_id: Optional[int],
        since: Optional[datetime],
        topic_id: Optional[int],
        batch_limit: Optional[int] = None,
    ) -> AsyncIterator[types.Message]:
        attempts = 0
        current_min_id = min_id or 0
        while True:
            attempts += 1
            try:
                async for message in self._client.iter_messages(
                    entity,
                    min_id=current_min_id,
                    offset_date=since,
                    reverse=True,
                    reply_to=topic_id,
                    limit=batch_limit,
                ):
                    if message.id:
                        current_min_id = max(current_min_id, message.id)
                    yield message
                break
            except FloodWaitError as exc:
                if attempts >= 5:
                    raise
                await _sleep_for_flood(exc)
            except RPCError:
                if attempts >= 5:
                    raise
                await asyncio.sleep(_backoff_delay(attempts))

    async def forward_message(self, destination_chat_id: int, message: types.Message) -> None:
        await retry_async(lambda: self._client.forward_messages(destination_chat_id, message))

    async def copy_message(self, destination_chat_id: int, message: types.Message) -> None:
        text = message.message or ""
        if message.media:
            await retry_async(
                lambda: self._client.send_file(
                    destination_chat_id,
                    file=message.media,
                    caption=text or None,
                )
            )
        elif text:
            await retry_async(lambda: self._client.send_message(destination_chat_id, text))

    async def send_text_message(self, destination_chat_id: int, text: str) -> None:
        await retry_async(lambda: self._client.send_message(destination_chat_id, text))

    async def delete_all_messages(self, destination_chat_id: int, batch_size: int = 100) -> int:
        deleted = 0
        batch: list[int] = []
        async for message in self._client.iter_messages(destination_chat_id):
            if not isinstance(message.id, int):
                continue
            batch.append(message.id)
            if len(batch) >= batch_size:
                await retry_async(lambda: self._client.delete_messages(destination_chat_id, batch))
                deleted += len(batch)
                batch = []
        if batch:
            await retry_async(lambda: self._client.delete_messages(destination_chat_id, batch))
            deleted += len(batch)
        return deleted

    async def iter_recent_messages(
        self,
        entity: Any,
        *,
        limit: int = 100,
    ) -> AsyncIterator[types.Message]:
        attempts = 0
        while True:
            attempts += 1
            try:
                async for message in self._client.iter_messages(entity, limit=limit):
                    yield message
                break
            except FloodWaitError as exc:
                if attempts >= 5:
                    raise
                await _sleep_for_flood(exc)
            except RPCError:
                if attempts >= 5:
                    raise
                await asyncio.sleep(_backoff_delay(attempts))


async def _sleep_for_flood(exc: FloodWaitError) -> None:
    delay = max(1, int(getattr(exc, "seconds", 1)))
    await asyncio.sleep(delay)


def _backoff_delay(attempt: int) -> float:
    return min(2 ** (attempt - 1), 30)


def _resolve_chat_type(entity: types.TypePeer) -> tuple[str, bool]:
    if isinstance(entity, types.User):
        return "private", False
    if isinstance(entity, types.Chat):
        return "group", False
    if isinstance(entity, types.Channel):
        if getattr(entity, "megagroup", False):
            return "supergroup", getattr(entity, "forum", False)
        return "channel", False
    return "unknown", False
