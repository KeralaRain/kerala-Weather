import os, re, glob, itertools, imaplib, email
from email.header import decode_header
from datetime import datetime
import pandas as pd
from sqlalchemy import create_engine, text

def load_env(path="~/.kseb_mail.env"):
    full = os.path.expanduser(path)
    if not os.path.exists(full):
        return {}
    cfg = {}
    with open(full) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    return cfg

def get_isolated_kseb_engine():
    pg_url = os.getenv("DATABASE_URL", "postgresql://jyotisha:monsoon2026@localhost:5432/monsoon_jyotisha")
    try:
        eng = create_engine(pg_url, connect_args={"connect_timeout": 2})
        with eng.begin() as c:
            c.execute(text("CREATE SCHEMA IF NOT EXISTS kseb_telemetry"))
        return eng, "kseb_telemetry."
    except Exception:
        repo_kdb = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kseb_sldc_telemetry.db")
        if os.path.exists(repo_kdb) and os.path.getsize(repo_kdb) > 4096:
            return create_engine(f"sqlite:///{repo_kdb}"), ""
        db_dir = os.path.expanduser("~/.monsoon_jyotisha")
        os.makedirs(db_dir, exist_ok=True)
        return create_engine(f"sqlite:///{os.path.join(db_dir, 'kseb_sldc_telemetry.db')}"), ""

def init_kseb_tables(eng, prefix):
    stmts = (
        f"""CREATE TABLE IF NOT EXISTS {prefix}daily_power_summary (
            report_date TEXT PRIMARY KEY,
            day_name TEXT,
            total_consumption_mu REAL,
            total_generation_mu REAL,
            hydro_generation_mu REAL,
            thermal_ipp_mu REAL,
            solar_mu REAL,
            wind_mu REAL,
            small_hydro_mu REAL,
            central_share_import_mu REAL,
            morning_peak_mw REAL,
            evening_peak_mw REAL,
            night_min_mw REAL,
            avg_frequency_hz REAL,
            source_filename TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS {prefix}slot_30min_energy (
            report_date TEXT,
            slot_idx INT,
            time_slot TEXT,
            kerala_consumption_mwh REAL,
            total_gen_mwh REAL,
            hydro_total_mwh REAL,
            total_import_mwh REAL,
            solar_mwh REAL,
            wind_mwh REAL,
            small_hydro_mwh REAL,
            idukki_idi_mwh REAL,
            sabarigiri_sbg_mwh REAL,
            kuttiyadi_kdi_mwh REAL,
            lower_periyar_lp_mwh REAL,
            neriamangalam_nlm_mwh REAL,
            sholayar_slr_mwh REAL,
            sengulam_slm_mwh REAL,
            pallivasal_pvl_mwh REAL,
            panniar_pnr_mwh REAL,
            poringalkuthu_pgl_mwh REAL,
            PRIMARY KEY (report_date, slot_idx)
        )""",
        f"""CREATE TABLE IF NOT EXISTS {prefix}reservoir_levels_inflow (
            report_date TEXT,
            capacity_rank INT,
            reservoir_name TEXT,
            full_capacity_mcm REAL,
            water_level_m REAL,
            live_storage_mcm REAL,
            storage_pct REAL,
            daily_inflow_mcm REAL,
            PRIMARY KEY (report_date, reservoir_name)
        )""",
        f"""CREATE TABLE IF NOT EXISTS {prefix}email_ingest_log (
            message_uid TEXT PRIMARY KEY,
            report_date TEXT,
            filename TEXT,
            processed_at TEXT
        )"""
    )
    with eng.begin() as c:
        for s in stmts:
            c.execute(text(s))

def extract_date_from_filename(fname):
    m = re.search(r"(\d{1,2})[.\-_](\d{1,2})[.\-_](20\d{2})", fname)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{y:04d}-{mo:02d}-{d:02d}"
    return None

def _f(row, idx):
    try:
        if idx >= len(row) or pd.isna(row.iloc[idx]):
            return 0.0
        v = row.iloc[idx]
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).replace(",", "").strip()
        m = re.search(r"^[-+]?\d*\.?\d+$", s)
        return float(m.group(0)) if m else 0.0
    except Exception:
        return 0.0

def _fmt_time(val, idx):
    s = str(val).strip()
    if "00:00:00" in s and "1900" in s:
        return "24:00"
    m = re.search(r"(\d{1,2}:\d{2})", s)
    if m:
        return m.group(1).zfill(5)
    mins = (idx + 1) * 30
    return f"{mins // 60:02d}:{mins % 60:02d}"

def parse_and_store_xls(filepath, report_date, fname, eng, prefix):
    xl = pd.ExcelFile(filepath, engine="xlrd")
    df_e = xl.parse("Energy Log", header=None) if "Energy Log" in xl.sheet_names else xl.parse(next(iter(xl.sheet_names)), header=None)
    day_name = str(df_e.iat[0, 0]).strip() if pd.notna(df_e.iat[0, 0]) else ""

    slots = []
    for idx in range(48):
        r_i = idx + 2
        if r_i >= len(df_e):
            break
        row = df_e.iloc[r_i]
        ts = _fmt_time(row.iat[1], idx)
        slots.append({
            "report_date": report_date, "slot_idx": idx + 1, "time_slot": ts,
            "kerala_consumption_mwh": round(_f(row, 38), 3), "total_gen_mwh": round(_f(row, 24), 3),
            "hydro_total_mwh": round(_f(row, 18), 3), "total_import_mwh": round(_f(row, 36), 3),
            "solar_mwh": round(_f(row, 45), 3), "wind_mwh": round(_f(row, 46), 3),
            "small_hydro_mwh": round(_f(row, 47), 3), "idukki_idi_mwh": round(_f(row, 12), 3),
            "sabarigiri_sbg_mwh": round(_f(row, 14), 3), "kuttiyadi_kdi_mwh": round(_f(row, 2), 3),
            "lower_periyar_lp_mwh": round(_f(row, 11), 3), "neriamangalam_nlm_mwh": round(_f(row, 10), 3),
            "sholayar_slr_mwh": round(_f(row, 5), 3), "sengulam_slm_mwh": round(_f(row, 8), 3),
            "pallivasal_pvl_mwh": round(_f(row, 7), 3), "panniar_pnr_mwh": round(_f(row, 9), 3),
            "poringalkuthu_pgl_mwh": round(_f(row, 3), 3),
        })

    cons_mu = round(sum(s["kerala_consumption_mwh"] for s in slots) / 1000.0, 3)
    gen_mu = round(sum(s["total_gen_mwh"] for s in slots) / 1000.0, 3)
    hyd_mu = round(sum(s["hydro_total_mwh"] for s in slots) / 1000.0, 3)
    imp_mu = round(sum(s["total_import_mwh"] for s in slots) / 1000.0, 3)
    sol_mu = round(sum(s["solar_mwh"] for s in slots) / 1000.0, 3)
    wnd_mu = round(sum(s["wind_mwh"] for s in slots) / 1000.0, 3)
    shd_mu = round(sum(s["small_hydro_mwh"] for s in slots) / 1000.0, 3)
    thm_mu = round(max(0.0, gen_mu - hyd_mu - sol_mu - wnd_mu - shd_mu), 3)

    mng_pk = round(float(df_e.iat[51, 8]), 1) if len(df_e) > 51 and pd.notna(df_e.iat[51, 8]) else 0.0
    nit_mn = round(float(df_e.iat[53, 8]), 1) if len(df_e) > 53 and pd.notna(df_e.iat[53, 8]) else 0.0
    evg_pk = round(float(df_e.iat[55, 8]), 1) if len(df_e) > 55 and pd.notna(df_e.iat[55, 8]) else 0.0
    avg_fq = 50.0
    if "Active Power Log" in xl.sheet_names:
        df_a = xl.parse("Active Power Log", header=None)
        if len(df_a) > 60 and pd.notna(df_a.iat[60, 1]):
            avg_fq = round(float(df_a.iat[60, 1]), 3)

    with eng.begin() as c:
        c.execute(text(f"DELETE FROM {prefix}slot_30min_energy WHERE report_date = :rd"), {"rd": report_date})
        for s in slots:
            c.execute(text(f"""INSERT INTO {prefix}slot_30min_energy VALUES (
                :report_date, :slot_idx, :time_slot, :kerala_consumption_mwh, :total_gen_mwh, :hydro_total_mwh,
                :total_import_mwh, :solar_mwh, :wind_mwh, :small_hydro_mwh, :idukki_idi_mwh, :sabarigiri_sbg_mwh,
                :kuttiyadi_kdi_mwh, :lower_periyar_lp_mwh, :neriamangalam_nlm_mwh, :sholayar_slr_mwh,
                :sengulam_slm_mwh, :pallivasal_pvl_mwh, :panniar_pnr_mwh, :poringalkuthu_pgl_mwh
            )"""), s)
        c.execute(text(f"DELETE FROM {prefix}daily_power_summary WHERE report_date = :rd"), {"rd": report_date})
        c.execute(text(f"""INSERT INTO {prefix}daily_power_summary VALUES (
            :rd, :dn, :cmu, :gmu, :hmu, :tmu, :smu, :wmu, :shmu, :imu, :mpk, :epk, :nmn, :afq, :fn
        )"""), {
            "rd": report_date, "dn": day_name, "cmu": cons_mu, "gmu": gen_mu, "hmu": hyd_mu,
            "tmu": thm_mu, "smu": sol_mu, "wmu": wnd_mu, "shmu": shd_mu, "imu": imp_mu,
            "mpk": mng_pk, "epk": evg_pk, "nmn": nit_mn, "afq": avg_fq, "fn": fname
        })

def reparse_local_downloads():
    eng, prefix = get_isolated_kseb_engine()
    init_kseb_tables(eng, prefix)
    dl_dir = os.path.expanduser("~/kseb_telemetry_worker/downloads")
    count = 0
    for fp in sorted(glob.glob(os.path.join(dl_dir, "*.xls*"))):
        fn = os.path.basename(fp)
        rd = extract_date_from_filename(fn)
        if rd:
            parse_and_store_xls(fp, rd, fn, eng, prefix)
            count += 1
    print(f"Re-parsed {count} local KSEB Energy Log files into clean named tables!")

def run_harvester():
    cfg = load_env()
    if not cfg.get("KSEB_EMAIL_PASS") or "PUT_YOUR_NEW_PASSWORD_HERE" in cfg.get("KSEB_EMAIL_PASS", ""):
        reparse_local_downloads()
        return
    eng, prefix = get_isolated_kseb_engine()
    init_kseb_tables(eng, prefix)
    with eng.connect() as c:
        done_uids = {str(next(iter(r))) for r in c.execute(text(f"SELECT message_uid FROM {prefix}email_ingest_log")).fetchall()}
        done_dates = {str(next(iter(r))) for r in c.execute(text(f"SELECT report_date FROM {prefix}daily_power_summary")).fetchall()}

    mail = imaplib.IMAP4_SSL(cfg["KSEB_IMAP_HOST"], int(cfg.get("KSEB_IMAP_PORT", 993)))
    mail.login(cfg["KSEB_EMAIL_USER"], cfg["KSEB_EMAIL_PASS"])
    mail.select("INBOX")
    status, data = mail.uid("search", None, '(FROM "ldc@sldckerala.com")')
    raw_uids = next(iter(data)) if (status == "OK" and data and next(iter(data))) else b""
    imported = 0
    for uid_b in raw_uids.split():
        uid = uid_b.decode()
        if uid in done_uids:
            continue
        res, msg_data = mail.uid("fetch", uid_b, "(RFC822)")
        if res != "OK" or not msg_data:
            continue
        msg_bytes = next(itertools.islice(next(iter(msg_data)), 1, None))
        msg = email.message_from_bytes(msg_bytes)
        for part in msg.walk():
            raw_fn = part.get_filename()
            if not raw_fn:
                continue
            fname = "".join(p.decode(enc or "utf-8") if isinstance(p, bytes) else p for p, enc in decode_header(raw_fn))
            if "energy log" in fname.lower() and fname.lower().endswith((".xls", ".xlsx")):
                r_date = extract_date_from_filename(fname) or datetime.now().strftime("%Y-%m-%d")
                if r_date in done_dates:
                    continue
                save_path = os.path.join(os.path.expanduser("~/kseb_telemetry_worker/downloads"), fname)
                with open(save_path, "wb") as fp:
                    fp.write(part.get_payload(decode=True))
                parse_and_store_xls(save_path, r_date, fname, eng, prefix)
                with eng.begin() as c:
                    c.execute(text(f"INSERT INTO {prefix}email_ingest_log VALUES (:u, :rd, :fn, :ts) ON CONFLICT DO NOTHING"), {
                        "u": uid, "rd": r_date, "fn": fname, "ts": datetime.now().isoformat()
                    })
                done_uids.add(uid)
                done_dates.add(r_date)
                imported += 1
    mail.logout()
    print(f"Imported {imported} new KSEB Energy Logs.")
