import textwrap

from tg_keyword_forwarder.config import load_config


def test_load_config_normalizes_keywords(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        textwrap.dedent(
            """\
            destination_chat_id: 1
            sources:
              - chat_id: 2
                keywords:
                  - " Foo "
                  - "foo"
                  - "bar"
                  - ""
            """
        ),
        encoding="utf-8",
    )

    config = load_config(str(config_path))
    assert config.destination_chat_id == 1
    assert config.sources[0].keywords == ["Foo", "bar"]


def test_load_config_accepts_chat_name(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        textwrap.dedent(
            """\
            destination_chat_id: 1
            sources:
              - chat_id: 2
                chat_name: "My Supergroup"
                keywords:
                  - "foo"
            """
        ),
        encoding="utf-8",
    )

    config = load_config(str(config_path))
    assert config.sources[0].chat_name == "My Supergroup"
