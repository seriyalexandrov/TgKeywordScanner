# Telegram Keyword Scanner Architecture

## Library choice

This project uses [Telethon](https://github.com/LonamiWebs/Telethon) as the Telegram client library because it:

- Supports user sessions via `TELEGRAM_SESSION_STRING` (no interactive login prompts needed).
- Enumerates dialogs with entity metadata (title, ID, type).
- Iterates messages incrementally with `min_id`/`offset_date` to avoid full-history scans.
- Supports forwarding messages and re-sending/copying content.
- Exposes forum topic APIs (e.g., `GetForumTopicsRequest`) when available; otherwise, messages include
  thread identifiers (`reply_to_top_id`) that can be used to discover topics.

Known limitations and fallbacks:

- If topic enumeration is not supported or fails, list-chats will inspect recent messages for
  `reply_to_top_id` and print observed topic IDs.
- Forwarding may fail due to protected content; the tool will attempt a copy fallback (text/media/caption)
  and log a clear error if copying is not possible.

## Module layout

- `cli.py`: CLI entry point and argument parsing.
- `config.py`: load/validate YAML config.
- `storage.py`: atomic persistence of cursor updates.
- `telegram_client.py`: Telethon wrapper for auth, dialogs, topics, message fetch, forward/copy.
- `matcher.py`: keyword normalization and matching.
- `forwarder.py`: forward/copy behavior orchestration.
- `logging_setup.py`: structured logging configuration.
- `runner.py`: run-mode orchestration across sources.
- `utils.py`: shared helpers (time windows, retries, safe casting).

## Config schema (YAML)

```yaml
destination_chat_id: 123456789
sources:
  - chat_id: 11111111
    topic_id: 987654321   # optional, for forum topics only
    keywords:
      - "keyword A"
      - "keyword B"
    cursor:
      last_message_id: 42
      last_timestamp: "2024-01-01T12:00:00Z"
```

Notes:

- `cursor` is managed by the tool; users do not edit it.
- Cursors are tracked per `(chat_id, topic_id)` pair so a forum topic is independent from its parent chat.
- `last_message_id` is preferred; `last_timestamp` is used as fallback and on first-run 24h windows.

## Execution flow

1. Load config (default `~/.telegram-scrapper-config.yaml` or `--config` override).
2. Initialize logging and Telegram client using env session string.
3. `list-chats` mode: list dialogs; attempt forum topic enumeration or provide topic ID hints.
4. `run` mode:
   - For each source, compute the fetch window from cursor or last 24h.
   - Stream messages incrementally, match keywords, forward/copy.
   - Update cursor to max processed position and persist atomically.
5. Log per-source statistics and overall completion.
