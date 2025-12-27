from datetime import datetime, timezone
from pathlib import Path

import yaml

from tg_keyword_forwarder.config import Config, CursorState, SourceConfig
from tg_keyword_forwarder.storage import apply_cursor_updates, atomic_write_yaml, merge_cursor


def test_merge_cursor_uses_max_values():
    older = datetime(2024, 1, 1, tzinfo=timezone.utc)
    newer = datetime(2024, 1, 2, tzinfo=timezone.utc)
    existing = CursorState(last_message_id=10, last_timestamp=older)
    incoming = CursorState(last_message_id=5, last_timestamp=newer)
    merged = merge_cursor(existing, incoming)
    assert merged.last_message_id == 10
    assert merged.last_timestamp == newer


def test_atomic_write_yaml_creates_file(tmp_path):
    path = tmp_path / "config.yaml"
    data = {"destination_chat_id": 1, "sources": []}
    atomic_write_yaml(path, data)
    assert path.exists()
    assert yaml.safe_load(path.read_text(encoding="utf-8")) == data
    temp_files = [p for p in Path(tmp_path).iterdir() if p.name.startswith(".config.yaml.")]
    assert not temp_files


def test_apply_cursor_updates_does_not_regress(tmp_path):
    path = tmp_path / "config.yaml"
    raw = {
        "destination_chat_id": 1,
        "sources": [
            {
                "chat_id": 2,
                "keywords": ["foo"],
                "cursor": {"last_message_id": 10},
            }
        ],
    }
    config = Config(
        destination_chat_id=1,
        sources=[
            SourceConfig(
                chat_id=2,
                chat_name=None,
                topic_id=None,
                keywords=["foo"],
                cursor=CursorState(10, None),
            )
        ],
        raw=raw,
        path=path,
    )
    updated = apply_cursor_updates(config, {(2, None): CursorState(5, None)})
    assert updated["sources"][0]["cursor"]["last_message_id"] == 10
