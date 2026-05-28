"""TDD: Tests for ArticleStats dataclass."""
import pytest
from wikiki.models import ArticleStats


def make_stats(
    title="Test Article",
    editor_count=3,
    revert_count=2,
    edit_velocity=5.0,
    tension_score=42.0,
    status="watching",
    flags=None,
    last_edit_min=10,
):
    return ArticleStats(
        title=title,
        editor_count=editor_count,
        revert_count=revert_count,
        edit_velocity=edit_velocity,
        tension_score=tension_score,
        status=status,
        flags=flags if flags is not None else [],
        last_edit_min=last_edit_min,
    )


# --- Instantiation ---

def test_article_stats_can_be_created():
    stats = make_stats()
    assert stats.title == "Test Article"
    assert stats.editor_count == 3
    assert stats.revert_count == 2
    assert stats.edit_velocity == 5.0
    assert stats.tension_score == 42.0
    assert stats.status == "watching"
    assert stats.last_edit_min == 10


def test_flags_defaults_to_empty_list():
    stats = ArticleStats(
        title="A", editor_count=1, revert_count=0,
        edit_velocity=1.0, tension_score=0.0, status="low risk",
    )
    assert stats.flags == []


def test_last_edit_min_defaults_to_zero():
    stats = ArticleStats(
        title="A", editor_count=1, revert_count=0,
        edit_velocity=1.0, tension_score=0.0, status="low risk",
    )
    assert stats.last_edit_min == 0


# --- Field types ---

def test_tension_score_accepts_float():
    stats = make_stats(tension_score=99.9)
    assert isinstance(stats.tension_score, float)


def test_edit_velocity_accepts_float():
    stats = make_stats(edit_velocity=12.5)
    assert isinstance(stats.edit_velocity, float)


def test_flags_is_a_list():
    stats = make_stats(flags=["3RR", "VELOCITY_SPIKE"])
    assert isinstance(stats.flags, list)
    assert len(stats.flags) == 2


# --- Status values ---

@pytest.mark.parametrize("status", ["escalating", "watching", "low risk"])
def test_valid_status_values(status):
    stats = make_stats(status=status)
    assert stats.status == status


# --- Sorting ---

def test_sort_by_tension_score_descending():
    articles = [
        make_stats(title="Low", tension_score=10.0),
        make_stats(title="High", tension_score=90.0),
        make_stats(title="Mid", tension_score=50.0),
    ]
    sorted_articles = sorted(articles, key=lambda a: a.tension_score, reverse=True)
    assert [a.title for a in sorted_articles] == ["High", "Mid", "Low"]


def test_sort_stable_on_equal_tension_score():
    articles = [
        make_stats(title="Alpha", tension_score=50.0),
        make_stats(title="Beta", tension_score=50.0),
    ]
    sorted_articles = sorted(articles, key=lambda a: a.tension_score, reverse=True)
    assert [a.title for a in sorted_articles] == ["Alpha", "Beta"]


# --- Edge cases ---

def test_tension_score_zero():
    stats = make_stats(tension_score=0.0)
    assert stats.tension_score == 0.0


def test_tension_score_max():
    stats = make_stats(tension_score=100.0)
    assert stats.tension_score == 100.0


def test_revert_count_zero():
    stats = make_stats(revert_count=0)
    assert stats.revert_count == 0


def test_flags_with_all_known_types():
    flags = ["3RR", "VELOCITY_SPIKE", "EDITOR_CONFLICT"]
    stats = make_stats(flags=flags)
    assert stats.flags == flags
