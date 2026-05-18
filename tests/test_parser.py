"""TDD: Tests for enwiki filtering and event field parsing."""
import pytest
from wikiki.parser import is_enwiki_edit, parse_edit_event
from wikiki.models import EditEvent

SAMPLE = {
    "$schema": "/mediawiki/recentchange/1.0.0",
    "wiki": "enwiki",
    "type": "edit",
    "title": "Python (programming language)",
    "user": "Alice",
    "bot": False,
    "timestamp": 1779109905,
    "comment": "Fixed typo",
    "length": {"old": 100, "new": 120},
    "revision": {"old": 1000, "new": 1001},
    "server_name": "en.wikipedia.org",
}


class TestIsEnwikiEdit:
    def test_enwiki_edit_returns_true(self):
        assert is_enwiki_edit(SAMPLE) is True

    def test_other_wiki_filtered_out(self):
        assert is_enwiki_edit({**SAMPLE, "wiki": "dewiki"}) is False

    def test_commonswiki_filtered_out(self):
        assert is_enwiki_edit({**SAMPLE, "wiki": "commonswiki"}) is False

    def test_log_type_filtered_out(self):
        assert is_enwiki_edit({**SAMPLE, "type": "log"}) is False

    def test_new_type_filtered_out(self):
        assert is_enwiki_edit({**SAMPLE, "type": "new"}) is False

    def test_missing_wiki_key_returns_false(self):
        event = {k: v for k, v in SAMPLE.items() if k != "wiki"}
        assert is_enwiki_edit(event) is False


class TestParseEditEvent:
    def test_parses_all_required_fields(self):
        result = parse_edit_event(SAMPLE)
        assert isinstance(result, EditEvent)
        assert result.title == "Python (programming language)"
        assert result.user == "Alice"
        assert result.bot is False
        assert result.timestamp == 1779109905
        assert result.comment == "Fixed typo"
        assert result.length_old == 100
        assert result.length_new == 120
        assert result.revision_old == 1000
        assert result.revision_new == 1001

    def test_missing_comment_defaults_to_empty_string(self):
        event = {k: v for k, v in SAMPLE.items() if k != "comment"}
        result = parse_edit_event(event)
        assert result.comment == ""

    def test_bot_edit_parsed_correctly(self):
        result = parse_edit_event({**SAMPLE, "bot": True})
        assert result.bot is True

    def test_missing_title_raises_key_error(self):
        event = {k: v for k, v in SAMPLE.items() if k != "title"}
        with pytest.raises(KeyError):
            parse_edit_event(event)

    def test_missing_revision_raises_key_error(self):
        event = {k: v for k, v in SAMPLE.items() if k != "revision"}
        with pytest.raises(KeyError):
            parse_edit_event(event)

    def test_missing_length_raises_key_error(self):
        event = {k: v for k, v in SAMPLE.items() if k != "length"}
        with pytest.raises(KeyError):
            parse_edit_event(event)
