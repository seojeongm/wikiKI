"""TDD: Tests for SQLite storage of EditEvent."""
import pytest
from wikiki.models import EditEvent
from wikiki.storage import connect, save_event, find_by_title, find_recent

SAMPLE_EVENT = EditEvent(
    title="Python (programming language)",
    user="Alice",
    bot=False,
    timestamp=1779109905,
    comment="Fixed typo",
    length_old=100,
    length_new=120,
    revision_old=1000,
    revision_new=1001,
)


@pytest.fixture
def db():
    conn = connect(":memory:")
    yield conn
    conn.close()


class TestConnect:
    def test_creates_edit_events_table(self, db):
        tables = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        assert ("edit_events",) in tables

    def test_table_has_required_columns(self, db):
        cols = {row[1] for row in db.execute("PRAGMA table_info(edit_events)")}
        assert cols >= {"title", "user", "bot", "timestamp", "comment",
                        "length_old", "length_new", "revision_old", "revision_new"}


class TestSaveEvent:
    def test_saves_event_to_db(self, db):
        save_event(db, SAMPLE_EVENT)
        row = db.execute("SELECT * FROM edit_events").fetchone()
        assert row is not None

    def test_saved_fields_are_correct(self, db):
        save_event(db, SAMPLE_EVENT)
        row = db.execute(
            "SELECT title, user, bot, timestamp, comment, "
            "length_old, length_new, revision_old, revision_new "
            "FROM edit_events"
        ).fetchone()
        assert row == (
            "Python (programming language)", "Alice", 0,
            1779109905, "Fixed typo", 100, 120, 1000, 1001,
        )

    def test_bot_stored_as_integer(self, db):
        save_event(db, EditEvent(**{**SAMPLE_EVENT.__dict__, "bot": True}))
        val = db.execute("SELECT bot FROM edit_events").fetchone()[0]
        assert val == 1

    def test_multiple_events_all_saved(self, db):
        save_event(db, SAMPLE_EVENT)
        save_event(db, SAMPLE_EVENT)
        count = db.execute("SELECT COUNT(*) FROM edit_events").fetchone()[0]
        assert count == 2

    def test_empty_comment_saved(self, db):
        event = EditEvent(**{**SAMPLE_EVENT.__dict__, "comment": ""})
        save_event(db, event)
        val = db.execute("SELECT comment FROM edit_events").fetchone()[0]
        assert val == ""


def make_event(title="Alpha", user="alice", timestamp=1000):
    return EditEvent(
        title=title, user=user, bot=False, timestamp=timestamp,
        comment="edit", length_old=100, length_new=110,
        revision_old=1, revision_new=2,
    )


class TestFindByTitle:
    def test_returns_events_for_title(self, db):
        save_event(db, make_event(title="Alpha", timestamp=1000))
        results = find_by_title(db, "Alpha", window_seconds=9999, now=5000)
        assert len(results) == 1
        assert results[0].title == "Alpha"

    def test_excludes_other_titles(self, db):
        save_event(db, make_event(title="Alpha", timestamp=1000))
        save_event(db, make_event(title="Beta", timestamp=1000))
        results = find_by_title(db, "Alpha", window_seconds=9999, now=5000)
        assert len(results) == 1
        assert results[0].title == "Alpha"

    def test_excludes_events_outside_window(self, db):
        save_event(db, make_event(title="Alpha", timestamp=100))
        save_event(db, make_event(title="Alpha", timestamp=5000))
        results = find_by_title(db, "Alpha", window_seconds=1000, now=5000)
        assert len(results) == 1
        assert results[0].timestamp == 5000

    def test_returns_edit_event_instances(self, db):
        save_event(db, make_event(title="Alpha", timestamp=1000))
        results = find_by_title(db, "Alpha", window_seconds=9999, now=5000)
        assert isinstance(results[0], EditEvent)

    def test_ordered_oldest_first(self, db):
        for ts in [3000, 1000, 2000]:
            save_event(db, make_event(title="Alpha", timestamp=ts))
        results = find_by_title(db, "Alpha", window_seconds=9999, now=5000)
        assert [e.timestamp for e in results] == [1000, 2000, 3000]

    def test_empty_when_no_matching_events(self, db):
        assert find_by_title(db, "Alpha", window_seconds=9999, now=5000) == []


class TestFindRecent:
    def test_returns_most_recent_events(self, db):
        for ts in [1000, 2000, 3000]:
            save_event(db, make_event(timestamp=ts))
        results = find_recent(db, limit=2)
        assert len(results) == 2

    def test_ordered_newest_first(self, db):
        for ts in [1000, 2000, 3000]:
            save_event(db, make_event(timestamp=ts))
        results = find_recent(db, limit=3)
        assert [e.timestamp for e in results] == [3000, 2000, 1000]

    def test_respects_limit(self, db):
        for ts in range(10):
            save_event(db, make_event(timestamp=ts))
        assert len(find_recent(db, limit=5)) == 5

    def test_returns_edit_event_instances(self, db):
        save_event(db, make_event(timestamp=1000))
        results = find_recent(db, limit=1)
        assert isinstance(results[0], EditEvent)

    def test_empty_when_no_events(self, db):
        assert find_recent(db, limit=10) == []
