# Telegram Keyword Forwarder

Local Python CLI that scans Telegram chats for keywords and forwards matches into a single destination chat.

## Requirements

- macOS with `python3`
- Environment variables: `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_SESSION_STRING`

## Config

Default path: `~/.telegram-scrapper-config.yaml` (override with `--config`).

Example:

```yaml
destination_chat_id: 123456789
sources:
  - chat_id: 11111111
    chat_name: "My Supergroup" # optional label
    keywords:
      - "keyword A"
      - "keyword B"
```

## Usage

```bash
./scripts/run.sh list-chats
./scripts/run.sh run --config ~/.telegram-scrapper-config.yaml
```

## Notes

- Cursors are managed by the tool inside the config file.
- Forwarding falls back to copy when forwarding is restricted.
