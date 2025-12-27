# Manual Validation Checklist

## Authentication and listing

- Run `scripts/run.sh list-chats` and verify it lists dialogs with IDs and types.
- For a forum-enabled supergroup, confirm topics are listed or `TOPIC_HINT` values appear.

## First-run behavior

- Configure a new source with no cursor and run `scripts/run.sh run`.
- Confirm only messages from the last 24 hours are scanned.

## Incremental behavior

- Run `scripts/run.sh run` twice without new messages and confirm no forwards occur.
- Post a new message containing a keyword and verify it forwards once.

## Forwarding restrictions

- Use a protected content channel and verify forward fails but copy fallback is attempted.
- Confirm errors are logged without stopping other sources.

## Topic monitoring

- Configure a source with `topic_id` and verify only that topic's messages are scanned.

## Error isolation

- Include one invalid source (e.g., unreachable chat) and verify other sources still process.
