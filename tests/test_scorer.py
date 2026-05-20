"""TDD: Tests for TensionScorer."""
from wikiki.scorer import TensionScorer
from wikiki.rules import Flag

scorer = TensionScorer()


def make_flag(weight: float) -> Flag:
    return Flag(type="TEST", title="Alpha", weight=weight)


def test_calculate_empty_flags_returns_zero():
    assert scorer.calculate([]) == 0.0


def test_calculate_single_flag():
    assert scorer.calculate([make_flag(0.5)]) == 50.0


def test_calculate_multiple_flags_summed():
    assert scorer.calculate([make_flag(0.3), make_flag(0.4)]) == 70.0


def test_calculate_clamped_to_100():
    assert scorer.calculate([make_flag(0.8), make_flag(0.8)]) == 100.0


def test_calculate_returns_float():
    assert isinstance(scorer.calculate([make_flag(0.5)]), float)


# --- to_status ---

def test_status_calm():
    assert scorer.to_status(0.0) == "calm"
    assert scorer.to_status(24.9) == "calm"


def test_status_elevated():
    assert scorer.to_status(25.0) == "elevated"
    assert scorer.to_status(49.9) == "elevated"


def test_status_tense():
    assert scorer.to_status(50.0) == "tense"
    assert scorer.to_status(74.9) == "tense"


def test_status_critical():
    assert scorer.to_status(75.0) == "critical"
    assert scorer.to_status(100.0) == "critical"
