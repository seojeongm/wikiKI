"""TDD: Tests for SQLite storage of EditEvent."""
import pytest
from wikiki.models import EditEvent
from wikiki.storage import connect, save_event

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
