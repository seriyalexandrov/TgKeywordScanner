from types import SimpleNamespace

from tg_keyword_forwarder.matcher import match_message, normalize_keywords


def test_normalize_keywords_deduplicates():
    keywords = normalize_keywords([" Foo ", "foo", "bar", ""])
    assert keywords == ["Foo", "bar"]


def test_match_message_case_insensitive():
    message = SimpleNamespace(message="Hello BAR world")
    result = match_message(message, ["foo", "bar"])
    assert result.matched is True
    assert result.keyword.lower() == "bar"


def test_match_message_no_content():
    message = SimpleNamespace(message=None)
    result = match_message(message, ["foo"])
    assert result.matched is False
