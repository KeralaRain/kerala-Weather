import io
import streamlit as st
import pandas as pd
import pydeck as pdk
from sqlalchemy import text
from engine import engine, DB_BACKEND, NORMALS, to_scale, init_database, predict_and_cache_year, get_historical_backtest, get_njattuvela_forecast, get_extreme_year_profile, get_temperature_forecast, get_daily_astro_weather, get_vishu_ingress, get_month_daily_split

st.set_page_config(page_title="Monsoon Prediction For Kerala :- Astro-Meteorological Forecasting System", page_icon="🌧️", layout="wide")
st.markdown("<style>div[data-baseweb='tab-list'] { flex-wrap: wrap; row-gap: 6px; }</style>", unsafe_allow_html=True)

@st.cache_resource
def _boot():
    init_database()
    return True

_boot()

def classify_regime(ann_mm, peak_month_mm=0.0):
    if ann_mm >= 3650.0 or peak_month_mm >= 900.0:
        return "🔴 SEVERE FLOOD / MEGA-DELUGE RISK"
    elif ann_mm >= 3275.0:
        return "🟠 EXCESS RAINFALL / HIGH DAM INFLOW"
    elif ann_mm <= 2280.0:
        return "🟤 SEVERE DROUGHT / MONSOON FAILURE"
    elif ann_mm <= 2575.0:
        return "🟡 MODERATE RAINFALL DEFICIT"
    return "🟢 NORMAL MONSOON REGIME"

st.title("🌧️ Monsoon Prediction For Kerala :- Astro-Meteorological Forecasting System")
st.caption("V6.1 Calibrated Astro-ML Edition | 25-Feature Sidereal Ensemble | 126-Year IMD Master History (1901–2026) | 1 mm = 1 L/m²")

with st.sidebar:
    st.header("Forecast Controls")
    sel_year = st.number_input("Select Target Year (1901–2100)", min_value=1901, max_value=2100, value=2027, step=1)
    if st.button("Compute & Cache Selected Year"):
        with st.spinner(f"Running V6 Ephemeris Ensemble for {sel_year}..."):
            predict_and_cache_year(int(sel_year))
        st.success(f"Year {sel_year} computed and stored!")

    st.divider()
    db_label = "PostgreSQL Server (Connected)" if DB_BACKEND == "postgresql" else "Standalone Local DB (Zero-Config)"
    st.info(f"**Database Engine:** {db_label}")
    st.markdown("**Pre-Cached Years in DB:** 2026–2030 + 1901–2026 IMD Actuals")
    st.divider()
    st.subheader("Ocean Teleconnections (ENSO & IOD)")
    enso_state = st.selectbox("ENSO (Pacific SST):", ("Neutral (0.0)", "La Niña (+12% Monsoon)", "El Niño (-14% Monsoon)"))
    iod_state = st.selectbox("Indian Ocean Dipole (IOD):", ("Neutral IOD", "Positive IOD (+10% Rain)", "Negative IOD (-8% Rain)"))
    ocean_mult = 1.0 + (0.12 if "La Niña" in enso_state else (-0.14 if "El Niño" in enso_state else 0.0)) + (0.10 if "Positive" in iod_state else (-0.08 if "Negative" in iod_state else 0.0))

predict_and_cache_year(int(sel_year))

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
    "1. General Kerala Annual",
    "2. 12-Month Kerala Forecast",
    "3. 9-Grid Kurma × 12 Months",
    "4. Dam Catchment Areas",
    "5. 126-Yr IMD Master DB",
    "6. 27 Njattuvela Almanac",
    "7. Extreme Flood & Drought Risk",
    "8. Temperature & Heatwave",
    "9. Hybrid Astro-Meteo & Live NWP"
])

with tab1:
    st.subheader(f"General Kerala Annual Outlook — {sel_year}")
    df_s = pd.read_sql(text("SELECT month, score_1_to_10, predicted_mm FROM rainfall_predictions WHERE sector_id = 0 AND year = :y"), engine, params={"y": int(sel_year)})
    peak_m = float(df_s["predicted_mm"].max())
    ann_total_val = float(df_s["predicted_mm"].sum())
    reg_label = classify_regime(ann_total_val, peak_m)
    if "SEVERE FLOOD" in reg_label:
        st.error(f"**{sel_year} Astro-Meteorological Regime:** {reg_label} — Annual Total: **{ann_total_val:,.1f} mm** | Peak Month: **{peak_m:,.1f} mm**")
    elif "SEVERE DROUGHT" in reg_label:
        st.warning(f"**{sel_year} Astro-Meteorological Regime:** {reg_label} — Annual Total: **{ann_total_val:,.1f} mm** (Severe Deficit)")
    elif "EXCESS" in reg_label or "DEFICIT" in reg_label:
        st.info(f"**{sel_year} Astro-Meteorological Regime:** {reg_label} — Annual Total: **{ann_total_val:,.1f} mm**")
    else:
        st.success(f"**{sel_year} Astro-Meteorological Regime:** {reg_label} — Annual Total: **{ann_total_val:,.1f} mm**")

    def s_calc(ms):
        sub = df_s[df_s["month"].isin(ms)]
        p, n = float(sub["predicted_mm"].sum()), sum(NORMALS.get(m) for m in ms)
        return p, round(((p - n) / n) * 100.0, 1), round(float(sub["score_1_to_10"].mean()), 1)
    sw_p, sw_d, sw_s = s_calc((6, 7, 8, 9))
    ne_p, ne_d, ne_s = s_calc((10, 11, 12))
    pr_p, pr_d, pr_s = s_calc((3, 4, 5))
    c_s1, c_s2, c_s3 = st.columns(3)
    c_s1.metric("Edavappathi (SW: Jun-Sep)", f"{sw_p:,.1f} mm", f"{sw_d:+.1f}% (Scale {sw_s}/10)")
    c_s2.metric("Thulavarsham (NE: Oct-Dec)", f"{ne_p:,.1f} mm", f"{ne_d:+.1f}% (Scale {ne_s}/10)")
    c_s3.metric("Summer Showers (Mar-May)", f"{pr_p:,.1f} mm", f"{pr_d:+.1f}% (Scale {pr_s}/10)")
    if abs(ocean_mult - 1.0) > 0.001:
        adj_ann = ann_total_val * ocean_mult
        st.info(f"**Ocean-Adjusted Annual Outlook ({enso_state} + {iod_state}):** **{adj_ann:,.1f} mm** (vs. Pure Astro: {ann_total_val:,.1f} mm | Multiplier: `{ocean_mult:.2f}x`)")
    st.divider()

    df_ann = pd.read_sql(text("SELECT year, ROUND(AVG(score_1_to_10), 2) AS avg_score_1_10, SUM(predicted_mm) AS annual_mm, SUM(predicted_l_per_m2) AS annual_l_m2, ROUND(AVG(departure_pct), 1) AS avg_departure_pct FROM rainfall_predictions WHERE sector_id = 0 AND year BETWEEN 2026 AND 2030 GROUP BY year ORDER BY year"), engine)
    st.markdown("#### Pre-Cached 5-Year Annual Outlook (2026–2030)")
    st.dataframe(df_ann, use_container_width=True)
    st.bar_chart(df_ann.set_index("year")["annual_mm"], use_container_width=True)

with tab2:
    st.subheader(f"12-Month Statewide Kerala Forecast — {sel_year}")
    df_m = pd.read_sql(text("SELECT month, score_1_to_10, predicted_mm, predicted_l_per_m2, departure_pct, astro_notes FROM rainfall_predictions WHERE sector_id = 0 AND year = :y ORDER BY month"), engine, params={"y": int(sel_year)})
    st.dataframe(df_m, use_container_width=True)
    c_left, c_right = st.columns(2)
    with c_left:
        st.markdown("##### Monthly Predicted Rainfall (mm / L per m²)")
        st.bar_chart(df_m.set_index("month")["predicted_mm"], use_container_width=True)
    with c_right:
        st.markdown("##### Monthly Astro-Intensity Curve (1–10 Scale)")
        st.line_chart(df_m.set_index("month")["score_1_to_10"], use_container_width=True)
    st.download_button(f"Download {sel_year} 12-Month CSV", df_m.to_csv(index=False), f"kerala_12m_{sel_year}.csv")

with tab3:
    st.subheader(f"9-Grid Kurma Chakra × 12 Months — {sel_year}")
    unit_choice = st.radio("Display Metric:", ("1–10 Intensity Scale", "Millimeters (mm)", "Liters per m² (L/m²)"), horizontal=True)
    col_map = {"1–10 Intensity Scale": "score_1_to_10", "Millimeters (mm)": "predicted_mm", "Liters per m² (L/m²)": "predicted_l_per_m2"}
    df_9 = pd.read_sql(text("SELECT k.sector_name, p.month, p.score_1_to_10, p.predicted_mm, p.predicted_l_per_m2 FROM rainfall_predictions p JOIN kurma_sectors_dams k ON p.sector_id = k.sector_id WHERE p.year = :y ORDER BY k.sector_id, p.month"), engine, params={"y": int(sel_year)})
    piv = df_9.pivot(index="sector_name", columns="month", values=col_map.get(unit_choice))
    st.dataframe(piv, use_container_width=True)

with tab4:
    st.subheader(f"Kerala Dam Catchments & River Basins — {sel_year}")
    df_dams = pd.read_sql(text("SELECT k.sector_name, k.nakshatras, k.river_basins, k.major_dams, ROUND(AVG(p.score_1_to_10), 2) AS annual_score, SUM(p.predicted_mm) AS annual_catchment_mm, SUM(p.predicted_l_per_m2) AS annual_l_per_m2 FROM kurma_sectors_dams k JOIN rainfall_predictions p ON k.sector_id = p.sector_id WHERE p.year = :y GROUP BY k.sector_id, k.sector_name, k.nakshatras, k.river_basins, k.major_dams ORDER BY k.sector_id"), engine, params={"y": int(sel_year)})
    st.dataframe(df_dams, use_container_width=True)
    st.markdown("##### Annual Catchment Volume by Sector (mm / L per m²)")
    st.bar_chart(df_dams.set_index("sector_name")["annual_catchment_mm"], use_container_width=True)
    st.markdown("##### Interactive Kerala Kurma Sectors & Major Dams Map")
    coords = {1:(10.53,76.21), 2:(9.85,76.98), 3:(10.83,76.68), 4:(9.34,77.15), 5:(8.53,77.15), 6:(9.62,76.38), 7:(11.12,76.12), 8:(11.98,75.56), 9:(11.65,75.96)}
    df_map = df_dams.copy()
    df_map["lat"] = tuple(coords.get(i).__getitem__(0) for i in range(1, 10))
    df_map["lon"] = tuple(coords.get(i).__getitem__(1) for i in range(1, 10))
    df_map["color"] = tuple(list((0, 119, 182, 210)) if s >= 6.5 else (list((16, 185, 129, 200)) if s >= 5.0 else list((245, 158, 11, 210))) for s in df_map["annual_score"])
    df_map["radius"] = (df_map["annual_catchment_mm"] / df_map["annual_catchment_mm"].max()) * 16000 + 8000
    st.pydeck_chart(pdk.Deck(
        map_style=None,
        initial_view_state=pdk.ViewState(latitude=10.35, longitude=76.45, zoom=6.5),
        layers=list((pdk.Layer("ScatterplotLayer", data=df_map, get_position="[lon, lat]", get_color="color", get_radius="radius", pickable=True),)),
        tooltip={"html": "<b>{sector_name}</b><br/>Dams: {major_dams}<br/>Annual: <b>{annual_catchment_mm} mm</b><br/>Score: {annual_score}/10"}
    ))

with tab5:
    st.subheader("Stored 126-Year Authentic IMD Master History (1901–2026) — Zero Re-Download Needed")
    yr_filter = st.slider("Filter Historical Years", 1901, 2026, (2015, 2026))
    df_hist = pd.read_sql(text("SELECT * FROM imd_master_history WHERE year BETWEEN :y1 AND :y2 ORDER BY year DESC, month ASC"), engine, params={"y1": yr_filter.__getitem__(0), "y2": yr_filter.__getitem__(1)})
    st.dataframe(df_hist, use_container_width=True)
    st.divider()
    st.subheader("V6.3 Engine 50-Year Historical Backtest (1975–2026)")
    if st.button("Run 50-Year IMD Accuracy Validation"):
        with st.spinner("Computing 52 years of Sidereal Ephemeris + Ardra Pravesha charts..."):
            st.session_state["df_bt"] = get_historical_backtest(1975, 2026)
    if "df_bt" in st.session_state:
        df_bt = st.session_state["df_bt"]
        oos_avg = round(float(df_bt["Blind_OOS_Acc_pct"].mean()), 1)
        in_avg = round(float(df_bt["InSample_Fit_pct"].mean()), 1)
        sw_acc = round(float(df_bt["SW_Acc_pct"].mean()), 1)
        ne_acc = round(float(df_bt["Thulavarsham_Acc_pct"].mean()), 1)
        pre_acc = round(float(df_bt["Summer_Acc_pct"].mean()), 1)
        win_acc = round(float(df_bt["Winter_Acc_pct"].mean()), 1)
        c_top1, c_top2 = st.columns(2)
        c_top1.metric("Blind Out-of-Sample Accuracy (True Unseen Forecast)", f"{oos_avg}%", "10-Fold Year-Grouped Cross-Validation")
        c_top2.metric("In-Sample Calibration Fit (Historical Memory)", f"{in_avg}%", "Full 1901–2026 Training Fit")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Edavappathi SW (Blind)", f"{sw_acc}%")
        m2.metric("Thulavarsham NE (Blind)", f"{ne_acc}%")
        m3.metric("Summer Mar–May (Blind)", f"{pre_acc}%")
        m4.metric("Winter Jan–Feb (Blind)", f"{win_acc}%")
        df_bt["IMD_Regime"] = df_bt["IMD_Actual_mm"].apply(classify_regime)
        df_bt["Astro_Regime"] = df_bt["V6_Blind_OOS_mm"].apply(classify_regime)
        st.markdown("##### Annual Rainfall Validation: IMD Actual (Navy) vs. Blind Out-of-Sample Astro Forecast (Red)")
        st.line_chart(df_bt.set_index("Year")[["IMD_Actual_mm", "V6_Blind_OOS_mm"]], color=["#003366", "#FF4B4B"], use_container_width=True)
        st.markdown("##### Thulavarsham (Oct–Dec NE Monsoon) Validation (IMD Navy vs Astro Red)")
        st.line_chart(df_bt.set_index("Year")[["Thulavarsham_Actual_mm", "Thulavarsham_Pred_mm"]], color=["#003366", "#FF4B4B"], use_container_width=True)
        only_ext = st.checkbox("Show Extreme Years Only (🔴 Severe Floods & 🟤 Severe Droughts)", value=False)
        df_show = df_bt[df_bt["IMD_Regime"].str.contains("SEVERE") | df_bt["Astro_Regime"].str.contains("SEVERE")] if only_ext else df_bt
        st.dataframe(df_show.sort_values("Year", ascending=False), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Historical Astro-Meteorological Case Study (e.g., 2018 Mega-Floods)")
    case_yr = st.selectbox("Select Historic Kerala Year to Inspect Month-by-Month:", (2018, 2016, 2021, 2024, 1992, 2007))
    predict_and_cache_year(int(case_yr))
    df_case = pd.read_sql(text("SELECT h.month, h.imd_normal_mm, h.imd_actual_mm, p.score_1_to_10 AS astro_score, p.predicted_mm AS astro_pred_mm, p.astro_notes FROM imd_master_history h JOIN rainfall_predictions p ON h.year = p.year AND h.month = p.month WHERE h.year = :y AND p.sector_id = 0 ORDER BY h.month"), engine, params={"y": int(case_yr)})
    st.dataframe(df_case, use_container_width=True, hide_index=True)
    st.line_chart(df_case.set_index("month")[["imd_actual_mm", "astro_pred_mm"]], color=["#003366", "#FF4B4B"], use_container_width=True)


with tab6:
    st.subheader(f"27 Njattuvela (ഞാറ്റുവേല) Solar Nakshatra Forecast — {sel_year}")
    st.caption("13.5-Day Sidereal Solar Transits | Tracks exact Ingress Moon Nakshatra, Water-Nakshatra density & Node storm bursts")
    df_nj = get_njattuvela_forecast(int(sel_year))
    n1, n2, n3 = st.columns(3)
    wettest = df_nj.loc[df_nj["Predicted_mm"].idxmax()]
    n1.metric("Peak Rainfall Njattuvela", wettest["Njattuvela"].split(" ")[0], f"{wettest['Predicted_mm']} mm ({wettest['Start_Date']})")
    n2.metric("Deluge / Excess Njattuvelas", int(df_nj["Status"].str.contains("Heavy|Active").sum()), "Out of 27 Solar Transits")
    n3.metric("Dry / Break Njattuvelas", int(df_nj["Status"].str.contains("Dry").sum()), "Monsoon Break Windows")
    st.dataframe(df_nj, use_container_width=True, hide_index=True)
    st.markdown("##### Rainfall Distribution Across All 27 Njattuvelas (mm / L per m²)")
    st.bar_chart(df_nj.set_index("Njattuvela")["Predicted_mm"], use_container_width=True)
    st.download_button(f"Download {sel_year} 27-Njattuvela CSV", df_nj.to_csv(index=False), f"kerala_njattuvela_{sel_year}.csv")


with tab7:
    st.subheader(f"Extreme Flood & Severe Drought Tail-Risk Analysis — {sel_year}")
    st.caption("Quantile Tail-Routed Ensemble (14th-Percentile Drought Floor vs. 88th-Percentile Deluge Ceiling) + Synodic Outer-Planet Cycles")
    df_ext, a_nak, a_ben, s_nak = get_extreme_year_profile(int(sel_year))
    tot_dr = float(df_ext["Drought_Tail_14pct_mm"].sum())
    tot_ex = float(df_ext["Expected_Forecast_mm"].sum())
    tot_fl = float(df_ext["Flood_Tail_88pct_mm"].sum())
    peak_fl = float(df_ext["Flood_Tail_88pct_mm"].max())

    dep_pct = ((tot_ex - 2924.7) / 2924.7) * 100.0
    storm_ms = df_ext[df_ext["Node_Storm_Score"] >= 10]["Month"].tolist()
    canc_ms = df_ext[df_ext["Cancer_Stellium_Days"] >= 6]["Month"].tolist()
    burst_ms = sorted(list(set(storm_ms + canc_ms)))

    if tot_ex >= 3650.0 or float(df_ext["Expected_Forecast_mm"].max()) >= 900.0:
        verdict_title = f"🔴 HIGH / EXTREME FLOOD ALERT FOR {sel_year}"
        verdict_msg = f"Astrological signs indicate **severe statewide flood risk** in {sel_year} (**{tot_ex:,.0f} mm**, **{dep_pct:+.1f}%** above normal). Major deluge triggers are active in **Month(s) {', '.join(str(m) for m in burst_ms) if burst_ms else '6–9'}**."
        st.error(f"**{verdict_title}** — {verdict_msg}")
    elif tot_ex <= 2280.0:
        verdict_title = f"🟤 SEVERE DROUGHT ALERT FOR {sel_year}"
        verdict_msg = f"Astrological signs indicate **severe monsoon failure / drought risk** in {sel_year} (**{tot_ex:,.0f} mm**, **{dep_pct:+.1f}%** below normal). Dry-season combustion and arid ingress indicators dominate."
        st.warning(f"**{verdict_title}** — {verdict_msg}")
    elif burst_ms:
        verdict_title = f"🟠 NORMAL ANNUAL TOTAL WITH LOCALIZED HEAVY RAIN BURSTS IN {sel_year}"
        verdict_msg = f"Overall, **{sel_year} is NOT a statewide mega-flood year** (Expected total: **{tot_ex:,.0f} mm**, **{dep_pct:+.1f}%** vs. IMD normal). **However**, astrological storm & Cancer stellium triggers warn of **short-duration heavy rain / high dam-inflow bursts in Month(s) {', '.join(str(m) for m in burst_ms)}** (Flood ceiling up to **{tot_fl:,.0f} mm** if cyclonic triggers intensify)."
        st.info(f"**{verdict_title}** — {verdict_msg}")
    else:
        verdict_title = f"🟢 STEADY / NORMAL MONSOON OUTLOOK FOR {sel_year}"
        verdict_msg = f"Astrological indicators point to a **balanced, normal monsoon year** in {sel_year} (**{tot_ex:,.0f} mm**, **{dep_pct:+.1f}%** vs. normal) with **no major statewide flood or drought triggers**."
        st.success(f"**{verdict_title}** — {verdict_msg}")

    e1, e2, e3, e4 = st.columns(4)
    e1.metric("Drought Tail Scenario (14%)", f"{tot_dr:,.0f} mm", f"{((tot_dr-2924.7)/2924.7)*100:+.1f}% vs Normal")
    e2.metric("Expected Forecast (Central)", f"{tot_ex:,.0f} mm", f"{dep_pct:+.1f}% vs Normal")
    e3.metric("Flood Tail Ceiling (88%)", f"{tot_fl:,.0f} mm", f"Peak Month: {peak_fl:,.0f} mm")
    e4.metric("Ingress Anchors", f"Ardra: {a_nak}", f"Swati: {s_nak}")

    with st.expander(f"📜 Detailed Jyotisha & Sidereal Ephemeris Analysis for {sel_year}", expanded=True):
        storm_months = df_ext[df_ext["Node_Storm_Score"] >= 10]["Month"].tolist()
        canc_months = df_ext[df_ext["Cancer_Stellium_Days"] >= 6]["Month"].tolist()
        peak_row = df_ext.loc[df_ext["Expected_Forecast_mm"].idxmax()]
        a_col1, a_col2 = st.columns(2)
        with a_col1:
            st.markdown(f"**1. Solar Ingress Anchors ({sel_year})**")
            st.markdown(f"- **Ardra Pravesha (SW Monsoon Onset, Jun 21–22):** Moon in **{a_nak}** {'with **Jupiter/Venus benefic aspect** (amplifies Arabian Sea moisture)' if a_ben else '(no direct Jupiter/Venus ingress aspect)'}.")
            st.markdown(f"- **Swati Pravesha (Thulavarsham NE, Oct 24):** Moon in **{s_nak}** (governs Bay of Bengal cyclonic & convective activity).")
            st.markdown(f"- **Peak Deluge Window:** Month **{int(peak_row['Month'])}** (`{peak_row['Expected_Forecast_mm']} mm` expected / `{peak_row['Flood_Tail_88pct_mm']} mm` flood ceiling) — `{peak_row['Astro_Triggers']}`.")
        with a_col2:
            st.markdown("**2. Active Flood & Drought Planetary Triggers**")
            st.markdown(f"- **Rahu/Ketu Water-Sign Storm Pulses:** {'Months ' + ', '.join(str(m) for m in storm_months) + ' (elevated cyclonic/cloudburst potential)' if storm_months else 'None above threshold (low nodal storm risk)'}.")
            st.markdown(f"- **Karka (Cancer) Water Stelliums:** {'Months ' + ', '.join(str(m) for m in canc_months) + ' (heavy Western Ghats / Idukki & Wayanad inflow)' if canc_months else 'No multi-planet Cancer stellium'}.")
            st.markdown(f"- **Synodic Outer-Planet Cycle:** Incorporates Jupiter–Saturn 20-yr *Yuga* phase, 18.6-yr Lunar Nodal cycle, and *Stambhana* stationary motion.")

    st.markdown("##### 12-Month Extreme Envelope: Drought Floor (Amber) vs. Expected (Navy) vs. Flood Ceiling (Red)")
    st.line_chart(
        df_ext.set_index("Month")[["Drought_Tail_14pct_mm", "Expected_Forecast_mm", "Flood_Tail_88pct_mm"]],
        color=["#F59E0B", "#003366", "#FF4B4B"],
        use_container_width=True
    )
    st.dataframe(df_ext, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("10-Year Extreme Regime Scanner (2026–2035)")
    if st.button("Scan 2026–2035 for Severe Flood & Drought Years"):
        scan_rows = []
        with st.spinner("Scanning planetary synodic & nodal cycles for 2026–2035..."):
            for sy in range(2026, 2036):
                df_y, an, _, sn = get_extreme_year_profile(sy)
                ex_s = float(df_y["Expected_Forecast_mm"].sum())
                fl_s = float(df_y["Flood_Tail_88pct_mm"].sum())
                pk_m = float(df_y["Expected_Forecast_mm"].max())
                scan_rows.append({
                    "Year": sy,
                    "Ardra_Moon": an,
                    "Swati_Moon": sn,
                    "Expected_Annual_mm": round(ex_s, 1),
                    "Flood_Ceiling_mm": round(fl_s, 1),
                    "Peak_Month_mm": round(pk_m, 1),
                    "Regime_Classification": classify_regime(ex_s, pk_m)
                })
        st.dataframe(pd.DataFrame(scan_rows), use_container_width=True, hide_index=True)


@st.cache_data
def _cached_temp(yr, sec):
    return get_temperature_forecast(yr, sec)

@st.cache_data
def _cached_daily_temp(dt, sec):
    return get_daily_astro_weather(dt, sec)

with tab8:
    st.subheader(f"Kerala Temperature & Heatwave Astro-Forecast — {sel_year}")
    st.caption("Agni-Tattva Fire Stelliums, Sun–Mars Yoga, Dahana Nakshatras & Cloud-Cover Cooling | Sector-Calibrated")
    sec_options = {
        0: "Statewide Kerala Average",
        1: "1. Center (Thrissur / Chalakudy)",
        2: "2. East High Ranges (Idukki / Munnar)",
        3: "3. Southeast (Palakkad Gap)",
        4: "4. South (Pathanamthitta / Kollam)",
        5: "5. Southwest (Thiruvananthapuram)",
        6: "6. West (Kottayam / Alappuzha)",
        7: "7. Northwest (Malappuram / Kozhikode)",
        8: "8. North (Kannur / Kasaragod)",
        9: "9. Northeast High Ranges (Wayanad)"
    }
    sel_sec = st.selectbox("Select Kerala Region / Kurma Sector:", list(sec_options.keys()), format_func=lambda k: sec_options.get(k))
    df_temp = _cached_temp(int(sel_year), int(sel_sec))

    t1, t2, t3 = st.columns(3)
    hottest = df_temp.loc[df_temp["Max_Temp_C"].idxmax()]
    coolest = df_temp.loc[df_temp["Min_Temp_C"].idxmin()]
    t1.metric("Peak Daytime Max Temp", f"{hottest['Max_Temp_C']} °C", f"Month {int(hottest['Month'])} ({hottest['Thermal_Outlook']})")
    t2.metric("Coolest Night Min Temp", f"{coolest['Min_Temp_C']} °C", f"Month {int(coolest['Month'])}")
    t3.metric("Heatwave / Hot Months", int(df_temp["Thermal_Outlook"].str.contains("Heat").sum()), "Months Above Thermal Threshold")

    st.markdown("##### 12-Month Maximum (°C, Red) vs. Minimum (°C, Blue) Temperature Curve")
    st.line_chart(df_temp.set_index("Month")[["Max_Temp_C", "Min_Temp_C"]], color=["#FF4B4B", "#0077B6"], use_container_width=True)
    st.dataframe(df_temp, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader(f"Intraseasonal Day-by-Day Rain Surges vs. Hot Breaks ({sel_year})")
    st.caption("Tracks how a single month (e.g., August) alternates between 💧 Rain-Cooled Surges and ☀️ Dry Hot Breaks via Chandra Gochara")
    split_m = st.selectbox("Select Month to View Daily Rain vs. Heat Alternation:", list(range(1, 13)), index=7, format_func=lambda m: f"Month {m:02d}")
    df_split = get_month_daily_split(int(sel_year), int(split_m), int(sel_sec))
    s1, s2, s3 = st.columns(3)
    s1.metric("Rain-Cooled Surge Days", int(df_split["Intramonth_Phase"].str.contains("Rain Surge").sum()), "Cooler / Wet Spells")
    s2.metric("Hot Dry Break Days", int(df_split["Intramonth_Phase"].str.contains("Hot").sum()), "Clear-Sky Heat Spells")
    s3.metric("Peak Daily Temp in Month", f"{df_split['Day_Max_C'].max()} °C", f"Coolest Day Max: {df_split['Day_Max_C'].min()} °C")
    st.line_chart(df_split.set_index("Day")[["Day_Max_C", "Daily_Rain_mm"]], color=["#FF4B4B", "#0077B6"], use_container_width=True)
    st.dataframe(df_split, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Daily Chandra Gochara Temperature & Sky Predictor")
    import datetime
    pick_date = st.date_input("Pick Any Exact Date (1901–2100):", value=datetime.date(2026, 11, 21) if int(sel_year) == 2026 else datetime.date(int(sel_year), 8, 15), min_value=datetime.date(1901, 1, 1), max_value=datetime.date(2100, 12, 31))
    d_info = get_daily_astro_weather(pick_date, int(sel_sec))
    d1, d2, d3, d4, d5 = st.columns(5)
    d1.metric("Predicted Daily Rain", f"{d_info['rain_mm']} mm", d_info["condition"])
    d2.metric("Day Max / Night Min", f"{d_info['max_c']}° / {d_info['min_c']}°C", d_info["date"])
    d3.metric("Moon Nakshatra", d_info["moon_nakshatra"], "Chandra Gochara")
    d4.metric("Lunar Tithi", d_info["tithi"], "Panchanga Phase")
    d5.metric("Wind Speed", f"{d_info['wind_kmh']} km/h", d_info["wind_status"])
    st.markdown(f"##### 3-Hour Intra-Day Prahara & Lagna Curve for {d_info['date']} (IST)")
    df_intra = get_intraday_prahara_curve, get_month_all_praharas, get_astronomical_metrics, get_analog_years, fetch_live_kerala_nwp, fetch_7month_seasonal_forecast(pick_date, int(sel_sec))
    st.line_chart(df_intra.set_index("Time_IST")[["Temp_C", "Rain_mm"]], color=["#FF4B4B", "#0077B6"], use_container_width=True)
    st.dataframe(df_intra, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Full-Month 3-Hour Prahara Weather Schedule (Present Month or Any Month)")
    st.caption("Complete 8-Prahara (every 3 hours IST) temperature, Rising Lagna & rain schedule across all days of the selected month")
    c_mp1, c_mp2 = st.columns(2)
    mp_year = c_mp1.number_input("Schedule Year:", min_value=1901, max_value=2100, value=2026, step=1)
    mp_month = c_mp2.selectbox("Schedule Month:", list(range(1, 13)), index=10, format_func=lambda m: f"Month {m:02d}")
    df_mp = get_month_all_praharas, get_astronomical_metrics, get_analog_years, fetch_live_kerala_nwp, fetch_7month_seasonal_forecast(int(mp_year), int(mp_month), int(sel_sec))
    df_mp["Slot_Label"] = df_mp["Date"] + " " + df_mp["Time_IST"].str.slice(0, 5)
    st.line_chart(df_mp.set_index("Slot_Label")[["Temp_C", "Rain_mm"]], color=["#FF4B4B", "#0077B6"], use_container_width=True)
    st.markdown("##### Day-by-Day Temperature Grid Across All 8 Times of Day (°C)")
    df_mp["Time_Col"] = df_mp["Time_IST"].str.slice(0, 9)
    piv_temp = df_mp.pivot(index="Date", columns="Time_Col", values="Temp_C")
    st.dataframe(piv_temp, use_container_width=True)
    with st.expander("View Full 240-Slot Detailed Log (Rising Lagna, Temp °C, Rain mm & Sky)", expanded=False):
        st.dataframe(df_mp[["Date", "Time_IST", "Rising_Lagna", "Temp_C", "Rain_mm", "Sky_Condition"]], use_container_width=True, hide_index=True)
    st.download_button(f"Download {mp_year}-{mp_month:02d} 3-Hour Schedule CSV", df_mp.to_csv(index=False), f"kerala_3hr_schedule_{mp_year}_{mp_month:02d}.csv")

    st.divider()
    v_hot, v_nak, v_mars = get_vishu_ingress, get_month_daily_split(int(sel_year))
    st.info(f"**Mesha Sankranti (Vishu, Apr 14) Thermal Anchor ({sel_year}):** Moon in **{v_nak}** | Mars Agni Aspect: **{'Active (Amplifies Summer Heat)' if v_mars else 'Inactive'}** -> Summer Regime: **{'🔴 Elevated Heatwave Risk' if v_hot else '🟢 Moderate Summer'}**")
    if st.button("Scan 2026–2035 for Extreme Heatwave Years & Months"):
        h_rows = []
        with st.spinner("Scanning Agni-Tattva & Vishu ingress cycles for 2026–2035..."):
            for hy in range(2026, 2036):
                df_ty = _cached_temp(hy, int(sel_sec))
                pk_r = df_ty.loc[df_ty["Max_Temp_C"].idxmax()]
                vh, vn, _ = get_vishu_ingress, get_month_daily_split(hy)
                h_rows.append({
                    "Year": hy,
                    "Vishu_Moon": vn,
                    "Peak_Month": int(pk_r["Month"]),
                    "Peak_Max_Temp_C": pk_r["Max_Temp_C"],
                    "Departure_C": pk_r["Departure_C"],
                    "Summer_Status": pk_r["Thermal_Outlook"]
                })
        st.dataframe(pd.DataFrame(h_rows), use_container_width=True, hide_index=True)


with tab9:
    st.subheader("Hybrid Astronomical + Numerical Weather (NWP) + 126-Yr Analog System")
    st.caption("Combines Physical Astronomy (Lunar Perigee Tidal Force & Solar Zenith Declination), Live 14-Day ECMWF/GFS NWP & Historical Analog Years")

    st.markdown("#### 1. Physical Astronomical & Gravitational Indicators (Today / Selected Date)")
    import datetime
    astro_dt = st.date_input("Select Date for Physical Astronomy Check:", value=datetime.date(2026, 11, 21), min_value=datetime.date(1901, 1, 1), max_value=datetime.date(2100, 12, 31))
    am = get_astronomical_metrics(astro_dt.year, astro_dt.month, astro_dt.day)
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Solar Declination", f"{am['solar_declination_deg']}°", f"{am['kerala_zenith_offset_deg']}° from Kerala Overhead (10°N)")
    a2.metric("Lunar Distance", f"{am['lunar_distance_km']:,} km", f"Perigee Tidal Index: {am['lunar_perigee_tide_pct']}%")
    a3.metric("Spring-Perigee Surge", "🌊 ACTIVE" if am["spring_perigee_surge"] else "Normal Tide", "Syzygy + Lunar Perigee Gravity")
    a4.metric("Earth–Sun Distance", f"{am['earth_sun_au']} AU", "Solar Irradiance Factor")

    st.divider()
    st.markdown("#### 2. Live 14-Day Numerical Weather Prediction (NWP) vs. Astro-Engine Blend")
    city_map = {
        "Thiruvananthapuram (8.52°N, 76.94°E)": (8.5241, 76.9366),
        "Kochi / Ernakulam (9.93°N, 76.26°E)": (9.9312, 76.2673),
        "Palakkad Gap (10.78°N, 76.65°E)": (10.7867, 76.6548),
        "Kozhikode (11.25°N, 75.78°E)": (11.2588, 75.7804),
        "Idukki High Ranges (9.85°N, 76.97°E)": (9.8495, 76.9720),
        "Wayanad (11.68°N, 76.13°E)": (11.6854, 76.1320)
    }
    sel_city = st.selectbox("Select Kerala Station for Live 14-Day NWP Model:", list(city_map.keys()))
    lat_c, lon_c = city_map.get(sel_city)
    df_nwp, online_ok = fetch_live_kerala_nwp, fetch_7month_seasonal_forecast(lat_c, lon_c)
    if online_ok and not df_nwp.empty:
        st.success(f"Connected to Live Open-Meteo Global NWP Feed for **{sel_city}** (Next 14 Days)")
        st.line_chart(df_nwp.set_index("Date")[["NWP_Max_C", "NWP_Rain_mm", "NWP_Max_Wind_kmh"]], color=["#FF4B4B", "#0077B6", "#10B981"], use_container_width=True)
        st.dataframe(df_nwp, use_container_width=True, hide_index=True)
    else:
        st.info("Offline Mode Active: Live NWP feed unavailable without internet; using 100% offline Astro-Astronomical Engine.")

    st.divider()
    st.markdown("#### 2B. 7-Month (210-Day) Global Seasonal Climate Ensemble vs. Astro-Engine")
    st.caption("Bridges Days 17–210 using Open-Meteo Global Seasonal Ensemble (ECMWF SEAS5 / CFSv2) compared against your Astro-Forecast")
    df_seas, seas_ok = fetch_7month_seasonal_forecast(lat_c, lon_c)
    if seas_ok and not df_seas.empty:
        astro_vals = []
        for _, sr in df_seas.iterrows():
            sy_i, sm_i = int(sr["Year"]), int(sr["Month"])
            predict_and_cache_year(sy_i)
            val_a = pd.read_sql(text("SELECT predicted_mm FROM rainfall_predictions WHERE sector_id = 0 AND year = :y AND month = :m"), engine, params={"y": sy_i, "m": sm_i})
            a_mm = float(val_a["predicted_mm"].iloc) if not val_a.empty else 0.0
            astro_vals.append(round(a_mm * ocean_mult, 1))
        df_seas["Astro_Ocean_Rain_mm"] = astro_vals
        st.line_chart(df_seas.set_index("YM")[["Seasonal_NWP_Rain_mm", "Astro_Ocean_Rain_mm"]], color=["#0077B6", "#FF4B4B"], use_container_width=True)
        st.dataframe(df_seas[["YM", "Seasonal_NWP_Rain_mm", "Astro_Ocean_Rain_mm", "Seasonal_NWP_Max_C"]], use_container_width=True, hide_index=True)
    else:
        st.info("7-Month Seasonal Ensemble unavailable offline; using 100% offline Astro-Astronomical + ENSO/IOD Engine.")

    st.divider()
    st.markdown(f"#### 3. Top 5 Historical Celestial Analog Years Matching {sel_year} (from 1901–2025 IMD Archive)")
    df_ana = get_analog_years(int(sel_year), top_n=5)
    st.dataframe(df_ana, use_container_width=True, hide_index=True)

with st.sidebar:
    st.divider()
    st.subheader("Export Full Report")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_ann.to_excel(writer, sheet_name="5Yr_Annual_Outlook", index=False)
        df_m.to_excel(writer, sheet_name=f"{sel_year}_12M_Statewide", index=False)
        piv.to_excel(writer, sheet_name=f"{sel_year}_9Sector_Grid")
        df_dams.to_excel(writer, sheet_name=f"{sel_year}Dam_Catchments", index=False)
    st.download_button(
        label=f"📊 Download {sel_year} Full Excel (.xlsx)",
        data=buf.getvalue(),
        file_name=f"Kerala_Monsoon_Forecast{sel_year}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
