import math
from datetime import datetime

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# -----------------------
# Config
# -----------------------
st.set_page_config(page_title="NASEA Leaderboard", layout="wide")

# Auto-refresh every 5 seconds (safe + "real-time enough")
refresh_count = st_autorefresh(interval=5000, limit=None, key="nasea_refresh")

# Display settings
TOP_N = 20
PAGE_SIZE = 15  # number of rows shown at a time in the "All Teams" scroller

# -----------------------
# Helpers
# -----------------------
def compute_score(cost: float, outcome: str, em_completed: str) -> float:
    """Lower is better."""
    penalty = 0
    if outcome == "Cracked":
        penalty = 1_000_000
    elif outcome == "Broken":
        penalty = 10_000_000

    refund = 10_000 if str(em_completed).strip().lower() in {"yes", "y", "true"} else 0
    return float(cost) + penalty - refund

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Handles common Google Form response shapes:
    - Timestamp column present
    - Your 4 fields present
    """
    # Try to locate by exact header names first (best case)
    expected = {
        "Team Name": None,
        "Supply Cost in $": None,
        "Outcome": None,
        "EM Questions Completed": None,
    }

    for col in df.columns:
        if col in expected:
            expected[col] = col

    if all(v is not None for v in expected.values()):
        out = df[list(expected.values())].copy()
        out.columns = ["team_name", "cost", "outcome", "em_completed"]
        return out

    # Fallback: assume Google Forms default: A=Timestamp, then B.. are your fields
    # If someone renamed the headers, this still works as long as order is same.
    # Columns: [Timestamp, Team Name, Supply Cost in $, Outcome, EM Questions Completed]
    if len(df.columns) >= 5:
        out = df.iloc[:, 1:5].copy()
        out.columns = ["team_name", "cost", "outcome", "em_completed"]
        return out

    raise ValueError(
        "Could not find the expected columns. "
        "Check your sheet headers match the form fields, or adjust normalize_columns()."
    )

# -----------------------
# Read data
# -----------------------
st.title("🏛️ NASEA Re-entry Leaderboard")
st.caption("Lowest score wins. Updates automatically.")

conn = st.connection("gsheets", type="gsheets")

# Read the worksheet that Google Forms writes into.
# Usually: "Form Responses 1"
raw = conn.read(worksheet="Form Responses 1", ttl=0)  # ttl=0 forces fresh reads
df = pd.DataFrame(raw)

if df.empty:
    st.info("No submissions yet.")
    st.stop()

data = normalize_columns(df)

# Clean + validate
data["team_name"] = data["team_name"].astype(str).str.strip()
data["outcome"] = data["outcome"].astype(str).str.strip()
data["em_completed"] = data["em_completed"].astype(str).str.strip()

# Costs may come through as strings depending on sheet formatting
data["cost"] = pd.to_numeric(data["cost"], errors="coerce")

# Drop rows missing essentials
data = data.dropna(subset=["team_name", "cost", "outcome"])

# Compute score + rank
data["score"] = data.apply(lambda r: compute_score(r["cost"], r["outcome"], r["em_completed"]), axis=1)
data = data.sort_values(["score", "team_name"], ascending=[True, True]).reset_index(drop=True)
data["rank"] = range(1, len(data) + 1)

# Outcome label for fun
def outcome_badge(outcome: str) -> str:
    if outcome == "Survived":
        return "✅ CLEARED"
    if outcome == "Cracked":
        return "⚖️ LITIGATION"
    if outcome == "Broken":
        return "💸 F&F CLAIM"
    return outcome

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
    top = top.rename(columns={"team_name": "Team", "score": "Score", "status": "Status", "rank": "Rank"})
    st.dataframe(top, use_container_width=True, hide_index=True)

with right:
    st.subheader("📜 All Teams (auto-scroll)")
    total_pages = max(1, math.ceil(len(data) / PAGE_SIZE))

    # Rotate pages based on refresh_count so it scrolls automatically on the projector
    page = (refresh_count or 0) % total_pages
    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, len(data))

    page_df = data.iloc[start:end][["rank", "team_name", "score", "status"]].copy()
    page_df = page_df.rename(columns={"team_name": "Team", "score": "Score", "status": "Status", "rank": "Rank"})

    st.caption(f"Showing ranks {start+1}–{end} of {len(data)} (page {page+1}/{total_pages})")
    st.dataframe(page_df, use_container_width=True, hide_index=True)
