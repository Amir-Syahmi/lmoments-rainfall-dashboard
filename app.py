# ---------------------------
# Rainfall Dashboard — OCD-friendly redesign (white-bar fix + legend spacing)
# ---------------------------
import os
import numpy as np
import pandas as pd
import streamlit as st
import lmoments3 as lm
from lmoments3 import distr
import pydeck as pdk
import plotly.graph_objects as go

st.set_page_config(
    page_title="Rainfall Dashboard",
    page_icon=":cloud_with_rain:",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- Scoped CSS ----------
st.markdown(
    """
    <style>
      .stApp { background: #f4f6f9; } /* soft gray */

      /* Card shell */
      .rf-card {
        background: #ffffff;
        border: 1px solid #e9edf3;
        border-radius: 14px;
        box-shadow: 0 6px 18px rgba(17,24,39,.06);
        padding: 16px 18px;
        margin-bottom: 18px;
      }
      .rf-card h3, .rf-card h4, .rf-card h5, .rf-card p, .rf-card label { color: #0f172a; }
      .soft { color: #6b7280; }

      /* Sidebar: dark, readable */
      section[data-testid="stSidebar"] > div { background: #111827; color: #e5e7eb; }
      section[data-testid="stSidebar"] h1,
      section[data-testid="stSidebar"] h2,
      section[data-testid="stSidebar"] h3,
      section[data-testid="stSidebar"] label,
      section[data-testid="stSidebar"] p { color: #f9fafb !important; }
      /* Radios on dark */
      section[data-testid="stSidebar"] .stRadio > div { flex-direction: column; }
      section[data-testid="stSidebar"] [role="radiogroup"] * { color: #f9fafb !important; fill: #f9fafb !important; }
      /* Select on dark */
      section[data-testid="stSidebar"] div[role="combobox"] {
        background: #fff !important; border: 1px solid #e5e7eb !important; border-radius: 10px !important;
      }
      section[data-testid="stSidebar"] div[role="combobox"] * { color: #111827 !important; }
      /* Year slider labels readable */
      section[data-testid="stSidebar"] div[data-baseweb="slider"] * { color: #e5e7eb !important; }

      /* Tables a touch smaller */
      .stDataFrame { font-size: 0.94rem; }

      /* === White-bar killer ===
         Hide any main-column vertical blocks that DON'T contain a card.
         This removes those strange empty "pill" bars above your first card. */
      main[data-testid="stAppViewContainer"] div[data-testid="column"] div[data-testid="stVerticalBlock"]:not(:has(.rf-card)) {
        display: none !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)
st.markdown(
    """
    <style>
      /* Remove any first empty block at the top of each column */
      main [data-testid="column"] > div > div:first-child:empty { display:none !important; }
      /* …and hide any non-card block that sneaks in above your first card */
      main [data-testid="column"] > div > div:first-child:not(:has(.rf-card)) { display:none !important; }
    </style>
    """,
    unsafe_allow_html=True
)


# ---------- Paths ----------
logo_path = "assets/unisza logo transparent.png"
data_base_dir = "data"
coord_path = os.path.join(data_base_dir, "merged_station_coordinates.csv")

# ---------- SIDEBAR ----------
with st.sidebar:
    st.image(logo_path, use_column_width=True)
    st.markdown("### Data Filters")

    time_scale_display = st.radio("Select Time Scale", ["Annual", "Daily"])
    time_scale = time_scale_display.lower()
    data_path = os.path.join(data_base_dir, time_scale)
    if not os.path.isdir(data_path):
        st.error(f"Data folder not found: `{data_path}`"); st.stop()

    if not os.path.exists(coord_path):
        st.error(f"Coordinates file not found: `{coord_path}`"); st.stop()
    coord_df = pd.read_csv(coord_path)

    station_files = [f for f in os.listdir(data_path) if f.endswith(".csv")]
    if not station_files:
        st.error(f"No CSV files in `{data_path}`"); st.stop()

    station_ids = [os.path.splitext(f)[0] for f in station_files]
    id_to_name = dict(zip(coord_df.get("File", []), coord_df.get("Station Name", [])))
    display_names = [id_to_name.get(s, s) for s in station_ids]

    display_choice = st.selectbox("Select Station", options=display_names)
    station_id = station_ids[display_names.index(display_choice)]
    file_path = os.path.join(data_path, f"{station_id}.csv")

    if time_scale == "annual":
        df = pd.read_csv(file_path)
        if "Year" not in df.columns:
            st.error("Expected 'Year' column in Annual CSV."); st.stop()
        df["Date"] = pd.to_datetime(df["Year"].astype(str), format="%Y", errors="coerce")
        df = df.dropna(subset=["Date"])
        years = sorted(df["Date"].dt.year.astype(int).unique().tolist())
        if not years:
            st.error("No valid years found in Annual data."); st.stop()
        start_y, end_y = st.select_slider("Select Year Range", options=years, value=(min(years), max(years)))
        df = df[(df["Date"].dt.year >= start_y) & (df["Date"].dt.year <= end_y)]
    else:
        df = pd.read_csv(file_path)
        if "Date" not in df.columns:
            st.error("Expected 'Date' column in Daily CSV."); st.stop()
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["Date"])
        min_date = df["Date"].min().date(); max_date = df["Date"].max().date()
        c1, c2 = st.columns(2)
        with c1:
            d_from = st.date_input("From", value=min_date, min_value=min_date, max_value=max_date)
        with c2:
            d_to = st.date_input("To", value=max_date, min_value=d_from, max_value=max_date)
        df = df[(df["Date"] >= pd.to_datetime(d_from)) & (df["Date"] <= pd.to_datetime(d_to))]

    value_col = "Value (mm)" if "Value (mm)" in df.columns else df.columns[1]
