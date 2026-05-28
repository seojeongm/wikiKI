"""TDD: Tests for Coordinator."""
import pytest
from wikiki.coordinator import ArticleStats, Coordinator
from wikiki.models import EditEvent
from wikiki.rules import RuleEngine, ThreeRRStrategy
from wikiki.scorer import TensionScorer
from wikiki.storage import connect


class FakeDashboard:
    def __init__(self):
        self.updates = []

    def update(self, stats: ArticleStats) -> None:
        self.updates.append(stats)


@pytest.fixture
def db():
    conn = connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def dashboard():
    return FakeDashboard()


@pytest.fixture
def coordinator(db, dashboard):
    engine = RuleEngine()
    engine.add_strategy(ThreeRRStrategy(window_seconds=3600))
    return Coordinator(conn=db, engine=engine, scorer=TensionScorer(),
                       dashboard=dashboard, window_seconds=3600)


def make_edit(title="Alpha", user="alice", timestamp=1000, comment=""):
    return EditEvent(title=title, user=user, bot=False, timestamp=timestamp,
                     comment=comment, length_old=100, length_new=110,
                     revision_old=1, revision_new=2)


def revert(title="Alpha", user="alice", timestamp=1000):
    return make_edit(title=title, user=user, timestamp=timestamp,
                     comment="Reverted edits by Bob")


class TestHandlePersists:
    def test_event_is_saved_to_db(self, coordinator, db):
        coordinator.handle(make_edit(timestamp=1000))
        count = db.execute("SELECT COUNT(*) FROM edit_events").fetchone()[0]
        assert count == 1


class TestHandleReturnsStats:
    def test_returns_article_stats_instance(self, coordinator):
        assert isinstance(coordinator.handle(make_edit(timestamp=1000)), ArticleStats)

    def test_stats_title_matches_event(self, coordinator):
        stats = coordinator.handle(make_edit(title="Alpha", timestamp=1000))
        assert stats.title == "Alpha"


class TestHandleDashboard:
    def test_dashboard_update_is_called(self, coordinator, dashboard):
        coordinator.handle(make_edit(timestamp=1000))
        assert len(dashboard.updates) == 1

    def test_dashboard_receives_article_stats(self, coordinator, dashboard):
        coordinator.handle(make_edit(timestamp=1000))
        assert isinstance(dashboard.updates[0], ArticleStats)


class TestHandleStatsFields:
    def test_edit_velocity_counts_all_events_in_window(self, coordinator):
        coordinator.handle(make_edit(timestamp=1000))
        coordinator.handle(make_edit(timestamp=2000))
        stats = coordinator.handle(make_edit(timestamp=3000))
        assert stats.edit_velocity == 3

    def test_editor_count_deduplicates_users(self, coordinator):
        coordinator.handle(make_edit(user="alice", timestamp=1000))
        coordinator.handle(make_edit(user="alice", timestamp=2000))
        stats = coordinator.handle(make_edit(user="bob", timestamp=3000))
        assert stats.editor_count == 2

    def test_revert_count(self, coordinator):
        coordinator.handle(make_edit(timestamp=1000, comment="normal edit"))
        coordinator.handle(revert(timestamp=2000))
        stats = coordinator.handle(revert(timestamp=3000))
        assert stats.revert_count == 2

    def test_tension_score_zero_when_no_flags(self, coordinator):
        stats = coordinator.handle(make_edit(timestamp=1000))
        assert stats.tension_score == 0.0

    def test_tension_score_nonzero_when_3rr_triggered(self, coordinator):
        coordinator.handle(revert(timestamp=1000))
        coordinator.handle(revert(timestamp=2000))
        stats = coordinator.handle(revert(timestamp=3000))
        assert stats.tension_score > 0

    def test_status_calm_when_no_flags(self, coordinator):
        stats = coordinator.handle(make_edit(timestamp=1000))
        assert stats.status == "calm"


class TestHandleIsolation:
    def test_different_articles_have_separate_history(self, coordinator):
        coordinator.handle(make_edit(title="Alpha", timestamp=1000))
        stats = coordinator.handle(make_edit(title="Beta", timestamp=1000))
        assert stats.edit_velocity == 1
