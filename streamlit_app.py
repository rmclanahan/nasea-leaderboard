import math
from datetime import datetime

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Converts Google Form / CSV column headers into a stable internal schema.

    Expected Google Form fields:
    - Team Name
    - Supply Cost in $
    - Outcome
    - EM Questions Completed
    """

    column_map = {
        "Team Name": "team_name",
        "Supply Cost in $": "cost",
        "Outcome": "outcome",
        "EM Questions Completed": "em_completed",
    }

    # Best case: headers match exactly
    if all(col in df.columns for col in column_map.keys()):
        out = df[list(column_map.keys())].copy()
        return out.rename(columns=column_map)

    # Fallback: assume Google Form default order with Timestamp first
    # [Timestamp, Team Name, Supply Cost in $, Outcome, EM Questions Completed]
    if len(df.columns) >= 5:
        out = df.iloc[:, 1:5].copy()
        out.columns = ["team_name", "cost", "outcome", "em_completed"]
        return out

    raise ValueError(f"Could not normalize columns. Found columns: {list(df.columns)}")


def compute_score(cost: float, outcome: str, em_completed: str) -> float:
    """Lower is better."""
    penalty = 0
    if outcome == "Cracked":
        penalty = 1_000_000
    elif outcome == "Broken":
        penalty = 10_000_000

    refund = 10_000 if str(em_completed).strip().lower() in {"yes", "y", "true"} else 0
    return float(cost) + penalty - refund


def outcome_badge(outcome: str) -> str:
    if outcome == "Survived":
        return "✅ CLEARED"
    if outcome == "Cracked":
        return "⚖️ LITIGATION"
    if outcome == "Broken":
        return "💸 F&F CLAIM"
    return outcome


# -----------------------
# Config
# -----------------------
st.set_page_config(page_title="NASEA Leaderboard", layout="wide")

# Auto-refresh every 5 seconds
refresh_count = st_autorefresh(interval=5000, limit=None, key="nasea_refresh")

# Display settings
TOP_N = 20
PAGE_SIZE = 15  # rows per "All Teams" page


# -----------------------
# Read data (Published CSV)
# -----------------------
st.title("🏛️ NASEA Re-entry Leaderboard")
st.caption("Lowest score wins. Updates automatically.")

@st.cache_data(ttl=5)
def load_sheet(csv_url: str) -> pd.DataFrame:
    return pd.read_csv(csv_url)

csv_url = st.secrets["leaderboard"]["csv_url"]
df = load_sheet(csv_url)

if df.empty:
    st.info("No submissions yet.")
    st.stop()

data = normalize_columns(df)

# Clean + validate
data["team_name"] = data["team_name"].astype(str).str.strip()
data["outcome"] = data["outcome"].astype(str).str.strip()
data["em_completed"] = data["em_completed"].astype(str).str.strip()

data["cost"] = pd.to_numeric(data["cost"], errors="coerce")
data = data.dropna(subset=["team_name", "cost", "outcome"])

# Compute score + rank
data["score"] = data.apply(lambda r: compute_score(r["cost"], r["outcome"], r["em_completed"]), axis=1)
data = data.sort_values(["score", "team_name"], ascending=[True, True]).reset_index(drop=True)
data["rank"] = range(1, len(data) + 1)
data["status"] = data["outcome"].map(outcome_badge)

# -----------------------
# Layout
# -----------------------
last_updated = datetime.now().strftime("%H:%M:%S")
st.write(f"**Last updated:** {last_updated}  •  **Total entries:** {len(data)}")

left, right = st.columns([1.2, 1])

with left:
    st.subheader(f"🏆 Top {min(TOP_N, len(data))}")
    top = data.head(TOP_N)[["rank", "team_name", "score", "status"]].copy()
    top = top.rename(columns={"rank": "Rank", "team_name": "Team", "score": "Score", "status": "Status"})
    st.dataframe(top, use_container_width=True, hide_index=True)

with right:
    st.subheader("📜 All Teams (auto-scroll)")
    total_pages = max(1, math.ceil(len(data) / PAGE_SIZE))

    page = (refresh_count or 0) % total_pages
    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, len(data))

    page_df = data.iloc[start:end][["rank", "team_name", "score", "status"]].copy()
    page_df = page_df.rename(columns={"rank": "Rank", "team_name": "Team", "score": "Score", "status": "Status"})

    st.caption(f"Showing ranks {start+1}–{end} of {len(data)} (page {page+1}/{total_pages})")
    st.dataframe(page_df, use_container_width=True, hide_index=True)
