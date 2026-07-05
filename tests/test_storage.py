"""TDD: Tests for SQLite storage of EditEvent."""
import pytest
from wikiki.models import EditEvent
from wikiki.storage import SQLiteRepository, connect

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


@pytest.fixture
def repo(db):
    return SQLiteRepository(db)


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
    def test_saves_event_to_db(self, repo, db):
        repo.save_event(SAMPLE_EVENT)
        row = db.execute("SELECT * FROM edit_events").fetchone()
        assert row is not None

    def test_saved_fields_are_correct(self, repo, db):
        repo.save_event(SAMPLE_EVENT)
        row = db.execute(
            "SELECT title, user, bot, timestamp, comment, "
            "length_old, length_new, revision_old, revision_new "
            "FROM edit_events"
        ).fetchone()
        assert row == (
            "Python (programming language)", "Alice", 0,
            1779109905, "Fixed typo", 100, 120, 1000, 1001,
        )

    def test_bot_stored_as_integer(self, repo, db):
        repo.save_event(EditEvent(**{**SAMPLE_EVENT.__dict__, "bot": True}))
        val = db.execute("SELECT bot FROM edit_events").fetchone()[0]
        assert val == 1

    def test_multiple_events_all_saved(self, repo, db):
        repo.save_event(SAMPLE_EVENT)
        repo.save_event(SAMPLE_EVENT)
        count = db.execute("SELECT COUNT(*) FROM edit_events").fetchone()[0]
        assert count == 2

    def test_empty_comment_saved(self, repo, db):
        event = EditEvent(**{**SAMPLE_EVENT.__dict__, "comment": ""})
        repo.save_event(event)
        val = db.execute("SELECT comment FROM edit_events").fetchone()[0]
        assert val == ""


def make_event(title="Alpha", user="alice", timestamp=1000):
    return EditEvent(
        title=title, user=user, bot=False, timestamp=timestamp,
        comment="edit", length_old=100, length_new=110,
        revision_old=1, revision_new=2,
    )


class TestFindByTitle:
    def test_returns_events_for_title(self, repo):
        repo.save_event(make_event(title="Alpha", timestamp=1000))
        results = repo.find_by_title("Alpha", window_seconds=9999, now=5000)
        assert len(results) == 1
        assert results[0].title == "Alpha"

    def test_excludes_other_titles(self, repo):
        repo.save_event(make_event(title="Alpha", timestamp=1000))
        repo.save_event(make_event(title="Beta", timestamp=1000))
        results = repo.find_by_title("Alpha", window_seconds=9999, now=5000)
        assert len(results) == 1
        assert results[0].title == "Alpha"

    def test_excludes_events_outside_window(self, repo):
        repo.save_event(make_event(title="Alpha", timestamp=100))
        repo.save_event(make_event(title="Alpha", timestamp=5000))
        results = repo.find_by_title("Alpha", window_seconds=1000, now=5000)
        assert len(results) == 1
        assert results[0].timestamp == 5000

    def test_returns_edit_event_instances(self, repo):
        repo.save_event(make_event(title="Alpha", timestamp=1000))
        results = repo.find_by_title("Alpha", window_seconds=9999, now=5000)
        assert isinstance(results[0], EditEvent)

    def test_ordered_oldest_first(self, repo):
        for ts in [3000, 1000, 2000]:
            repo.save_event(make_event(title="Alpha", timestamp=ts))
        results = repo.find_by_title("Alpha", window_seconds=9999, now=5000)
        assert [e.timestamp for e in results] == [1000, 2000, 3000]

    def test_empty_when_no_matching_events(self, repo):
        assert repo.find_by_title("Alpha", window_seconds=9999, now=5000) == []


class TestFindRecent:
    def test_returns_most_recent_events(self, repo):
        for ts in [1000, 2000, 3000]:
            repo.save_event(make_event(timestamp=ts))
        results = repo.find_recent(limit=2)
        assert len(results) == 2

    def test_ordered_newest_first(self, repo):
        for ts in [1000, 2000, 3000]:
            repo.save_event(make_event(timestamp=ts))
        results = repo.find_recent(limit=3)
        assert [e.timestamp for e in results] == [3000, 2000, 1000]

    def test_respects_limit(self, repo):
        for ts in range(10):
            repo.save_event(make_event(timestamp=ts))
        assert len(repo.find_recent(limit=5)) == 5

    def test_returns_edit_event_instances(self, repo):
        repo.save_event(make_event(timestamp=1000))
        results = repo.find_recent(limit=1)
        assert isinstance(results[0], EditEvent)

    def test_empty_when_no_events(self, repo):
        assert repo.find_recent(limit=10) == []

    def test_negative_limit_raises(self, repo):
        with pytest.raises(ValueError):
            repo.find_recent(limit=-1)


def make_redis_stats(**overrides):
    stats = {
        "editor_count": 2,
        "tension_score": 10.0,
        "status": "calm",
        "flags": [],
        "last_seen_at": 1000,
    }
    stats.update(overrides)
    return stats


class TestAccumulateStatsBatchCommit:
    """Batched commits: writes become durable per batch, not per evict."""

    @pytest.fixture
    def file_db(self, tmp_path):
        conn = connect(str(tmp_path / "batch.db"))
        yield conn
        conn.close()

    @pytest.fixture
    def reader(self, tmp_path, file_db):
        conn = connect(str(tmp_path / "batch.db"))
        yield conn
        conn.close()

    @staticmethod
    def committed_count(reader):
        return reader.execute("SELECT COUNT(*) FROM article_stats").fetchone()[0]

    def test_holds_commit_until_batch_size(self, file_db, reader):
        repo = SQLiteRepository(file_db, commit_batch=3, max_commit_delay_seconds=9999)
        for i in range(2):
            repo.accumulate_stats(make_event(title=f"T{i}"), make_redis_stats(), count=5)
        assert self.committed_count(reader) == 0

    def test_commits_when_batch_size_reached(self, file_db, reader):
        repo = SQLiteRepository(file_db, commit_batch=3, max_commit_delay_seconds=9999)
        for i in range(3):
            repo.accumulate_stats(make_event(title=f"T{i}"), make_redis_stats(), count=5)
        assert self.committed_count(reader) == 3

    def test_flush_commits_pending_writes(self, file_db, reader):
        repo = SQLiteRepository(file_db, commit_batch=100, max_commit_delay_seconds=9999)
        repo.accumulate_stats(make_event(title="T"), make_redis_stats(), count=5)
        assert self.committed_count(reader) == 0
        repo.flush()
        assert self.committed_count(reader) == 1

    def test_max_delay_forces_commit(self, file_db, reader):
        repo = SQLiteRepository(file_db, commit_batch=100, max_commit_delay_seconds=0)
        repo.accumulate_stats(make_event(title="T"), make_redis_stats(), count=5)
        assert self.committed_count(reader) == 1

    def test_skipped_write_does_not_count_toward_batch(self, file_db, reader):
        repo = SQLiteRepository(file_db, commit_batch=2, max_commit_delay_seconds=9999)
        repo.accumulate_stats(make_event(title="Rare"), make_redis_stats(), count=1)
        repo.accumulate_stats(make_event(title="T"), make_redis_stats(), count=5)
        assert self.committed_count(reader) == 0

    def test_save_event_flushes_pending_stats(self, file_db, reader):
        repo = SQLiteRepository(file_db, commit_batch=100, max_commit_delay_seconds=9999)
        repo.accumulate_stats(make_event(title="T"), make_redis_stats(), count=5)
        repo.save_event(make_event(title="Other"))
        assert self.committed_count(reader) == 1
