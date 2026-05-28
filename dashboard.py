import html
import sys
import time
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import streamlit as st
from wikiki.models import ArticleStats
from wikiki.storage import connect, get_all_stats

REFRESH_INTERVAL = 30

# --- Design tokens ---
TOKENS: dict[str, str] = {
    # surface
    "bg_card":       "#1a1d24",
    "border":        "#2d3139",
    # text
    "text_primary":  "#e5e7eb",
    "text_muted":    "#6b7280",
    # semantic colors
    "color_live":       "#22c55e",
    "color_escalating": "#ef4444",
    "color_watching":   "#f59e0b",
    "color_low_risk":   "#22c55e",
    "color_fallback":   "#9ca3af",
    # flag foreground colors
    "flag_3rr":        "#ef4444",
    "flag_revert":     "#f97316",
    "flag_velocity":   "#f59e0b",
    "flag_protected":  "#a78bfa",
    "flag_account":    "#eab308",
    "flag_blp":        "#60a5fa",
    "flag_blp_editor": "#22d3ee",
    # typography
    "fs_logo":       "28px",
    "fs_header":     "16px",
    "fs_card_title": "28px",
    "fs_chip":       "16px",
    "fs_meta":       "16px",
    "fs_score":      "42px",
    "fs_score_label":"16px",
    "fs_status":     "16px",
    "fs_section":    "12px",
    # layout
    "r_card":        "10px",
    "r_chip":        "9999px",
    "p_card":        "18px 22px",
    "p_chip":        "3px 10px",
    "gap_chips":     "6px",
}

FLAG_LABELS: dict[str, str] = {
    "3RR":            "3RR breach",
    "MUTUAL_REVERT":  "mutual reverts",
    "VELOCITY_SPIKE": "velocity spike",
    "EDITOR_CONFLICT":"editor conflict",
    "SEMI_PROTECTED": "semi-protected",
    "NEW_ACCOUNT":    "new account editing",
    "BLP":            "BLP article",
    "BLP_EDITOR":     "BLP editor active",
}

# (foreground, background) pairs derived from TOKENS
FLAG_COLORS: dict[str, tuple[str, str]] = {
    "3RR":            (TOKENS["flag_3rr"],        "#2d0a0a"),
    "MUTUAL_REVERT":  (TOKENS["flag_revert"],     "#2d1200"),
    "VELOCITY_SPIKE": (TOKENS["flag_velocity"],   "#2d1f00"),
    "EDITOR_CONFLICT":(TOKENS["flag_3rr"],        "#2d0a0a"),
    "SEMI_PROTECTED": (TOKENS["flag_protected"],  "#1a0d2d"),
    "NEW_ACCOUNT":    (TOKENS["flag_account"],    "#2d2600"),
    "BLP":            (TOKENS["flag_blp"],        "#00122d"),
    "BLP_EDITOR":     (TOKENS["flag_blp_editor"], "#00232d"),
}

STATUS_COLORS: dict[str, str] = {
    "calm":     TOKENS["color_low_risk"],
    "elevated": TOKENS["color_watching"],
    "tense":    TOKENS["color_watching"],
    "critical": TOKENS["color_escalating"],
}

STATUS_ARROWS: dict[str, str] = {
    "calm":     "↓",
    "elevated": "→",
    "tense":    "↑",
    "critical": "↑",
}


def _flag_chip(flag_type: str) -> str:
    label = FLAG_LABELS.get(flag_type, flag_type.lower().replace("_", " "))
    color, bg = FLAG_COLORS.get(flag_type, (TOKENS["color_fallback"], "#1f2937"))
    return (
        f'<span style="background:{bg};color:{color};'
        f'padding:{TOKENS["p_chip"]};border-radius:{TOKENS["r_chip"]};'
        f'font-size:{TOKENS["fs_chip"]};font-weight:600;'
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

    title = html.escape(article.title)
    t = TOKENS
    return f"""
<div style="background:{t['bg_card']};border:1px solid {t['border']};
            border-radius:{t['r_card']};padding:{t['p_card']};margin-bottom:12px;
            display:flex;justify-content:space-between;align-items:flex-start;">
  <div style="flex:1;min-width:0;margin-right:24px;">
    <div style="color:{t['text_primary']};font-size:{t['fs_card_title']};
                font-weight:600;margin-bottom:10px;line-height:1.4;">
      {title}
    </div>
    <div style="display:flex;flex-wrap:wrap;gap:{t['gap_chips']};margin-bottom:10px;">
      {chips}
    </div>
    <div style="color:{t['text_muted']};font-size:{t['fs_meta']};">{meta}</div>
  </div>
  <div style="text-align:right;flex-shrink:0;">
    <div style="font-size:{t['fs_score']};font-weight:700;color:{score_color};
                line-height:1;">{int(article.tension_score)}</div>
    <div style="color:{t['text_muted']};font-size:{t['fs_score_label']};
                margin:2px 0 4px;">tension score</div>
    <div style="color:{status_color};font-size:{t['fs_status']};font-weight:600;">
      {arrow} {article.status}
    </div>
  </div>
</div>
"""


def render() -> None:
    db_path = os.getenv("DB_PATH", "wikiki.db")
    db = connect(db_path)
    articles = get_all_stats(db)

    flagged = [a for a in articles if a.tension_score > 0]
    three_rr = [a for a in articles if "3RR" in a.flags]
    avg_velocity = (
        sum(a.edit_velocity for a in articles) / len(articles) if articles else 0.0
    )
    live_stats = {
        "articles_monitored": len(articles),
        "flagged_now": len(flagged),
        "three_rr_breaches_today": len(three_rr),
        "avg_edit_velocity": round(avg_velocity, 1),
        "edits_tracked_today": sum(int(a.edit_velocity) for a in articles),
    }

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

    t = TOKENS
    # --- Header ---
    st.markdown(
        f"""<div style="display:flex;justify-content:space-between;
                        align-items:center;margin-bottom:24px;">
          <span style="font-size:{t['fs_logo']};font-weight:800;
                       color:{t['text_primary']};letter-spacing:-0.5px;">wikiKI</span>
          <span style="color:{t['text_muted']};font-size:{t['fs_header']};">
            <span style="color:{t['color_live']};font-weight:700;">● live</span>
            &nbsp;• enwiki &nbsp;•&nbsp;
            <strong style="color:{t['text_primary']};">
              {live_stats["edits_tracked_today"]:,}
            </strong> edits tracked today
          </span>
        </div>""",
        unsafe_allow_html=True,
    )

    # --- Top metric cards ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("articles monitored",
              f"{live_stats['articles_monitored']:,}")
    c2.metric("flagged now",
              str(live_stats["flagged_now"]))
    c3.metric("3RR breaches today",
              str(live_stats["three_rr_breaches_today"]))
    c4.metric("avg edit velocity",
              f"{live_stats['avg_edit_velocity']} /hr")

    st.markdown("<br>", unsafe_allow_html=True)

    # --- Article list ---
    st.markdown(
        f'<p style="color:{t["text_muted"]};font-size:{t["fs_section"]};'
        'font-weight:700;letter-spacing:1.5px;margin-bottom:12px;">'
        'ARTICLES UNDER TENSION</p>',
        unsafe_allow_html=True,
    )

    if not articles:
        st.info("No articles tracked yet. Start main.py to begin receiving events.")
    else:
        for article in articles:
            st.markdown(_article_card(article), unsafe_allow_html=True)

    # --- Auto-refresh ---
    time.sleep(REFRESH_INTERVAL)
    st.rerun()


if __name__ == "__main__":
    render()
