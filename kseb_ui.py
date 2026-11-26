import io
import datetime
import streamlit as st
import pandas as pd
from sqlalchemy import text
from kseb_harvester import get_isolated_kseb_engine, init_kseb_tables, run_harvester

def render_kseb_tab():
    st.subheader("⚡ KSEB SLDC Daily Consumption, Generation & Station Analytics")
    st.caption("Clean Named Tables & Printable Reports | Time on X-Axis with Separate Line per Load/Generation Type")
    k_eng, k_pref = get_isolated_kseb_engine()
    init_kseb_tables(k_eng, k_pref)

    c_btn1, c_btn2 = st.columns((1, 3))
    with c_btn1:
        if st.button("🔄 Sync & Parse KSEB Energy Logs"):
            with st.spinner("Syncing & parsing KSEB Energy Logs..."):
                try:
                    run_harvester()
                    st.success("KSEB Energy Logs updated!")
                except Exception as e:
                    st.error(f"Sync note: {e}")
    with c_btn2:
        st.info(f"**Isolated Storage:** `{k_pref.rstrip('.') or 'kseb_sldc_telemetry.db'}` | **48 Half-Hourly Slots/Day + Daily Summary**")

    df_pwr = pd.read_sql(text(f"SELECT * FROM {k_pref}daily_power_summary ORDER BY report_date DESC"), k_eng)
    if df_pwr.empty:
        st.warning("No KSEB Energy Log records stored yet. Click **Sync & Parse KSEB Energy Logs** above.")
        return

    df_pwr["Year_Month"] = df_pwr["report_date"].str.slice(0, 7)
    df_pwr["Year"] = df_pwr["report_date"].str.slice(0, 4)
    avail_days = sorted(df_pwr["report_date"].dropna().unique().tolist(), reverse=True)
    avail_months = sorted(df_pwr["Year_Month"].dropna().unique().tolist(), reverse=True)
    cur_ym = datetime.date.today().strftime("%Y-%m")
    default_m_idx = avail_months.index(cur_ym) if cur_ym in avail_months else 0

    # 1. DAILY 30-MIN CURVE (TIME ON X-AXIS, SEPARATE LINE PER TYPE, LATEST DAY DEFAULT + DAY SELECTOR)
    st.markdown("#### 1. Daily 30-Minute Grid Curve (Time on X-Axis, Separate Line per Type)")
    sel_k_day = st.selectbox("Select Day (Defaults to Latest Available Date):", avail_days, index=0)
    day_row = next(iter(df_pwr[df_pwr["report_date"] == sel_k_day].to_dict("records")))
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Report Date", f"{sel_k_day} ({day_row.get('day_name') or ''})")
    k2.metric("Total Consumption", f"{day_row.get('total_consumption_mu') or 0:.2f} MU")
    k3.metric("KSEB Hydro Gen", f"{day_row.get('hydro_generation_mu') or 0:.2f} MU")
    k4.metric("Evening Peak", f"{day_row.get('evening_peak_mw') or 0:,.0f} MW")
    k5.metric("Morning Peak", f"{day_row.get('morning_peak_mw') or 0:,.0f} MW")

    df_slots = pd.read_sql(text(f"SELECT * FROM {k_pref}slot_30min_energy WHERE report_date = :rd ORDER BY slot_idx"), k_eng, params={"rd": sel_k_day})
    if not df_slots.empty:
        df_chart = df_slots.rename(columns={
            "time_slot": "Time",
            "kerala_consumption_mwh": "Kerala Consumption (MWh)",
            "total_gen_mwh": "Total Generation (MWh)",
            "hydro_total_mwh": "Hydro Generation (MWh)",
            "total_import_mwh": "Total Import (MWh)",
            "solar_mwh": "Solar (MWh)",
            "wind_mwh": "Wind (MWh)"
        }).set_index("Time")
        st.line_chart(df_chart[["Kerala Consumption (MWh)", "Total Generation (MWh)", "Hydro Generation (MWh)", "Total Import (MWh)", "Solar (MWh)", "Wind (MWh)"]], use_container_width=True)

    # 2. MONTHLY CURVE & AVERAGE (PRESENT MONTH DEFAULT + MONTH SELECTOR)
    st.divider()
    st.markdown("#### 2. Monthly Curve & Monthly Average (Present Month Default)")
    sel_k_month = st.selectbox("Select Month (Defaults to Present / Latest Month):", avail_months, index=default_m_idx)
    df_m_sub = df_pwr[df_pwr["Year_Month"] == sel_k_month].sort_values("report_date").rename(columns={
        "report_date": "Time",
        "total_consumption_mu": "Consumption (MU)",
        "hydro_generation_mu": "Hydro Gen (MU)",
        "central_share_import_mu": "Total Import (MU)",
        "solar_mu": "Solar (MU)",
        "wind_mu": "Wind (MU)"
    })
    st.line_chart(df_m_sub.set_index("Time")[["Consumption (MU)", "Hydro Gen (MU)", "Total Import (MU)", "Solar (MU)", "Wind (MU)"]], use_container_width=True)

    df_m_avg = df_pwr.groupby("Year_Month", as_index=False).agg(
        Days=("report_date", "count"),
        Consumption_MU=("total_consumption_mu", "mean"),
        Hydro_Gen_MU=("hydro_generation_mu", "mean"),
        Total_Import_MU=("central_share_import_mu", "mean"),
        Solar_MU=("solar_mu", "mean"),
        Evening_Peak_MW=("evening_peak_mw", "mean")
    ).round(2).sort_values("Year_Month").rename(columns={"Year_Month": "Time"})
    st.markdown("##### Monthly Average Trend Across Logged Months")
    st.line_chart(df_m_avg.set_index("Time")[["Consumption_MU", "Hydro_Gen_MU", "Total_Import_MU", "Solar_MU"]], use_container_width=True)

    # 3. YEARLY AVERAGE CURVE
    st.divider()
    st.markdown("#### 3. Yearly Average Trend")
    df_y_avg = df_pwr.groupby("Year", as_index=False).agg(
        Days=("report_date", "count"),
        Consumption_MU=("total_consumption_mu", "mean"),
        Hydro_Gen_MU=("hydro_generation_mu", "mean"),
        Total_Import_MU=("central_share_import_mu", "mean"),
        Solar_MU=("solar_mu", "mean"),
        Evening_Peak_MW=("evening_peak_mw", "mean")
    ).round(2).sort_values("Year").rename(columns={"Year": "Time"})
    st.line_chart(df_y_avg.set_index("Time")[["Consumption_MU", "Hydro_Gen_MU", "Total_Import_MU", "Solar_MU"]], use_container_width=True)
    st.dataframe(df_y_avg, use_container_width=True, hide_index=True)

    # 4. HYDRO STATIONS RANKED BY CAPACITY + RESERVOIR TABLE
    st.divider()
    st.markdown("#### 4. Hydro Generation by Station (Largest Storage/Capacity → Smallest) & Reservoir Status")
    if not df_slots.empty:
        station_meta = (
            ("Idukki (IDI — 1,460 MCM Reservoir / 780 MW)", "idukki_idi_mwh"),
            ("Sabarigiri / Kakki (SBG — 447 MCM Reservoir / 340 MW)", "sabarigiri_sbg_mwh"),
            ("Kuttiyadi (KDI — 38 MCM Reservoir / 225 MW)", "kuttiyadi_kdi_mwh"),
            ("Lower Periyar (LP — Run-of-River / 180 MW)", "lower_periyar_lp_mwh"),
            ("Neriamangalam (NLM — 77.65 MW)", "neriamangalam_nlm_mwh"),
            ("Sholayar (SLR — 150 MCM Reservoir / 54 MW)", "sholayar_slr_mwh"),
            ("Poringalkuthu (PGL — 32 MCM Reservoir / 52 MW)", "poringalkuthu_pgl_mwh"),
            ("Sengulam (SLM — 51.2 MW)", "sengulam_slm_mwh"),
            ("Pallivasal (PVL — 37.5 MW)", "pallivasal_pvl_mwh"),
            ("Panniar (PNR — 32.4 MW)", "panniar_pnr_mwh"),
        )
        st_rows = []
        for rank_i, (label, col) in enumerate(station_meta, 1):
            tot_mwh = round(float(df_slots[col].sum()), 2)
            pk_mwh = round(float(df_slots[col].max()), 2)
            st_rows.append({"Capacity_Rank": rank_i, "Station_and_Reservoir": label, "Daily_Gen_MWh": tot_mwh, "Daily_Gen_MU": round(tot_mwh / 1000.0, 3), "Peak_30m_MWh": pk_mwh})
        st.dataframe(pd.DataFrame(st_rows), use_container_width=True, hide_index=True)

    df_dam = pd.read_sql(text(f"SELECT * FROM {k_pref}reservoir_levels_inflow ORDER BY capacity_rank ASC, report_date DESC"), k_eng)
    if not df_dam.empty:
        st.dataframe(df_dam, use_container_width=True, hide_index=True)
    else:
        pass

    # 5. PRINTABLE & EXPORTABLE 30-MINUTE SCHEDULE TABLE
    st.divider()
    st.markdown(f"#### 5. Printable 30-Minute Energy Schedule ({sel_k_day})")
    if not df_slots.empty:
        disp_cols = {
            "time_slot": "Time",
            "kerala_consumption_mwh": "Consumption (MWh)",
            "total_gen_mwh": "Total Gen (MWh)",
            "hydro_total_mwh": "Hydro Total (MWh)",
            "total_import_mwh": "Import (MWh)",
            "solar_mwh": "Solar (MWh)",
            "wind_mwh": "Wind (MWh)",
            "idukki_idi_mwh": "Idukki (IDI)",
            "sabarigiri_sbg_mwh": "Sabarigiri (SBG)",
            "kuttiyadi_kdi_mwh": "Kuttiyadi (KDI)",
            "lower_periyar_lp_mwh": "Lower Periyar (LP)"
        }
        df_print = df_slots[list(disp_cols.keys())].rename(columns=disp_cols)
        st.dataframe(df_print, use_container_width=True, hide_index=True)
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df_print.to_excel(writer, sheet_name=f"30Min_Log_{sel_k_day}", index=False)
            df_pwr.drop(columns=["Year_Month", "Year"]).to_excel(writer, sheet_name="Daily_Grid_Summary", index=False)
        c_dl1, c_dl2 = st.columns(2)
        c_dl1.download_button(f"📊 Download Printable Excel ({sel_k_day}.xlsx)", buf.getvalue(), f"KSEB_Printable_Log_{sel_k_day}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        c_dl2.download_button(f"📄 Download CSV ({sel_k_day}.csv)", df_print.to_csv(index=False), f"KSEB_30Min_Log_{sel_k_day}.csv")

    from pathlib import Path as _DamPath
    import streamlit.components.v1 as _dam_components

    st.divider()
    st.subheader("🏞️ Kerala Dams — Monthly & Day-Wise Inflow Prediction")
    from kseb_db_bridge import render_live_dam_inflow_table as _render_live_dam
    _dam_rendered = _render_live_dam("dam_inflow_table.html")
    if _dam_rendered:
        _dam_components.html(_dam_rendered, height=740, scrolling=True)
