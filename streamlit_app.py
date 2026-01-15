import math
from datetime import datetime

import streamlit.components.v1 as components
import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh


# -----------------------
# Theme / Branding
# -----------------------
DARK_BLUE = "#125670"
LIGHT_GREY = "#e0e4ec"
ORANGE = "#f5b71a"

st.set_page_config(page_title="NASEA Leaderboard", layout="wide")

# Auto-refresh (ms). You can tune this later.
refresh_count = st_autorefresh(interval=10000, limit=None, key="nasea_refresh")

# Rows shown at a time in the auto-scroll list
PAGE_SIZE = 18


# -----------------------
# Helpers
# -----------------------
def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Converts Google Form / CSV column headers into a stable internal schema.
    Handles slight variations in EM column naming.
    """

    # Pick whichever EM column exists
    em_col = None
    if "EM Questions Completed" in df.columns:
        em_col = "EM Questions Completed"
    elif "EM Question Completed" in df.columns:
        em_col = "EM Question Completed"

    # Best case: headers match (Team, Cost, Outcome, EM)
    if em_col and all(c in df.columns for c in ["Team Name", "Supply Cost in $", "Outcome"]):
        out = df[["Team Name", "Supply Cost in $", "Outcome", em_col]].copy()
        out.columns = ["team_name", "cost_k", "outcome", "em_completed"]
        return out

    # Fallback: assume standard Google Form order with Timestamp first
    # [Timestamp, Team Name, Supply Cost in $, Outcome, EM Question(s) Completed]
    if len(df.columns) >= 5:
        out = df.iloc[:, 1:5].copy()
        out.columns = ["team_name", "cost_k", "outcome", "em_completed"]
        return out

    raise ValueError(f"Could not normalize columns. Found columns: {list(df.columns)}")


def compute_score_k(cost_k: float, outcome: str, em_completed: str) -> float:
    """
    Lower is better. All math is done in $K.
    - Cracked Egg: +$1,000,000  => +1,000K
    - Broken Egg:  +$10,000,000 => +10,000K
    - EM refund:   -$10,000     => -10K
    """
    o = str(outcome).strip().lower()

    penalty_k = 0
    if o == "cracked egg":
        penalty_k = 1_000
    elif o == "broken egg":
        penalty_k = 10_000

    refund_k = 10 if str(em_completed).strip().lower() in {"yes", "y", "true"} else 0
    return float(cost_k) + penalty_k - refund_k


def outcome_badge(outcome: str) -> str:
    o = str(outcome).strip().lower()
    if o == "unharmed egg":
        return "✅ CLEARED"
    if o == "cracked egg":
        return "⚖️ LITIGATION"
    if o == "broken egg":
        return "💸 F&F CLAIM"
    return str(outcome)


def esc_html(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render_leaderboard_table(df_view: pd.DataFrame) -> None:
    """
    Render a compact fixed-width table for projector display using an HTML component.
    Uses conference colors + fonts:
      - Raleway for headers
      - Muli for body text
    """

    def esc(s: str) -> str:
        return (
            str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    rows_html = "\n".join(
        f"""
        <tr>
          <td class="rank">{int(r['Rank'])}</td>
          <td class="team">{esc(r['Team'])}</td>
          <td class="score">{esc(r['Score'])}</td>
          <td class="status">{esc(r['Status'])}</td>
        </tr>
        """
        for _, r in df_view.iterrows()
    )

    html = f"""
    <html>
      <head>
        <style>
          @import url('https://fonts.googleapis.com/css2?family=Raleway:wght@600;700;800&family=Muli:wght@300;400;600;700&display=swap');

          body {{
            margin: 0;
            padding: 0;
            background: {DARK_BLUE};
            color: {LIGHT_GREY};
            font-family: 'Muli', sans-serif;
          }}

          table.lb {{
            width: 100%;
            border-collapse: collapse;
            font-size: 24px;
            background: rgba(255, 255, 255, 0.04);
            border-radius: 14px;
            overflow: hidden;
          }}

          thead tr {{
            background: {DARK_BLUE}; /* approved color (dark blue) */
          }}

          th {{
            text-align: left;
            padding: 12px 14px;
            border-bottom: 3px solid {ORANGE}; /* orange accent */
            white-space: nowrap;
            font-family: 'Raleway', sans-serif;
            font-weight: 800;
            color: {LIGHT_GREY};
          }}

          td {{
            padding: 12px 14px;
            border-bottom: 1px solid rgba(224, 228, 236, 0.14);
            vertical-align: middle;
          }}

          tbody tr:nth-child(odd) {{
            background: rgba(255, 255, 255, 0.03);
          }}

          tbody tr:nth-child(even) {{
            background: rgba(255, 255, 255, 0.01);
          }}

          td.rank, th.rank {{
            width: 4ch;
            text-align: right;
            font-variant-numeric: tabular-nums;
          }}

          td.score, th.score {{
            width: 14ch; /* "$15,000,000" fits */
            text-align: right;
            font-variant-numeric: tabular-nums;
          }}

          td.status, th.status {{
            width: 14ch;
            white-space: nowrap;
          }}

          td.team, th.team {{
            width: auto;
          }}
        </style>
      </head>
      <body>
        <table class="lb">
          <thead>
            <tr>
              <th class="rank">#</th>
              <th class="team">Team</th>
              <th class="score">Score</th>
              <th class="status">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows_html}
          </tbody>
        </table>
      </body>
    </html>
    """

    # Height: enough for ~PAGE_SIZE rows at 24px font. Tune if needed.
    components.html(html, height=60 + (PAGE_SIZE * 46), scrolling=False)


# -----------------------
# Read data (Published CSV)
# -----------------------
st.title("🥚 NASEA Re-entry Leaderboard 🥚")
st.markdown(
    "<div class='nasea-caption'>Lowest score wins. Scores shown as familiar large numbers in $ (even though teams enter cost in $K). Updates automatically.</div>",
    unsafe_allow_html=True,
)

@st.cache_data(ttl=10)
def load_sheet(csv_url: str) -> pd.DataFrame:
    return pd.read_csv(csv_url)

csv_url = st.secrets.get("leaderboard", {}).get("csv_url")
if not csv_url:
    st.error("Missing Streamlit secret: [leaderboard] csv_url")
    st.stop()

df = load_sheet(csv_url)

if df.empty:
    st.info("No submissions yet.")
    st.stop()

data = normalize_columns(df)

# Clean + validate
data["team_name"] = data["team_name"].astype(str).str.strip()
data["outcome"] = data["outcome"].astype(str).str.strip()
data["em_completed"] = data["em_completed"].astype(str).str.strip()

# Cost comes in as $K from the form now.
# Strip commas and coerce to number.
data["cost_k"] = data["cost_k"].astype(str).str.replace(",", "", regex=False)
data["cost_k"] = pd.to_numeric(data["cost_k"], errors="coerce")

# Drop rows missing essentials
data = data.dropna(subset=["team_name", "cost_k", "outcome"])

# Compute score in K, then display as familiar $ amount
data["score_k"] = data.apply(lambda r: compute_score_k(r["cost_k"], r["outcome"], r["em_completed"]), axis=1)
data = data.sort_values(["score_k", "team_name"], ascending=[True, True]).reset_index(drop=True)
data["rank"] = range(1, len(data) + 1)
data["status"] = data["outcome"].map(outcome_badge)

# Display score as familiar dollars with commas
data["score_display"] = (data["score_k"] * 1000).round(0).astype(int).map(lambda x: f"${x:,}")

# -----------------------
# Single scrolling layout (projector friendly)
# -----------------------
last_updated = datetime.now().strftime("%H:%M:%S")

st.markdown(
    f"<div class='lb-meta'><span class='accent'>Last updated:</span> {last_updated} &nbsp; • &nbsp; "
    f"<span class='accent'>Total entries:</span> {len(data)}</div>",
    unsafe_allow_html=True,
)

total_pages = max(1, math.ceil(len(data) / PAGE_SIZE))
page = (refresh_count or 0) % total_pages
start = page * PAGE_SIZE
end = min(start + PAGE_SIZE, len(data))

view = data.iloc[start:end][["rank", "team_name", "score_display", "status"]].copy()
view = view.rename(columns={"rank": "Rank", "team_name": "Team", "score_display": "Score", "status": "Status"})

st.markdown(
    f"<div class='lb-meta'>Showing ranks <span class='accent'>{start+1}</span>–<span class='accent'>{end}</span> "
    f"of <span class='accent'>{len(data)}</span> (page {page+1}/{total_pages})</div>",
    unsafe_allow_html=True,
)

render_leaderboard_table(view)
