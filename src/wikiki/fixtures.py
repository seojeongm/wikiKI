"""Dummy data matching the dashboard design mockup."""
from .models import ArticleStats

SAMPLE_ARTICLES: list[ArticleStats] = [
    ArticleStats(
        title="2024 United States presidential election",
        editor_count=8,
        revert_count=14,
        edit_velocity=14.0,
        tension_score=91.0,
        status="escalating",
        flags=["3RR", "MUTUAL_REVERT", "VELOCITY_SPIKE", "SEMI_PROTECTED"],
        last_edit_min=2,
    ),
    ArticleStats(
        title="Israel-Hamas war",
        editor_count=11,
        revert_count=9,
        edit_velocity=9.0,
        tension_score=78.0,
        status="escalating",
        flags=["MUTUAL_REVERT", "NEW_ACCOUNT", "VELOCITY_SPIKE"],
        last_edit_min=7,
    ),
    ArticleStats(
        title="Elon Musk",
        editor_count=5,
        revert_count=6,
        edit_velocity=6.0,
        tension_score=54.0,
        status="watching",
        flags=["VELOCITY_SPIKE", "BLP", "BLP_EDITOR"],
        last_edit_min=18,
    ),
    ArticleStats(
        title="Quantum computing",
        editor_count=3,
        revert_count=3,
        edit_velocity=2.0,
        tension_score=28.0,
        status="low risk",
        flags=["VELOCITY_SPIKE", "NEW_ACCOUNT"],
        last_edit_min=41,
    ),
]

DASHBOARD_STATS = {
    "articles_monitored": 3_841,
    "flagged_now": 17,
    "three_rr_breaches_today": 4,
    "avg_edit_velocity": 2.3,
    "edits_tracked_today": 1_247,
}
