"""TDD: Tests for detection strategies."""
import pytest
from wikiki.models import EditEvent
from wikiki.rules import Flag, ThreeRRStrategy, VelocitySpikeStrategy, EditorConflictStrategy


def make_edit(title="Alpha", user="alice", timestamp=1000, comment=""):
    return EditEvent(
        title=title, user=user, bot=False, timestamp=timestamp,
        comment=comment, length_old=100, length_new=90,
        revision_old=1, revision_new=2,
    )


def revert(title="Alpha", user="alice", timestamp=1000):
    return make_edit(title=title, user=user, timestamp=timestamp,
                     comment="Reverted edits by Bob")


STRATEGY = ThreeRRStrategy(window_seconds=86400)


def test_no_flag_on_first_revert():
    assert STRATEGY.evaluate(revert(timestamp=1000), history=[]) is None


def test_no_flag_on_second_revert():
    history = [revert(timestamp=500)]
    assert STRATEGY.evaluate(revert(timestamp=1000), history=history) is None


def test_flag_on_third_revert():
    history = [revert(timestamp=500), revert(timestamp=750)]
    flag = STRATEGY.evaluate(revert(timestamp=1000), history=history)
    assert flag is not None
    assert flag.type == "3RR"
    assert flag.title == "Alpha"


def test_flag_has_positive_weight():
    history = [revert(timestamp=500), revert(timestamp=750)]
    flag = STRATEGY.evaluate(revert(timestamp=1000), history=history)
    assert flag.weight > 0


def test_no_flag_for_non_revert_event():
    history = [revert(timestamp=500), revert(timestamp=750)]
    normal_edit = make_edit(timestamp=1000, comment="Fixed typo")
    assert STRATEGY.evaluate(normal_edit, history=history) is None


def test_no_flag_when_history_reverts_are_by_different_user():
    history = [revert(user="bob", timestamp=500), revert(user="carol", timestamp=750)]
    assert STRATEGY.evaluate(revert(user="alice", timestamp=1000), history=history) is None


def test_no_flag_when_history_reverts_are_on_different_article():
    history = [revert(title="Beta", timestamp=500), revert(title="Gamma", timestamp=750)]
    assert STRATEGY.evaluate(revert(title="Alpha", timestamp=1000), history=history) is None


def test_reverts_outside_window_are_ignored():
    window = 3600
    strategy = ThreeRRStrategy(window_seconds=window)
    # history reverts are older than the window
    history = [revert(timestamp=0), revert(timestamp=1)]
    current = revert(timestamp=window + 100)  # cutoff = 100, history is before that
    assert strategy.evaluate(current, history=history) is None


def test_reverts_inside_window_are_counted():
    window = 3600
    strategy = ThreeRRStrategy(window_seconds=window)
    base = 10000
    history = [revert(timestamp=base - 100), revert(timestamp=base - 200)]
    current = revert(timestamp=base)
    assert strategy.evaluate(current, history=history) is not None


def test_flag_on_fourth_revert_also_fires():
    history = [revert(timestamp=500), revert(timestamp=750), revert(timestamp=900)]
    flag = STRATEGY.evaluate(revert(timestamp=1000), history=history)
    assert flag is not None


# --- VelocitySpikeStrategy ---

VELOCITY = VelocitySpikeStrategy(window_seconds=3600, threshold=5)


def test_velocity_no_flag_below_threshold():
    history = [make_edit(timestamp=i * 100) for i in range(3)]
    assert VELOCITY.evaluate(make_edit(timestamp=1000), history=history) is None


def test_velocity_flag_at_threshold():
    # 4 in history + 1 current = 5 = threshold
    history = [make_edit(timestamp=i * 100) for i in range(4)]
    flag = VELOCITY.evaluate(make_edit(timestamp=1000), history=history)
    assert flag is not None
    assert flag.type == "VELOCITY_SPIKE"
    assert flag.title == "Alpha"


def test_velocity_flag_above_threshold():
    history = [make_edit(timestamp=i * 100) for i in range(10)]
    assert VELOCITY.evaluate(make_edit(timestamp=1000), history=history) is not None


def test_velocity_no_flag_for_single_edit():
    assert VELOCITY.evaluate(make_edit(timestamp=1000), history=[]) is None


def test_velocity_edits_on_different_article_not_counted():
    history = [make_edit(title="Beta", timestamp=i * 100) for i in range(4)]
    assert VELOCITY.evaluate(make_edit(title="Alpha", timestamp=1000), history=history) is None


def test_velocity_edits_outside_window_not_counted():
    window = 3600
    strategy = VelocitySpikeStrategy(window_seconds=window, threshold=3)
    base = 10000
    # all history edits are before the cutoff
    history = [make_edit(timestamp=base - window - i) for i in range(10)]
    assert strategy.evaluate(make_edit(timestamp=base), history=history) is None


def test_velocity_flag_has_positive_weight():
    history = [make_edit(timestamp=i * 100) for i in range(4)]
    flag = VELOCITY.evaluate(make_edit(timestamp=1000), history=history)
    assert flag.weight > 0


# --- EditorConflictStrategy ---

CONFLICT = EditorConflictStrategy(window_seconds=3600, min_editors=3)


def test_conflict_no_flag_below_threshold():
    history = [make_edit(user="bob", timestamp=500)]
    assert CONFLICT.evaluate(make_edit(user="alice", timestamp=1000), history=history) is None


def test_conflict_flag_at_threshold():
    # alice + bob in history, carol is current = 3 distinct editors
    history = [make_edit(user="alice", timestamp=500), make_edit(user="bob", timestamp=700)]
    flag = CONFLICT.evaluate(make_edit(user="carol", timestamp=1000), history=history)
    assert flag is not None
    assert flag.type == "EDITOR_CONFLICT"
    assert flag.title == "Alpha"


def test_conflict_same_user_multiple_edits_counts_once():
    # bob edited twice, alice is current — only 2 distinct editors
    history = [make_edit(user="bob", timestamp=400), make_edit(user="bob", timestamp=600)]
    assert CONFLICT.evaluate(make_edit(user="alice", timestamp=1000), history=history) is None


def test_conflict_current_user_already_in_history_not_double_counted():
    # alice in history + bob in history + alice again as current = 2 distinct editors
    history = [make_edit(user="alice", timestamp=400), make_edit(user="bob", timestamp=600)]
    assert CONFLICT.evaluate(make_edit(user="alice", timestamp=1000), history=history) is None


def test_conflict_edits_on_different_article_not_counted():
    history = [make_edit(user="bob", title="Beta", timestamp=500),
               make_edit(user="carol", title="Beta", timestamp=700)]
    assert CONFLICT.evaluate(make_edit(user="alice", title="Alpha", timestamp=1000), history=history) is None


def test_conflict_edits_outside_window_not_counted():
    window = 3600
    strategy = EditorConflictStrategy(window_seconds=window, min_editors=3)
    base = 10000
    history = [make_edit(user="bob", timestamp=base - window - 1),
               make_edit(user="carol", timestamp=base - window - 2)]
    assert strategy.evaluate(make_edit(user="alice", timestamp=base), history=history) is None


def test_conflict_flag_has_positive_weight():
    history = [make_edit(user="alice", timestamp=500), make_edit(user="bob", timestamp=700)]
    flag = CONFLICT.evaluate(make_edit(user="carol", timestamp=1000), history=history)
    assert flag.weight > 0
