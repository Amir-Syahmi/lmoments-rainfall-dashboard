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

    time_scale = st.radio("Select Time Scale", ["annual", "daily"])
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

    if time_scale == "Annual":
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

# ---------- MAIN ----------
col_map, col_mid, col_right = st.columns([3.1, 4.1, 2.8], gap="large")

# ====== CARD 1: Map ======
with col_map:
    st.markdown('<div class="rf-card">', unsafe_allow_html=True)
    st.markdown("### 📍 Station Location")

    station_row = coord_df[coord_df["File"] == station_id]
    all_coords = coord_df.dropna(subset=["Latitude", "Longitude"])

    if not station_row.empty:
        lat = float(station_row["Latitude"].values[0]); lon = float(station_row["Longitude"].values[0])
        zoom = 7.5
        station_name = station_row["Station Name"].values[0]
        st.markdown(f"**{station_name} ({station_id})**")
    else:
        lat = float(all_coords["Latitude"].mean()); lon = float(all_coords["Longitude"].mean())
        zoom = 5.5

    optional = [c for c in ["State", "District", "River", "Basin", "Elevation", "Elevation (m)"] if c in coord_df.columns]
    tt_lines = ["<b>{Station Name}</b> ({File})", "Lat: {Latitude} | Lon: {Longitude}"] + [f"{c}: "+"{"+c+"}" for c in optional]
    tooltip_html = "<br/>".join(tt_lines)

    layers = [pdk.Layer("ScatterplotLayer", data=all_coords,
                        get_position='[Longitude, Latitude]',
                        get_fill_color='[0, 102, 255, 160]', get_radius=1000, pickable=True)]
    if not station_row.empty:
        layers.append(pdk.Layer("ScatterplotLayer", data=station_row,
                        get_position='[Longitude, Latitude]',
                        get_fill_color='[255, 65, 54, 220]', get_radius=1500, pickable=True))

    deck = pdk.Deck(
        map_style="mapbox://styles/mapbox/light-v9",
        initial_view_state=pdk.ViewState(latitude=lat, longitude=lon, zoom=zoom, pitch=0),
        layers=layers,
        tooltip={"html": tooltip_html, "style": {"backgroundColor": "#111827", "color": "white", "fontSize": "12px"}},
        height=380  # remove if your pydeck version doesn't support height on Deck
    )
    st.pydeck_chart(deck, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ====== CARD 2: L-moments + ranking + Q–Q plot ======
with col_mid:
    st.markdown('<div class="rf-card">', unsafe_allow_html=True)
    st.markdown("### 📊 L-Moments & Fit Quality")

    values = df[value_col].dropna().values
    if len(values) < 5:
        st.info("Not enough data points for analysis.")
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        lmr = lm.lmom_ratios(values, nmom=4)
        st.markdown(
            f"**L1 (Mean):** {lmr[0]:.4f} &nbsp;&nbsp; "
            f"**L2 (L-Scale):** {lmr[1]:.4f} &nbsp;&nbsp; "
            f"**T3 (L-Skew):** {lmr[2]:.4f} &nbsp;&nbsp; "
            f"**T4 (L-Kurt):** {lmr[3]:.4f}",
            unsafe_allow_html=True
        )

        st.markdown("#### 🏅 Top 5 Distributions by MADI/MSDI")
        metric_choice = st.radio("Performance metric", ["MADI", "MSDI"], horizontal=True)

        n = len(values); sorted_data = np.sort(values)
        P_i = np.array([(i - 0.44) / (n + 0.12) for i in range(1, n + 1)])
        g_i = -np.log(-np.log(P_i))
        epsilon = 1

        distributions = ['gum', 'nor', 'exp', 'gev', 'glo', 'gno', 'gpa', 'pe3', 'kap']
        dist_names = {'gum': 'GUM', 'nor': 'NOR', 'exp': 'EXP', 'gev': 'GEV',
                      'glo': 'GLO', 'gno': 'GNO', 'gpa': 'GPA', 'pe3': 'PE3', 'kap': 'K4D'}
        pretty2code = {v: k for k, v in dist_names.items()}

        madi, msdi, params_map, quant_map = {}, {}, {}, {}
        for code in distributions:
            try:
                f = getattr(distr, code)
                params = f.lmom_fit(values)
                q = f.ppf(P_i, **params)
                norm_diff = (sorted_data - q) / ((sorted_data + epsilon) if time_scale == "Daily" else sorted_data)
                madi[code] = float(np.mean(np.abs(norm_diff)))
                msdi[code] = float(np.mean(norm_diff ** 2))
                params_map[code] = params
                quant_map[code] = q
            except Exception:
                continue

        metric_map = {"MADI": madi, "MSDI": msdi}; other_map = {"MADI": msdi, "MSDI": madi}
        scores = metric_map[metric_choice]; order = sorted(scores.items(), key=lambda x: x[1])

        for i, (code, sc) in enumerate(order[:5], 1):
            name = dist_names.get(code, code.upper())
            st.markdown(
                f"{i}. **{name}** — {metric_choice}: "
                f"<span style='color:#059669; font-weight:600;'>{sc:.4f}</span> "
                f"<span class='soft'>(other: {other_map[metric_choice][code]:.4f})</span>",
                unsafe_allow_html=True
            )

        with st.expander("Advanced / Manual override", expanded=False):
            use_manual = st.checkbox("Manually choose distribution", value=False)
            manual_pretty = st.selectbox("Distribution", [dist_names[d] for d in distributions], disabled=not use_manual)

        auto_code = order[0][0]
        if use_manual:
            chosen = pretty2code[manual_pretty]
            if chosen not in params_map:
                st.error(f"{manual_pretty} could not be fitted on this data.")
                st.markdown('</div>', unsafe_allow_html=True); st.stop()
            best_code = chosen; source = "Manual"
        else:
            best_code = auto_code; source = f"Auto: {metric_choice}"

        best_name = dist_names[best_code]; best_params = params_map[best_code]; best_quant = quant_map[best_code]
        st.session_state["bestfit"] = dict(code=best_code, name=best_name, params=best_params, metric=metric_choice, source=source)

        st.markdown(
            f"**Best Fit:** {best_name} &nbsp;&nbsp; "
            f"<span class='soft'>({source})</span><br>"
            f"**Parameters:** { {k: round(float(v), 4) for k, v in best_params.items()} }<br>"
            f"**MADI:** {madi[best_code]:.4f} &nbsp;&nbsp; **MSDI:** {msdi[best_code]:.4f}",
            unsafe_allow_html=True
        )

        # Q–Q Plot (Plotly) — legend far below, extra space for x-axis title
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=g_i, y=best_quant, mode="lines", name=f"{best_name} Quantiles"))
        fig.add_trace(go.Scatter(x=g_i, y=sorted_data, mode="lines", name="Actual Data", line=dict(dash="dash")))
        fig.update_layout(
            template="simple_white",
            margin=dict(l=10, r=10, t=72, b=120),  # more bottom space
            height=380,
            title=dict(text=f"{best_name} Fit ({source})", y=0.98, x=0.02, xanchor="left"),
            xaxis_title="Gringorten Position (g_i)",
            yaxis_title="Rainfall (mm)",
            xaxis_title_standoff=24,  # push x-axis title away from legend
            legend=dict(orientation="h", yanchor="top", y=-0.35, xanchor="left", x=0.0),
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

# ====== CARD 3: Return Period ======
with col_right:
    st.markdown('<div class="rf-card">', unsafe_allow_html=True)
    st.markdown("### 📈 Return Period Analysis")

    bf = st.session_state.get("bestfit")
    if not bf:
        st.info("Run the analysis first (middle card).")
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        best_code = bf["code"]; best_name = bf["name"]; best_params = bf["params"]; src = bf["source"]

        rp = np.array([30, 50, 100, 200, 500, 1000]) if time_scale == "Daily" else np.array([2, 5, 10, 20, 50, 100])
        exc = 1 - (1 / rp)

        f = getattr(distr, best_code)(**best_params)
        rv = f.ppf(exc)

        default_val = float(np.nanmax(df[value_col])) if np.isfinite(df[value_col].max()) else 100.0
        specific_val = st.number_input("Check Probability of Exceedance For (mm):", value=default_val)
        prob_exc = 1 - f.cdf(specific_val)
        est_rp = 1 / prob_exc if prob_exc > 0 else float("inf")

        st.markdown(f"**Best-fit:** {best_name} <span class='soft'>({src})</span>", unsafe_allow_html=True)

        rp_df = pd.DataFrame({
            f"Return Period ({'days' if time_scale=='Daily' else 'years'})": rp,
            "Return Value (mm)": np.round(rv, 2),
            "Exceedance Probability": np.round(exc, 3),
        })
        st.dataframe(rp_df, use_container_width=True)

        st.markdown(
            f"**Exceedance Probability for {specific_val:.1f} mm**: `{prob_exc:.3f}`  \n"
            f"**Estimated Return Period**: `{est_rp:.2f} {'days' if time_scale=='Daily' else 'years'}`"
        )

        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=rp, y=rv, mode="lines+markers", name="Return Values"))
        fig2.update_layout(
            template="simple_white",
            margin=dict(l=10, r=10, t=62, b=90),
            height=360,
            title=dict(text=f"Return Period vs Value ({best_name})", y=0.98, x=0.02, xanchor="left"),
            xaxis_title=f"Return Period ({'days' if time_scale=='Daily' else 'years'})",
            yaxis_title="Rainfall (mm)",
            xaxis_title_standoff=22,
            showlegend=False,
        )
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

