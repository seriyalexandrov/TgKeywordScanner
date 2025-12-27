"""CLI entry points and argument parsing."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import Optional

from tg_keyword_forwarder.config import load_config
from tg_keyword_forwarder.logging_setup import configure_logging
from tg_keyword_forwarder.runner import list_chats, run_sources
from tg_keyword_forwarder.telegram_client import TelegramClientWrapper

LOGGER = logging.getLogger(__name__)


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    configure_logging(args.log_level)
    try:
        if args.command == "list-chats":
            asyncio.run(_handle_list_chats())
        elif args.command == "run":
            asyncio.run(_handle_run(args.config))
    except Exception:  # noqa: BLE001
        LOGGER.exception("Fatal error")
        sys.exit(1)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tg-keyword-forwarder")
    parser.add_argument("--config", help="Path to YAML config file")
    parser.add_argument("--log-level", default="INFO", help="Logging level (e.g. INFO, DEBUG)")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list-chats", help="List dialogs and forum topic IDs")
    subparsers.add_parser("run", help="Process configured sources")
    return parser


async def _handle_list_chats() -> None:
    async with TelegramClientWrapper.from_environment() as client:
        lines = await list_chats(client)
        for line in lines:
            print(line)


async def _handle_run(config_path: Optional[str]) -> None:
    config = load_config(config_path)
    async with TelegramClientWrapper.from_environment() as client:
        summary = await run_sources(client, config)
    for stats in summary.sources:
        LOGGER.info(
            "source chat_id=%s topic_id=%s scanned=%s matched=%s forwarded=%s errors=%s",
            stats.chat_id,
            stats.topic_id,
            stats.scanned,
            stats.matched,
            stats.forwarded,
            len(stats.errors),
        )
