import asyncio
from pathlib import Path

import pytest

from tg_keyword_forwarder.config import Config, CursorState, SourceConfig
from tg_keyword_forwarder.runner import run_sources


class FailingDeleteClient:
    async def delete_all_messages(self, destination_chat_id: int) -> int:
        raise RuntimeError("not allowed")


def test_run_sources_aborts_on_destination_preclean_failure(tmp_path: Path) -> None:
    config = Config(
        destination_chat_id=123,
        sources=[
            SourceConfig(
                chat_id=456,
                chat_name=None,
                topic_id=None,
                keywords=["alpha"],
                cursor=CursorState(last_message_id=None, last_timestamp=None),
            )
        ],
        raw={},
        path=tmp_path / "config.yaml",
    )
    client = FailingDeleteClient()

    with pytest.raises(RuntimeError, match="Destination chat pre-clean failed"):
        asyncio.run(run_sources(client, config))
