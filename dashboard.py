import sys
import time
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import streamlit as st
from wikiki.fixtures import DASHBOARD_STATS, SAMPLE_ARTICLES
from wikiki.models import ArticleStats

REFRESH_INTERVAL = 30

FLAG_LABELS: dict[str, str] = {
    "3RR": "3RR breach",
    "MUTUAL_REVERT": "mutual reverts",
    "VELOCITY_SPIKE": "velocity spike",
    "EDITOR_CONFLICT": "editor conflict",
    "SEMI_PROTECTED": "semi-protected",
    "NEW_ACCOUNT": "new account editing",
    "BLP": "BLP article",
    "BLP_EDITOR": "BLP editor active",
}

FLAG_COLORS: dict[str, tuple[str, str]] = {
    "3RR":            ("#ef4444", "#2d0a0a"),
    "MUTUAL_REVERT":  ("#f97316", "#2d1200"),
    "VELOCITY_SPIKE": ("#f59e0b", "#2d1f00"),
    "EDITOR_CONFLICT":("#ef4444", "#2d0a0a"),
    "SEMI_PROTECTED": ("#a78bfa", "#1a0d2d"),
    "NEW_ACCOUNT":    ("#eab308", "#2d2600"),
    "BLP":            ("#60a5fa", "#00122d"),
    "BLP_EDITOR":     ("#22d3ee", "#00232d"),
}

STATUS_COLORS: dict[str, str] = {
    "escalating": "#ef4444",
    "watching":   "#f59e0b",
    "low risk":   "#22c55e",
}

STATUS_ARROWS: dict[str, str] = {
    "escalating": "↑",
    "watching":   "→",
    "low risk":   "↓",
}


def _flag_chip(flag_type: str) -> str:
    label = FLAG_LABELS.get(flag_type, flag_type.lower().replace("_", " "))
    color, bg = FLAG_COLORS.get(flag_type, ("#9ca3af", "#1f2937"))
    return (
        f'<span style="background:{bg};color:{color};padding:3px 10px;'
        f'border-radius:9999px;font-size:12px;font-weight:600;'
        f'border:1px solid {color}33;white-space:nowrap;">'
        f"{label}</span>"
    )


def _article_card(article: ArticleStats) -> str:
    chips = " ".join(_flag_chip(f) for f in article.flags)
    status_color = STATUS_COLORS.get(article.status, "#9ca3af")
    arrow = STATUS_ARROWS.get(article.status, "")
    score_color = status_color

    meta = (
        f"✎ {article.editor_count} editors"
        f" &nbsp;•&nbsp; ↩ {article.revert_count} reverts"
        f" &nbsp;•&nbsp; last edit {article.last_edit_min} min ago"
    )

    return f"""
<div style="background:#1a1d24;border:1px solid #2d3139;border-radius:10px;
            padding:18px 22px;margin-bottom:12px;
            display:flex;justify-content:space-between;align-items:flex-start;">
  <div style="flex:1;min-width:0;margin-right:24px;">
    <div style="color:#e5e7eb;font-size:16px;font-weight:600;
                margin-bottom:10px;line-height:1.4;">
      {article.title}
    </div>
    <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px;">
      {chips}
    </div>
    <div style="color:#6b7280;font-size:12px;">{meta}</div>
  </div>
  <div style="text-align:right;flex-shrink:0;">
    <div style="font-size:38px;font-weight:700;color:{score_color};
                line-height:1;">{int(article.tension_score)}</div>
    <div style="color:#6b7280;font-size:11px;margin:2px 0 4px;">tension score</div>
    <div style="color:{status_color};font-size:12px;font-weight:600;">
      {arrow} {article.status}
    </div>
  </div>
</div>
"""


def render() -> None:
    st.set_page_config(page_title="wikiKI", layout="wide", page_icon="📡")

    st.markdown(
        """<style>
        #MainMenu, footer, header {visibility: hidden;}
        .block-container {padding-top: 1.5rem; max-width: 960px;}
        div[data-testid="metric-container"] {
            background: #1a1d24;
            border: 1px solid #2d3139;
            border-radius: 10px;
            padding: 16px 20px;
        }
        </style>""",
        unsafe_allow_html=True,
    )

    # --- Header ---
    st.markdown(
        f"""<div style="display:flex;justify-content:space-between;
                        align-items:center;margin-bottom:24px;">
          <span style="font-size:22px;font-weight:800;
                       color:#e5e7eb;letter-spacing:-0.5px;">wikiKI</span>
          <span style="color:#6b7280;font-size:13px;">
            <span style="color:#22c55e;font-weight:700;">● live</span>
            &nbsp;• enwiki &nbsp;•&nbsp;
            <strong style="color:#e5e7eb;">
              {DASHBOARD_STATS["edits_tracked_today"]:,}
            </strong> edits tracked today
          </span>
        </div>""",
        unsafe_allow_html=True,
    )

    # --- Top metric cards ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("articles monitored",
              f"{DASHBOARD_STATS['articles_monitored']:,}")
    c2.metric("flagged now",
              str(DASHBOARD_STATS["flagged_now"]))
    c3.metric("3RR breaches today",
              str(DASHBOARD_STATS["three_rr_breaches_today"]))
    c4.metric("avg edit velocity",
              f"{DASHBOARD_STATS['avg_edit_velocity']} /hr")

    st.markdown("<br>", unsafe_allow_html=True)

    # --- Article list ---
    st.markdown(
        '<p style="color:#6b7280;font-size:11px;font-weight:700;'
        'letter-spacing:1.5px;margin-bottom:12px;">ARTICLES UNDER TENSION</p>',
        unsafe_allow_html=True,
    )

    sorted_articles = sorted(
        SAMPLE_ARTICLES, key=lambda a: a.tension_score, reverse=True
    )
    for article in sorted_articles:
        st.markdown(_article_card(article), unsafe_allow_html=True)

    # --- Auto-refresh ---
    time.sleep(REFRESH_INTERVAL)
    st.rerun()


if __name__ == "__main__":
    render()
