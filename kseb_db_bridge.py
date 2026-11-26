import json
import sqlite3
from pathlib import Path
import pandas as pd

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]
MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

def _get_db_path():
    base = Path(__file__).resolve().parent
    for candidate in [
        base / "kseb_sldc_telemetry.db",
        Path("/opt/monsoon_jyotisha_app/kseb_sldc_telemetry.db"),
        Path("/home/shan/Kerala_Weather_Prediction_dev/kseb_sldc_telemetry.db"),
    ]:
        if candidate.exists():
            return candidate
    return None

def render_live_demand_table(html_filename="kseb_demand_prediction.html"):
    base = Path(__file__).resolve().parent
    html_path = base / html_filename
    if not html_path.exists():
        return None
    html = html_path.read_text(encoding="utf-8")

    db_path = _get_db_path()
    if not db_path:
        return html

    try:
        conn = sqlite3.connect(str(db_path))
        df = pd.read_sql_query("""
            SELECT
                report_date,
                CAST(total_consumption_mu AS REAL) AS demand_mu,
                CAST(hydro_generation_mu AS REAL) AS hydro_mu,
                CAST(central_share_import_mu AS REAL) AS central_mu,
                CAST(COALESCE(thermal_ipp_mu, 0) + COALESCE(solar_mu, 0) + COALESCE(wind_mu, 0) + COALESCE(small_hydro_mu, 0) AS REAL) AS ipp_solar_mu,
                CAST(COALESCE(evening_peak_mw, morning_peak_mw, 0) AS REAL) AS peak_mw
            FROM daily_power_summary
            WHERE report_date IS NOT NULL AND total_consumption_mu IS NOT NULL
        """, conn)
        conn.close()

        if df.empty:
            return html

        df["dt"] = pd.to_datetime(df["report_date"], errors="coerce")
        df = df.dropna(subset=["dt"])
        df["month_num"] = df["dt"].dt.month

        # Compute daily averages per calendar month from real SLDC logs, scaled to full month days
        monthly_records = []
        for idx in range(12):
            m_num = idx + 1
            days_in_m = MONTH_DAYS[idx]
            sub = df[df["month_num"] == m_num]
            if not sub.empty:
                d_mu = round(float(sub["demand_mu"].mean()) * days_in_m, 1)
                h_mu = round(float(sub["hydro_mu"].mean()) * days_in_m, 1)
                c_mu = round(float(sub["central_mu"].mean()) * days_in_m, 1)
                i_mu = round(float(sub["ipp_solar_mu"].mean()) * days_in_m, 1)
                p_mw = int(round(float(sub["peak_mw"].max())))
                # Estimate MW breakdown proportional to energy share
                tot_sup_mu = max(h_mu + c_mu + i_mu, 1.0)
                h_mw = int(round(p_mw * (h_mu / tot_sup_mu) * 0.98))
                c_mw = int(round(p_mw * (c_mu / tot_sup_mu) * 0.98))
                i_mw = int(round(p_mw * (i_mu / tot_sup_mu) * 0.98))
                monthly_records.append({
                    "month": MONTH_NAMES[idx],
                    "days": days_in_m,
                    "demandMU": d_mu, "hydroMU": h_mu, "centralMU": c_mu, "ippSolarMU": i_mu,
                    "demandMW": p_mw, "hydroMW": h_mw, "centralMW": c_mw, "ippSolarMW": i_mw,
                })

        if len(monthly_records) == 12:
            js_data = json.dumps(monthly_records)
            html = html.replace("const DATA = [", f"const DATA = {js_data};\n  const _UNUSED_DATA = [", 1)
            html = html.replace("Weather-Adjusted KSEB Grid Forecast", f"Calibrated from {len(df):,} live SLDC records (kseb_sldc_telemetry.db)")
    except Exception:
        pass

    return html

def render_live_dam_inflow_table(html_filename="dam_inflow_table.html"):
    base = Path(__file__).resolve().parent
    html_path = base / html_filename
    if not html_path.exists():
        return None
    html = html_path.read_text(encoding="utf-8")

    db_path = _get_db_path()
    if not db_path:
        return html

    try:
        conn = sqlite3.connect(str(db_path))
        df = pd.read_sql_query("""
            SELECT report_date, reservoir_name, full_capacity_mcm, daily_inflow_mcm
            FROM reservoir_levels_inflow
            WHERE report_date IS NOT NULL AND reservoir_name IS NOT NULL
        """, conn)
        conn.close()

        if df.empty:
            return html

        df["dt"] = pd.to_datetime(df["report_date"], errors="coerce")
        df = df.dropna(subset=["dt"])
        df["month_num"] = df["dt"].dt.month
        df["inflow_val"] = pd.to_numeric(df["daily_inflow_mcm"], errors="coerce").fillna(0.0)
        df["cap_val"] = pd.to_numeric(df["full_capacity_mcm"], errors="coerce").fillna(0.0)

        # Build lookup dictionary by lowercase reservoir name
        res_stats = {}
        for r_name, grp in df.groupby("reservoir_name"):
            key = str(r_name).strip().lower()
            cap = float(grp["cap_val"].max())
            m_inflows = []
            for m_idx in range(12):
                m_sub = grp[grp["month_num"] == (m_idx + 1)]
                if not m_sub.empty:
                    m_inflows.append(round(float(m_sub["inflow_val"].mean()) * MONTH_DAYS[m_idx], 2))
                else:
                    m_inflows.append(None)
            res_stats[key] = {"cap": cap, "monthly": m_inflows}

        inject_js = f"""
  const LIVE_SLDC_DAMS = {json.dumps(res_stats)};
  dams = dams.map(d => {{
    const key = d.name.toLowerCase();
    const matchKey = Object.keys(LIVE_SLDC_DAMS).find(k => k.includes(key) || key.includes(k));
    if (matchKey) {{
      const rec = LIVE_SLDC_DAMS[matchKey];
      const updatedInflow = d.inflow.map((orig, idx) => rec.monthly[idx] !== null ? rec.monthly[idx] : orig);
      return {{
        ...d,
        cap: rec.cap > 0 ? rec.cap : d.cap,
        inflow: updatedInflow
      }};
    }}
    return d;
  }});
  renderTable();
"""
        html = html.replace("renderTable();\n</script>", inject_js + "\n</script>", 1)
    except Exception:
        pass

    return html

def render_live_tod_table(html_filename="kseb_tod_demand.html"):
    base = Path(__file__).resolve().parent
    html_path = base / html_filename
    if not html_path.exists():
        return None
    html = html_path.read_text(encoding="utf-8")

    db_path = _get_db_path()
    if not db_path:
        return html

    try:
        conn = sqlite3.connect(str(db_path))
        df = pd.read_sql_query("""
            SELECT
                s.report_date,
                SUM(CASE WHEN s.slot_idx BETWEEN 17 AND 36 THEN s.kerala_consumption_mwh ELSE 0 END) / 1000.0 AS day_mu,
                SUM(CASE WHEN s.slot_idx BETWEEN 37 AND 47 THEN s.kerala_consumption_mwh ELSE 0 END) / 1000.0 AS peak_mu,
                SUM(CASE WHEN s.slot_idx = 48 OR s.slot_idx <= 16 THEN s.kerala_consumption_mwh ELSE 0 END) / 1000.0 AS offpeak_mu,
                MAX(COALESCE(d.total_generation_mu, 0) + COALESCE(d.central_share_import_mu, 0)) AS sup_mu,
                MAX(CASE WHEN s.slot_idx BETWEEN 37 AND 47 THEN (COALESCE(s.total_gen_mwh, 0) + COALESCE(s.total_import_mwh, 0)) * 2.0 ELSE 0 END) AS peak_sup_mw
            FROM slot_30min_energy s
            LEFT JOIN daily_power_summary d ON s.report_date = d.report_date
            WHERE s.report_date IS NOT NULL AND s.kerala_consumption_mwh IS NOT NULL
            GROUP BY s.report_date
        """, conn)
        conn.close()

        if df.empty:
            return html

        df["dt"] = pd.to_datetime(df["report_date"], errors="coerce")
        df = df.dropna(subset=["dt"])
        df["month_num"] = df["dt"].dt.month

        live_by_month = {}
        for idx in range(12):
            m_num = idx + 1
            days_in_m = MONTH_DAYS[idx]
            sub = df[df["month_num"] == m_num]
            if not sub.empty:
                d_mu = round(float(sub["day_mu"].mean()) * days_in_m, 1)
                p_mu = round(float(sub["peak_mu"].mean()) * days_in_m, 1)
                o_mu = round(float(sub["offpeak_mu"].mean()) * days_in_m, 1)
                raw_sup = float(sub["sup_mu"].mean()) * days_in_m
                s_mu = round(raw_sup, 1) if raw_sup > 0 else round((d_mu + p_mu + o_mu) * 0.96, 1)
                raw_psup = float(sub["peak_sup_mw"].max())
                ps_mw = int(round(raw_psup)) if raw_psup > 0 else int(round((p_mu * 1000.0) / (days_in_m * 5.5) * 0.97))

                live_by_month[MONTH_NAMES[idx]] = {
                    "dayMU": d_mu,
                    "peakMU": p_mu,
                    "offPeakMU": o_mu,
                    "supplyMU": s_mu,
                    "peakSupplyMW": ps_mw,
                }

        if live_by_month:
            inject_js = f"""
  const LIVE_TOD_DB = {json.dumps(live_by_month)};
  TOD_DATA = TOD_DATA.map(row => LIVE_TOD_DB[row.month] ? {{ ...row, ...LIVE_TOD_DB[row.month] }} : row);
  document.getElementById("dbStatus").textContent = "Live SLDC Telemetry ({len(df):,} days • {len(live_by_month)}/12 months calibrated)";
  renderTable();
"""
            html = html.replace("renderTable();\n</script>", inject_js + "\n</script>", 1)
    except Exception:
        pass

    return html
