"""Forwarding and copy fallback behavior."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from telethon.errors import RPCError
from telethon.tl import types

from tg_keyword_forwarder.telegram_client import TelegramClientWrapper

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ForwardResult:
    forwarded: bool
    copied: bool
    error: Optional[str]


async def forward_with_fallback(
    client: TelegramClientWrapper,
    destination_chat_id: int,
    message: types.Message,
) -> ForwardResult:
    try:
        await client.forward_message(destination_chat_id, message)
        return ForwardResult(forwarded=True, copied=False, error=None)
    except RPCError as exc:
        LOGGER.warning("Forward failed for message %s; attempting copy", message.id)
        try:
            if not _has_copyable_content(message):
                return ForwardResult(forwarded=False, copied=False, error="No copyable content")
            await client.copy_message(destination_chat_id, message)
            return ForwardResult(forwarded=False, copied=True, error=None)
        except RPCError as copy_exc:
            return ForwardResult(forwarded=False, copied=False, error=str(copy_exc))
        except Exception as copy_exc:  # noqa: BLE001
            return ForwardResult(forwarded=False, copied=False, error=str(copy_exc))
    except Exception as exc:  # noqa: BLE001
        return ForwardResult(forwarded=False, copied=False, error=str(exc))


def _has_copyable_content(message: types.Message) -> bool:
    if message.media:
        return True
    if message.message:
        return True
    return False
