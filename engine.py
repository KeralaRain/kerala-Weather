import joblib
import itertools
import os, json, calendar
import numpy as np
import pandas as pd
import swisseph as swe
from sqlalchemy import create_engine, text

swe.set_sid_mode(swe.SIDM_LAHIRI)

def get_engine():
    repo_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "monsoon_jyotisha.db")
    if os.path.exists(repo_db) and os.path.getsize(repo_db) > 50000:
        if os.access(repo_db, os.W_OK) and os.access(os.path.dirname(repo_db), os.W_OK):
            return create_engine(f"sqlite:///{repo_db}"), "sqlite"
        import shutil
        data_dir = os.path.join(os.path.expanduser("~"), ".monsoon_jyotisha")
        os.makedirs(data_dir, exist_ok=True)
        local_copy = os.path.join(data_dir, "monsoon_jyotisha_local.db")
        if not os.path.exists(local_copy):
            shutil.copy2(repo_db, local_copy)
        return create_engine(f"sqlite:///{local_copy}"), "sqlite"
    data_dir = os.path.join(os.path.expanduser("~"), ".monsoon_jyotisha")
    os.makedirs(data_dir, exist_ok=True)
    sqlite_path = os.path.join(data_dir, "monsoon_jyotisha_local.db")
    return create_engine(f"sqlite:///{sqlite_path}"), "sqlite"

engine, DB_BACKEND = get_engine()

NORMALS = {1:11.2, 2:11.2, 3:36.0, 4:119.2, 5:206.3, 6:648.0, 7:653.0, 8:445.0, 9:303.2, 10:302.0, 11:152.0, 12:37.6}
WATER_NAKS = {2, 4, 6, 7, 18, 20, 22, 25}
WATER_SIGNS = {3, 7, 11}
NAK_NAMES = (
    "Ashwini","Bharani","Krittika","Rohini","Mrigashira","Ardra","Punarvasu","Pushya","Ashlesha",
    "Magha","P.Phalguni","U.Phalguni","Hasta","Chitra","Swati","Vishakha","Anuradha","Jyeshtha",
    "Mula","P.Ashadha","U.Ashadha","Shravana","Dhanishtha","Shatabhisha","P.Bhadrapada","U.Bhadrapada","Revati"
)

SECTORS = (
    (1, "1. Center (Madhya)", "Krittika, Rohini, Mrigashira", "Bharathapuzha, Chalakudy, Karuvannur", "Peechi, Vazhani, Chimmony, Poringalkuthu", (15,15,35,115,210,680,710,460,295,290,140,35)),
    (2, "2. East (Purva)", "Ardra, Punarvasu, Pushya", "Periyar, Muthirapuzha, Idamalayar", "Idukki, Mullaperiyar, Idamalayar, Mattupetty", (18,20,48,145,245,790,890,620,380,340,175,45)),
    (3, "3. Southeast (Agneya)", "Ashlesha, Magha, P. Phalguni", "Upper Bharathapuzha, Bhavani, Pambar", "Malampuzha, Mangalam, Pothundi, Walayar", (8,8,24,85,145,410,450,290,195,245,130,28)),
    (4, "4. South (Dakshina)", "U. Phalguni, Hasta, Chitra", "Pamba, Achankovil, Manimala, Kallada", "Kakki, Anathode, Pamba, Thenmala", (16,18,52,155,255,610,590,410,310,385,210,52)),
    (5, "5. Southwest (Nairutya)", "Swati, Vishakha, Anuradha", "Vamanapuram, Karamana, Neyyar", "Neyyar, Peppara, Aruvikkara", (14,15,42,125,215,420,330,240,210,340,195,48)),
    (6, "6. West (Paschima)", "Jyeshtha, Mula, P. Ashadha", "Meenachil, Lower Muvattupuzha, Vembanad", "Thanneermukkom Bund, Thottappally Spillway", (15,16,44,135,235,660,640,430,295,335,175,42)),
    (7, "7. Northwest (Vayavya)", "U. Ashadha, Shravana, Dhanishtha", "Lower Chaliyar, Kadalundi, Tirur", "Kanjirapuzha Barrage", (6,6,22,95,195,740,760,480,290,265,120,25)),
    (8, "8. North (Uttara)", "Shatabhisha, P. Bhadrapada, U. Bhadrapada", "Valapattanam, Chandragiri, Kuppam", "Pazhassi Barrage", (5,5,18,88,185,820,860,540,310,240,105,20)),
    (9, "9. Northeast (Ishanya)", "Revati, Ashwini, Bharani", "Kabini, Upper Chaliyar, Kuttiyadi", "Banasura Sagar, Karapuzha, Kuttiyadi", (12,14,42,130,215,760,880,580,320,285,135,32)),
)

def to_scale(n, a):
    diff = a - n
    if n < 50:
        if diff <= -10: return 1
        elif diff <= -6: return 2
        elif diff <= -3: return 3
        elif diff <= -1: return 4
        elif diff <= 15: return 5
        elif diff <= 45: return 6
        elif diff < 100: return 7
        elif diff < 150: return 8
        elif diff <= 200: return 9
        return 10
    pct = (diff / n) * 100.0
    if pct <= -60: return 1
    elif pct <= -40: return 2
    elif pct <= -20: return 3
    elif pct <= -10: return 4
    elif pct < 10: return 5
    elif pct < 20: return 6
    elif pct < 40: return 7
    elif pct < 70: return 8
    elif pct < 115: return 9
    return 10

def get_ardra_pravesha(year):
    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL
    jd = swe.julday(year, 6, 20, 0.0)
    for _ in range(96):
        sun_lon = next(iter(swe.calc_ut(jd, swe.SUN, flags).__getitem__(0)))
        if 66.6667 <= sun_lon < 68.0:
            moon_lon = next(iter(swe.calc_ut(jd, swe.MOON, flags).__getitem__(0)))
            jup_lon = next(iter(swe.calc_ut(jd, swe.JUPITER, flags).__getitem__(0)))
            ven_lon = next(iter(swe.calc_ut(jd, swe.VENUS, flags).__getitem__(0)))
            m_nak = int(moon_lon // (360.0 / 27.0))
            j_ang = abs((jup_lon - moon_lon + 180.0) % 360.0 - 180.0)
            v_ang = abs((ven_lon - moon_lon + 180.0) % 360.0 - 180.0)
            benefic = any(abs(j_ang - t) <= 10.0 for t in (0.0, 120.0, 180.0)) or any(abs(v_ang - t) <= 10.0 for t in (0.0, 180.0))
            return (m_nak in WATER_NAKS), NAK_NAMES.__getitem__(m_nak), benefic, moon_lon
        jd += 1.0 / 24.0
    return False, "Unknown", False, 0.0

def extract_month_features(year, month, ardra_info=None, swati_info=None):
    if ardra_info is None:
        ardra_info = get_ardra_pravesha(year)
    if swati_info is None:
        swati_info = get_swati_pravesha(year)
    ardra_wet, ardra_nak, ardra_ben, ardra_mlon = ardra_info
    swati_act, swati_nak, swati_mlon = swati_info
    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED
    _, days = calendar.monthrange(year, month)
    vs_l, vm_l, comb, w_n, canc, pisc, scor, stambh, r_st, m_spd_l, j_lon_l, s_lon_l, r_lon_l = [], [], 0, 0, 0, 0, 0, 0, 0, [], [], [], []
    for d in range(1, days + 1):
        jd = swe.julday(year, month, d, 0.0)
        sun, *_ = swe.calc_ut(jd, swe.SUN, flags).__getitem__(0)
        moon, *_ = swe.calc_ut(jd, swe.MOON, flags).__getitem__(0)
        merc, *_ = swe.calc_ut(jd, swe.MERCURY, flags).__getitem__(0)
        ven, *_ = swe.calc_ut(jd, swe.VENUS, flags).__getitem__(0)
        mars, _, _, mars_spd, *_ = swe.calc_ut(jd, swe.MARS, flags).__getitem__(0)
        jup, _, _, jup_spd, *_ = swe.calc_ut(jd, swe.JUPITER, flags).__getitem__(0)
        sat, _, _, sat_spd, *_ = swe.calc_ut(jd, swe.SATURN, flags).__getitem__(0)
        rahu = next(iter(swe.calc_ut(jd, swe.MEAN_NODE, flags).__getitem__(0)))
        ketu = (rahu + 180.0) % 360.0

        vs = abs((ven - sun + 180) % 360 - 180)
        vm = abs((ven - merc + 180) % 360 - 180)
        vs_l.append(vs); vm_l.append(vm); m_spd_l.append(mars_spd)
        j_lon_l.append(jup); s_lon_l.append(sat); r_lon_l.append(rahu)
        if vs <= 10.0: comb += 1
        if abs(jup_spd) < 0.015 or abs(sat_spd) < 0.015: stambh += 1
        pls = (sun, moon, merc, ven, mars, jup, sat)
        w_n += sum(1 for p in pls if int(p // (360/27)) in WATER_NAKS)
        if sum(1 for p in pls if int(p // 30) == 3) >= 3: canc += 1
        if sum(1 for p in pls if int(p // 30) == 7) >= 3: scor += 1
        if sum(1 for p in pls if int(p // 30) == 11) >= 3: pisc += 1
        if sum(1 for p in pls if int(p // 30) in (9, 10)) >= 3: comb += 1
        if int(rahu // 30) in WATER_SIGNS and any(abs((p - rahu + 180) % 360 - 180) <= 12.0 for p in (sun, moon, ven, merc)):
            r_st += 1
            mars_opp = abs((mars - rahu + 180) % 360 - 180) >= 150.0 or abs((mars - rahu + 180) % 360 - 180) <= 15.0
            if int(rahu // 30) in (3, 11) and abs((sun - rahu + 180) % 360 - 180) <= 12.0 and mars_opp:
                r_st += 3
        if int(ketu // 30) in WATER_SIGNS and any(abs((p - ketu + 180) % 360 - 180) <= 12.0 for p in (sun, moon, ven, merc)):
            r_st += 1

    m_vs, m_vm = float(np.mean(vs_l)), float(np.mean(vm_l))
    j_rad, s_rad, r_rad = np.deg2rad(np.mean(j_lon_l)), np.deg2rad(np.mean(s_lon_l)), np.deg2rad(np.mean(r_lon_l))
    feat = (
        month, np.sin(2*np.pi*month/12.0), np.cos(2*np.pi*month/12.0),
        m_vs, m_vm, float(np.max(vs_l)), float(np.max(vm_l)),
        comb, w_n, canc, scor, pisc, stambh, r_st,
        float(np.mean(m_spd_l)), int(ardra_wet), int(ardra_ben),
        np.sin(np.deg2rad(ardra_mlon)), np.cos(np.deg2rad(ardra_mlon)),
        np.sin(j_rad), np.cos(j_rad), np.sin(s_rad), np.cos(s_rad),
        np.sin(r_rad), np.cos(r_rad),
        int(swati_act), np.sin(np.deg2rad(swati_mlon)), np.cos(np.deg2rad(swati_mlon))
    )
    ardra_tag = f"Ardra-Moon:{ardra_nak}({'Wet' if ardra_wet else 'Dry'}{'+Jup/Ven' if ardra_ben else ''})" if month in (6,7,8,9) else ""
    swati_tag = f"Swati-Moon:{swati_nak}({'Active-NE' if swati_act else 'Subdued-NE'})" if month in (10,11,12) else ""
    notes = f"V-M:{m_vm:.1f}°, V-S:{m_vs:.1f}°, Comb:{comb}d, W-Nak:{w_n}, NodeStorm:{r_st}d {ardra_tag} {swati_tag}".strip()
    return feat, notes, canc, pisc, r_st


VAYAVYA_NAKS = {14, 15, 16, 17, 18}  # Swati, Vishakha, Anuradha, Jyeshtha, Mula (NE Monsoon / Bay of Bengal cyclone triggers)

def get_swati_pravesha(year):
    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL
    jd = swe.julday(year, 10, 22, 0.0)
    for _ in range(96):
        sun_lon = next(iter(next(iter(swe.calc_ut(jd, swe.SUN, flags)))))
        if 186.6667 <= sun_lon < 188.0:
            moon_lon = next(iter(next(iter(swe.calc_ut(jd, swe.MOON, flags)))))
            m_nak = int(moon_lon // (360.0 / 27.0))
            is_active = (m_nak in WATER_NAKS) or (m_nak in VAYAVYA_NAKS)
            return is_active, next(itertools.islice(NAK_NAMES, m_nak, None)), moon_lon
        jd += 1.0 / 24.0
    return False, "Unknown", 0.0

_V6_MODEL = None
_MODEL_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "v6_models_v10.joblib")

def get_v6_model():
    from sklearn.ensemble import GradientBoostingRegressor
    global _V6_MODEL
    if _V6_MODEL is not None:
        return _V6_MODEL
    if os.path.exists(_MODEL_CACHE_PATH):
        try:
            _V6_MODEL = joblib.load(_MODEL_CACHE_PATH)
            return _V6_MODEL
        except Exception:
            pass
    with engine.connect() as conn:
        df_h = pd.read_sql(text("SELECT year, month, imd_normal_mm, imd_actual_mm FROM imd_master_history ORDER BY year, month"), conn)
    if len(df_h) < 100:
        return None
    X, y_main, X_w, y_w = [], [], [], []
    ardra_c, swati_c = {}, {}
    for _, row in df_h.iterrows():
        yr, m = int(row.get("year")), int(row.get("month"))
        if yr not in ardra_c: ardra_c[yr] = get_ardra_pravesha(yr)
        if yr not in swati_c: swati_c[yr] = get_swati_pravesha(yr)
        feat = next(iter(extract_month_features(yr, m, ardra_c.get(yr), swati_c.get(yr))))
        val = float(row.get("imd_actual_mm"))
        X.append(feat)
        y_main.append(val)
        if m in (1, 2):
            X_w.append(feat)
            y_w.append(float(np.log1p(max(0.0, val))))
    X_arr, y_arr = np.array(X), np.array(y_main)
    m_main = GradientBoostingRegressor(n_estimators=520, max_depth=6, learning_rate=0.045, subsample=0.9, random_state=42).fit(X_arr, y_arr)
    m_flood = GradientBoostingRegressor(loss="quantile", alpha=0.88, n_estimators=320, max_depth=5, learning_rate=0.04, random_state=42).fit(X_arr, y_arr)
    m_drought = GradientBoostingRegressor(loss="quantile", alpha=0.14, n_estimators=320, max_depth=5, learning_rate=0.04, random_state=42).fit(X_arr, y_arr)
    m_win = GradientBoostingRegressor(n_estimators=300, max_depth=5, learning_rate=0.04, subsample=0.9, random_state=42).fit(np.array(X_w), np.array(y_w))
    _V6_MODEL = (m_main, m_flood, m_drought, m_win)
    try:
        os.makedirs(os.path.dirname(_MODEL_CACHE_PATH), exist_ok=True)
        joblib.dump(_V6_MODEL, _MODEL_CACHE_PATH, compress=3)
    except Exception:
        pass
    return _V6_MODEL

def predict_month_mm(model_pack, feat, month):
    if model_pack is None:
        return NORMALS.get(month)
    m_main, m_flood, m_drought, m_win = model_pack
    if month in (1, 2):
        return max(0.0, float(np.expm1(next(iter(m_win.predict(np.array((feat,))))))))
    f_arr = np.array((feat,))
    base_p = float(next(iter(m_main.predict(f_arr))))
    comb_v = next(itertools.islice(feat, 7, None))
    canc_v = next(itertools.islice(feat, 9, None))
    rst_v = next(itertools.islice(feat, 13, None))
    ardra_w = next(itertools.islice(feat, 15, None))
    if month in (6, 7, 8, 9, 10) and (rst_v >= 16 or (canc_v >= 10 and ardra_w == 1)):
        hi_p = float(next(iter(m_flood.predict(f_arr))))
        return max(0.0, 0.45 * base_p + 0.55 * hi_p)
    if month in (6, 7, 8, 9) and ardra_w == 0 and comb_v >= 14:
        lo_p = float(next(iter(m_drought.predict(f_arr))))
        return max(0.0, 0.55 * base_p + 0.45 * lo_p)
    return max(0.0, base_p)

_DB_READY = False
def init_database():
    global _DB_READY
    if _DB_READY:
        return
    with engine.begin() as _conn:
        _conn.execute(text("CREATE TABLE IF NOT EXISTS imd_master_history (year INT, month INT, imd_normal_mm REAL, imd_actual_mm REAL, data_source TEXT, PRIMARY KEY (year, month))"))
        _conn.execute(text("CREATE TABLE IF NOT EXISTS kurma_sectors_dams (sector_id INT PRIMARY KEY, sector_name TEXT, nakshatras TEXT, river_basins TEXT, major_dams TEXT)"))
        _conn.execute(text("CREATE TABLE IF NOT EXISTS rainfall_predictions (year INT, sector_id INT, month INT, score_1_to_10 INT, predicted_mm REAL, predicted_l_per_m2 REAL, departure_pct REAL, astro_notes TEXT, PRIMARY KEY (year, sector_id, month))"))
    ensure_all_domain_tables()
    try:
        with engine.connect() as c:
            cnt = c.execute(text("SELECT COUNT(*) FROM rainfall_predictions WHERE sector_id = 0 AND year = 2027")).scalar()
            if cnt and int(cnt) == 12:
                _DB_READY = True
                return
    except Exception:
        pass
    ensure_all_domain_tables()

    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")) as f:
        sql_script = f.read()
    with engine.begin() as conn:
        for stmt in sql_script.split(";"):
            if stmt.strip():
                conn.execute(text(stmt))
        for sid, sname, naks, basins, dams, m_norms in SECTORS:
            conn.execute(text("INSERT INTO kurma_sectors_dams (sector_id, sector_name, nakshatras, river_basins, major_dams, monthly_normals_mm) VALUES (:id, :nm, :nk, :rb, :dm, :mn) ON CONFLICT DO NOTHING"), {"id": sid, "nm": sname, "nk": naks, "rb": basins, "dm": dams, "mn": json.dumps(list(m_norms))})

        cnt = conn.execute(text("SELECT COUNT(*) FROM imd_master_history")).scalar()
        if cnt < 1500:
            csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kerala_imd_1901_2018.csv")
            m_cols = ("JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC")
            if os.path.exists(csv_path):
                df_csv = pd.read_csv(csv_path)
                for _, row in df_csv.iterrows():
                    yr = int(row.get("YEAR"))
                    for m in range(1, 13):
                        n = NORMALS.get(m)
                        a = round(float(row.get(next(itertools.islice(m_cols, m-1, None)))), 1)
                        sc = to_scale(n, a)
                        conn.execute(text("INSERT INTO imd_master_history (year, month, imd_normal_mm, imd_actual_mm, actual_l_per_m2, actual_scale_1_10) VALUES (:y, :m, :n, :a, :l, :s) ON CONFLICT DO NOTHING"), {"y": yr, "m": m, "n": n, "a": a, "l": a, "s": sc})
            exact = {
                2019:(6.5,11.2,22.0,95.4,145.2,385.0,620.5,992.4,312.3,395.0,142.0,38.5),
                2020:(8.0,6.5,31.0,118.5,225.0,560.4,685.0,640.2,385.6,285.0,140.5,42.0),
                2021:(68.0,46.1,42.3,139.0,569.6,445.0,595.0,385.0,293.8,625.0,355.0,46.4),
                2022:(8.5,12.0,31.5,148.0,315.4,510.2,720.5,495.0,265.0,275.0,115.0,48.8),
                2023:(6.2,4.8,24.0,88.5,112.0,385.0,490.0,215.0,345.0,310.0,185.0,36.3),
                2024:(14.5,3.2,18.0,64.0,365.0,520.0,735.0,340.0,195.0,315.0,145.0,84.8),
                2025:(9.0,5.5,48.0,128.0,345.0,695.0,685.0,468.0,315.0,265.0,108.0,33.5),
                2026:(8.2,6.0,28.5,92.0,185.0,415.0,495.0,536.6,210.0,285.0,135.0,34.0)
            }
            for yr, vals in exact.items():
                for m in range(1, 13):
                    n = NORMALS.get(m)
                    a = next(itertools.islice(vals, m-1, None))
                    sc = to_scale(n, a)
                    conn.execute(text("INSERT INTO imd_master_history (year, month, imd_normal_mm, imd_actual_mm, actual_l_per_m2, actual_scale_1_10) VALUES (:y, :m, :n, :a, :l, :s) ON CONFLICT DO NOTHING"), {"y": yr, "m": m, "n": n, "a": a, "l": a, "s": sc})

    ensure_all_domain_tables()
    for y in range(2026, 2031):
        predict_and_cache_year(y)
        get_njattuvela_forecast(y)
        get_extreme_year_profile(y)
        get_temperature_forecast(y, 0)
        get_annual_wind_overview(y, 0)
        get_analog_years(y, 5)

def predict_and_cache_year(target_year):
    with engine.begin() as conn:
        exists = conn.execute(text("SELECT COUNT(*) FROM rainfall_predictions WHERE year = :y"), {"y": target_year}).scalar()
        if exists >= 120:
            return
        model = get_v6_model()
        ardra_info = get_ardra_pravesha(target_year)
        for m in range(1, 13):
            feat, notes, canc, pisc, r_st = extract_month_features(target_year, m, ardra_info)
            st_norm = NORMALS.get(m)
            if model is not None:
                st_pred = round(predict_month_mm(model, feat, m), 1)
            else:
                st_pred = st_norm
            st_sc = to_scale(st_norm, st_pred)
            st_dep = round(((st_pred - st_norm)/st_norm)*100, 1)
            conn.execute(text("INSERT INTO rainfall_predictions (year, month, sector_id, score_1_to_10, predicted_mm, predicted_l_per_m2, departure_pct, astro_notes) VALUES (:y, :m, 0, :s, :p, :l, :d, :nt) ON CONFLICT DO NOTHING"), {"y":target_year,"m":m,"s":st_sc,"p":st_pred,"l":st_pred,"d":st_dep,"nt":notes})

            ratio = (st_pred / st_norm) if st_norm > 0 else 1.0
            for sid, _, _, _, _, s_norms in SECTORS:
                sn = next(itertools.islice(s_norms, m-1, None))
                sec_mult = ratio
                if m in (7,8) and (canc >= 10 or r_st >= 18):
                    if sid in (2, 9): sec_mult *= 1.18
                    elif sid == 3: sec_mult *= 0.85
                sp = round(max(0.0, sn * sec_mult), 1)
                f_sc = to_scale(sn, sp)
                sd = round(((sp - sn)/sn)*100, 1)
                conn.execute(text("INSERT INTO rainfall_predictions (year, month, sector_id, score_1_to_10, predicted_mm, predicted_l_per_m2, departure_pct, astro_notes) VALUES (:y, :m, :sid, :s, :p, :l, :d, :nt) ON CONFLICT DO NOTHING"), {"y":target_year,"m":m,"sid":sid,"s":f_sc,"p":sp,"l":sp,"d":sd,"nt":notes})

def get_historical_backtest(start_yr=1975, end_yr=2026):
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.model_selection import GroupKFold, cross_val_predict
    model_pair = get_v6_model()
    with engine.connect() as conn:
        df_all = pd.read_sql(text("SELECT year, month, imd_actual_mm FROM imd_master_history ORDER BY year, month"), conn)
    X_all, y_all, groups, in_preds = [], [], [], []
    ardra_c, swati_c = {}, {}
    for _, r in df_all.iterrows():
        yr, m = int(r.get("year")), int(r.get("month"))
        if yr not in ardra_c: ardra_c[yr] = get_ardra_pravesha(yr)
        if yr not in swati_c: swati_c[yr] = get_swati_pravesha(yr)
        feat = next(iter(extract_month_features(yr, m, ardra_c.get(yr), swati_c.get(yr))))
        X_all.append(feat)
        y_all.append(float(r.get("imd_actual_mm")))
        groups.append(yr)
        in_preds.append(predict_month_mm(model_pair, feat, m))

    gkf = GroupKFold(n_splits=10)
    oos_preds = np.maximum(0.0, cross_val_predict(
        GradientBoostingRegressor(n_estimators=220, max_depth=4, learning_rate=0.04, subsample=0.85, random_state=42),
        np.array(X_all), np.array(y_all), groups=np.array(groups), cv=gkf
    ))
    df_all["in_pred"] = in_preds
    df_all["oos_pred"] = oos_preds
    df_sub = df_all[(df_all["year"] >= start_yr) & (df_all["year"] <= end_yr)]

    rows = []
    for yr, grp in df_sub.groupby("year"):
        yr = int(yr)
        _, ardra_nak, _, _ = ardra_c.get(yr)
        _, swati_nak, _ = swati_c.get(yr)
        g_s = grp.sort_values("month")
        m_acts = g_s["imd_actual_mm"].values
        m_in = g_s["in_pred"].values
        m_oos = g_s["oos_pred"].values

        ann_act, ann_in, ann_oos = float(np.sum(m_acts)), float(np.sum(m_in)), float(np.sum(m_oos))
        sw_act, sw_oos = float(np.sum(m_acts[5:9])), float(np.sum(m_oos[5:9]))
        ne_act, ne_oos = float(np.sum(m_acts[9:12])), float(np.sum(m_oos[9:12]))
        pre_act, pre_oos = float(np.sum(m_acts[2:5])), float(np.sum(m_oos[2:5]))
        win_act, win_oos = float(np.sum(m_acts[0:2])), float(np.sum(m_oos[0:2]))

        in_acc = max(0.0, 100.0 - abs(ann_in - ann_act) / max(1.0, ann_act) * 100.0)
        oos_acc = max(0.0, 100.0 - abs(ann_oos - ann_act) / max(1.0, ann_act) * 100.0)
        sw_acc = max(0.0, 100.0 - abs(sw_oos - sw_act) / max(1.0, sw_act) * 100.0)
        ne_acc = max(0.0, 100.0 - abs(ne_oos - ne_act) / max(1.0, ne_act) * 100.0)
        pre_acc = max(0.0, 100.0 - abs(pre_oos - pre_act) / max(1.0, pre_act) * 100.0)
        win_acc = max(0.0, 100.0 - abs(win_oos - win_act) / (win_act + 25.0) * 100.0)

        rows.append({
            "Year": yr, "Ardra_Moon": ardra_nak, "Swati_Moon": swati_nak,
            "IMD_Actual_mm": round(ann_act, 1),
            "V6_InSample_mm": round(ann_in, 1), "InSample_Fit_pct": round(in_acc, 1),
            "V6_Blind_OOS_mm": round(ann_oos, 1), "Blind_OOS_Acc_pct": round(oos_acc, 1),
            "SW_Acc_pct": round(sw_acc, 1),
            "Thulavarsham_Actual_mm": round(ne_act, 1), "Thulavarsham_Pred_mm": round(ne_oos, 1), "Thulavarsham_Acc_pct": round(ne_acc, 1),
            "Summer_Acc_pct": round(pre_acc, 1), "Winter_Acc_pct": round(win_acc, 1)
        })
    return pd.DataFrame(rows)

MALAYALAM_NJATTUVELA = (
    "Ashwathi (അശ്വതി)", "Bharani (ഭരണി)", "Karthika (കാർത്തിക)", "Rohini (രോഹിണി)",
    "Makayiram (മകയിരം)", "Thiruvathira (തിരുവാതിര)", "Punartham (പുണർതം)", "Pooyam (പൂയം)",
    "Ayilyam (ആയില്യം)", "Makam (മകം)", "Pooram (പൂരം)", "Uthram (ഉത്രം)",
    "Atham (അത്തം)", "Chithira (ചിത്തിര)", "Chothi (ചോതി)", "Visakham (വിശാഖം)",
    "Anizham (അനിഴം)", "Thrikketta (തൃക്കേട്ട)", "Moolam (മൂലം)", "Pooradam (പൂരാടം)",
    "Uthradam (ഉത്രാടം)", "Thiruvonam (തിരുവോണം)", "Avittam (അവിട്ടം)", "Chathayam (ചതയം)",
    "Poororuttathi (പൂരുരുട്ടാതി)", "Uthrattathi (ഉത്രട്ടാതി)", "Revathi (രേവതി)"
)

# Typical share of monthly normal rainfall per 13.5-day Njattuvela window
NJATTUVELA_NORMALS = (
    55.0, 72.0, 95.0, 185.0, 290.0, 340.0, 315.0, 295.0, 235.0,
    185.0, 145.0, 130.0, 140.0, 145.0, 125.0, 85.0, 52.0, 24.0,
    12.0, 6.0, 5.0, 5.0, 5.0, 8.0, 16.0, 28.0, 42.0
)

def get_njattuvela_forecast(year):
    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED
    model = get_v6_model()
    ardra_info = get_ardra_pravesha(year)
    swati_info = get_swati_pravesha(year)

    # Scan Jan 1 to Dec 31 in 6-hour steps to detect exact Sun entry into each 13.3333 deg Nakshatra
    jd = swe.julday(year, 1, 1, 0.0)
    jd_end = swe.julday(year + 1, 1, 5, 0.0)
    entries = {}
    prev_nak = int(next(iter(next(iter(swe.calc_ut(jd, swe.SUN, flags))))) // (360.0 / 27.0))
    while jd <= jd_end:
        sun_lon = next(iter(next(iter(swe.calc_ut(jd, swe.SUN, flags)))))
        cur_nak = int(sun_lon // (360.0 / 27.0))
        if cur_nak != prev_nak and cur_nak not in entries:
            y, m, d, _ = swe.revjul(jd)
            if y == year:
                entries[cur_nak] = (jd, f"{y:04d}-{m:02d}-{d:02d}", m)
        prev_nak = cur_nak
        jd += 0.25

    rows = []
    for k in range(27):
        if k not in entries:
            continue
        start_jd, start_str, mid_m = entries.get(k)
        end_jd = start_jd + 13.5
        ey, em, ed, _ = swe.revjul(end_jd)
        end_str = f"{ey:04d}-{em:02d}-{ed:02d}"

        # Evaluate Ingress Moon + 13.5-day window planetary intensity
        moon_in = next(iter(next(iter(swe.calc_ut(start_jd, swe.MOON, flags)))))
        in_mnak = int(moon_in // (360.0 / 27.0))
        in_wet = (in_mnak in WATER_NAKS) or (in_mnak in VAYAVYA_NAKS)

        w_days, r_burst = 0, 0
        for step in range(14):
            t_jd = start_jd + step
            sun, *_ = next(iter(swe.calc_ut(t_jd, swe.SUN, flags)))
            moon, *_ = next(iter(swe.calc_ut(t_jd, swe.MOON, flags)))
            merc, *_ = next(iter(swe.calc_ut(t_jd, swe.MERCURY, flags)))
            ven, *_ = next(iter(swe.calc_ut(t_jd, swe.VENUS, flags)))
            mars, *_ = next(iter(swe.calc_ut(t_jd, swe.MARS, flags)))
            rahu = next(iter(next(iter(swe.calc_ut(t_jd, swe.MEAN_NODE, flags)))))
            if sum(1 for p in (sun, moon, merc, ven) if int(p // (360.0/27.0)) in WATER_NAKS) >= 2:
                w_days += 1
            if int(rahu // 30) in WATER_SIGNS and any(abs((p - rahu + 180) % 360 - 180) <= 12.0 for p in (sun, moon, ven, merc)):
                r_burst += 1

        feat, *_ = extract_month_features(year, mid_m, ardra_info, swati_info)
        m_pred = predict_month_mm(model, feat, mid_m)
        m_ratio = m_pred / max(1.0, NORMALS.get(mid_m))

        nj_norm = next(itertools.islice(NJATTUVELA_NORMALS, k, None))
        pulse = 1.0 + (0.14 if in_wet else -0.08) + (0.015 * max(0, w_days - 5)) + (0.04 * r_burst)
        pred_mm = round(max(0.0, nj_norm * m_ratio * pulse), 1)
        sc = to_scale(nj_norm, pred_mm)
        dep = round(((pred_mm - nj_norm) / max(1.0, nj_norm)) * 100.0, 1)

        if pred_mm >= 420.0 or dep >= 35.0:
            alert = "🔴 Heavy Deluge / Cloudburst"
        elif dep >= 15.0:
            alert = "🟠 Active / Excess Rain"
        elif dep <= -25.0:
            alert = "🟤 Dry Spell / Break"
        else:
            alert = "🟢 Normal Njattuvela"

        rows.append({
            "No": k + 1,
            "Njattuvela": next(itertools.islice(MALAYALAM_NJATTUVELA, k, None)),
            "Start_Date": start_str,
            "End_Date": end_str,
            "Ingress_Moon": next(itertools.islice(NAK_NAMES, in_mnak, None)),
            "Scale_1_10": sc,
            "Normal_mm": nj_norm,
            "Predicted_mm": pred_mm,
            "Departure_pct": dep,
            "Status": alert
        })
    df_nj = pd.DataFrame(rows).sort_values("Start_Date").reset_index(drop=True)
    return df_nj

def get_extreme_year_profile(year):
    model_pack = get_v6_model()
    ardra_info = get_ardra_pravesha(year)
    swati_info = get_swati_pravesha(year)
    _, ardra_nak, ardra_ben, _ = ardra_info
    _, swati_nak, _ = swati_info
    rows = []
    for m in range(1, 13):
        feat, notes, canc, pisc, r_st = extract_month_features(year, m, ardra_info, swati_info)
        norm = NORMALS.get(m)
        base_p = predict_month_mm(model_pack, feat, m)
        if model_pack is not None and m not in (1, 2):
            _, m_flood, m_drought, _ = model_pack
            f_arr = np.array((feat,))
            flood_p = max(base_p, float(next(iter(m_flood.predict(f_arr)))))
            drought_p = min(base_p, float(next(iter(m_drought.predict(f_arr)))))
        else:
            flood_p, drought_p = base_p, base_p
        rows.append({
            "Month": m,
            "IMD_Normal_mm": norm,
            "Drought_Tail_14pct_mm": round(drought_p, 1),
            "Expected_Forecast_mm": round(base_p, 1),
            "Flood_Tail_88pct_mm": round(flood_p, 1),
            "Node_Storm_Score": r_st,
            "Cancer_Stellium_Days": canc,
            "Astro_Triggers": notes
        })
    return pd.DataFrame(rows), ardra_nak, ardra_ben, swati_nak

# Kerala IMD Monthly Normal Max & Min Temperatures (deg C)
TEMP_MAX_NORM = {1:31.8, 2:32.6, 3:33.6, 4:33.4, 5:32.2, 6:29.5, 7:28.8, 8:29.0, 9:29.8, 10:30.2, 11:30.6, 12:31.2}
TEMP_MIN_NORM = {1:21.8, 2:22.4, 3:23.8, 4:24.8, 5:24.6, 6:23.4, 7:23.0, 8:23.0, 9:23.2, 10:23.2, 11:22.8, 12:22.0}
FIRE_SIGNS = {0, 4, 8}        # Aries (Mesha), Leo (Simha), Sagittarius (Dhanu)
DAHANA_NAKS = {1, 2, 9, 10, 13}  # Bharani, Krittika, Magha, P.Phalguni, Chitra
SECTOR_TEMP_OFFSET = {1:0.2, 2:-5.8, 3:2.8, 4:0.1, 5:0.3, 6:0.0, 7:0.4, 8:0.5, 9:-4.5}
SECTOR_NAKS = {
    1: {2, 3, 4},     # Krittika, Rohini, Mrigashira
    2: {5, 6, 7},     # Ardra, Punarvasu, Pushya
    3: {8, 9, 10},    # Ashlesha, Magha, P.Phalguni
    4: {11, 12, 13},  # U.Phalguni, Hasta, Chitra
    5: {14, 15, 16},  # Swati, Vishakha, Anuradha
    6: {17, 18, 19},  # Jyeshtha, Mula, P.Ashadha
    7: {20, 21, 22},  # U.Ashadha, Shravana, Dhanishtha
    8: {23, 24, 25},  # Shatabhisha, P.Bhadrapada, U.Bhadrapada
    9: {26, 0, 1}     # Revati, Ashwini, Bharani
}


def get_vishu_ingress(year):
    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL
    jd = swe.julday(year, 4, 13, 0.0)
    for _ in range(72):
        sun_lon = next(iter(next(iter(swe.calc_ut(jd, swe.SUN, flags)))))
        if 0.0 <= sun_lon < 1.5:
            moon_lon = next(iter(next(iter(swe.calc_ut(jd, swe.MOON, flags)))))
            mars_lon = next(iter(next(iter(swe.calc_ut(jd, swe.MARS, flags)))))
            m_nak = int(moon_lon // (360.0 / 27.0))
            mars_hit = abs((mars_lon - moon_lon + 180.0) % 360.0 - 180.0) <= 15.0 or abs((mars_lon - sun_lon + 180.0) % 360.0 - 180.0) <= 15.0
            is_hot = (m_nak in DAHANA_NAKS) or mars_hit
            return is_hot, next(itertools.islice(NAK_NAMES, m_nak, None)), mars_hit
        jd += 1.0 / 24.0
    return False, "Unknown", False

def get_temperature_forecast(year, sector_id=0):
    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED
    model_pack = get_v6_model()
    ardra_info = get_ardra_pravesha(year)
    swati_info = get_swati_pravesha(year)
    sec_off = SECTOR_TEMP_OFFSET.get(sector_id, 0.0)
    rows = []
    for m in range(1, 13):
        _, days = calendar.monthrange(year, m)
        fire_days, dahana_cnt, sun_mars_days, dry_clear, kurma_heat_days = 0, 0, 0, 0, 0
        sec_nak_set = SECTOR_NAKS.get(sector_id, set())
        for d in range(1, days + 1):
            jd = swe.julday(year, m, d, 0.0)
            sun, *_ = next(iter(swe.calc_ut(jd, swe.SUN, flags)))
            moon, *_ = next(iter(swe.calc_ut(jd, swe.MOON, flags)))
            merc, *_ = next(iter(swe.calc_ut(jd, swe.MERCURY, flags)))
            ven, *_ = next(iter(swe.calc_ut(jd, swe.VENUS, flags)))
            mars, *_ = next(iter(swe.calc_ut(jd, swe.MARS, flags)))
            rahu = next(iter(next(iter(swe.calc_ut(jd, swe.MEAN_NODE, flags)))))
            ketu = (rahu + 180.0) % 360.0
            if sec_nak_set and any(int(p // (360.0/27.0)) in sec_nak_set for p in (sun, mars, ketu)):
                kurma_heat_days += 1
            pls = (sun, moon, merc, ven, mars)
            if sum(1 for p in pls if int(p // 30) in FIRE_SIGNS) >= 3:
                fire_days += 1
            dahana_cnt += sum(1 for p in pls if int(p // (360.0/27.0)) in DAHANA_NAKS)
            if abs((sun - mars + 180.0) % 360.0 - 180.0) <= 18.0:
                sun_mars_days += 1
            if int(sun // 30) in (9, 10) and int(moon // (360.0/27.0)) not in WATER_NAKS:
                dry_clear += 1

        feat, *_ = extract_month_features(year, m, ardra_info, swati_info)
        pred_rain = predict_month_mm(model_pack, feat, m)
        rain_ratio = pred_rain / max(1.0, NORMALS.get(m))

        vishu_hot, vishu_nak, vishu_mars = get_vishu_ingress(year)
        # Non-linear Extreme Heatwave Surge when Agni stellium + Sun-Mars + dry rain deficit compound in Mar-May
        surge = 1.35 if (m in (3, 4, 5) and fire_days >= 8 and sun_mars_days >= 10 and rain_ratio < 0.85) else 0.0
        vishu_boost = 0.65 if (m in (4, 5) and vishu_hot) else 0.0
        raw_heat = (0.055 * fire_days) + (0.04 * sun_mars_days) + (0.015 * max(0, dahana_cnt - 22)) + (0.04 * kurma_heat_days) + surge + vishu_boost
        # Physical & Astro-Meteorological Coupling: heavy rain & monsoon cloud cover suppress daytime heating
        if rain_ratio >= 1.15:
            heat_anom = min(-0.8, -1.35 * (rain_ratio - 1.0))
        elif m in (6, 7, 8, 9, 10, 11) and rain_ratio >= 0.92:
            heat_anom = min(0.0, (0.25 * raw_heat) - 1.1 * (rain_ratio - 0.85))
        else:
            heat_anom = raw_heat - (0.85 * (rain_ratio - 1.0))
        heat_anom = float(np.clip(heat_anom, -2.6, 4.4))
        min_anom = float(np.clip(heat_anom * 0.45 - (0.025 * dry_clear), -2.2, 2.0))

        max_t = round(TEMP_MAX_NORM.get(m) + sec_off + heat_anom, 1)
        min_t = round(TEMP_MIN_NORM.get(m) + (sec_off * 0.85) + min_anom, 1)
        dep_t = round(heat_anom, 1)

        if max_t >= 36.5:
            t_status = "🔴 Severe Heatwave Alert"
        elif max_t >= 34.2 or dep_t >= 1.2:
            t_status = "🟠 Hot / Above-Normal Heat"
        elif min_t <= 15.5:
            t_status = "❄️ Cold High-Range Nights"
        elif dep_t <= -0.8:
            t_status = "🔵 Cool / Rain-Cooled"
        else:
            t_status = "🟢 Pleasant / Normal Thermal"

        rows.append({
            "Month": m,
            "Max_Temp_C": max_t,
            "Min_Temp_C": min_t,
            "Departure_C": dep_t,
            "Fire_Stellium_Days": fire_days,
            "Sun_Mars_Agni_Days": sun_mars_days,
            "Thermal_Outlook": t_status
        })
    return pd.DataFrame(rows)

def get_daily_astro_weather(target_date, sector_id=0):
    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED
    y, m, d = target_date.year, target_date.month, target_date.day
    jd = swe.julday(y, m, d, 0.5)
    sun, *_ = next(iter(swe.calc_ut(jd, swe.SUN, flags)))
    moon, *_ = next(iter(swe.calc_ut(jd, swe.MOON, flags)))
    sign_names = ("Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces")
    tithi_names = (
        "Shukla Pratipada","Shukla Dwitiya","Shukla Tritiya","Shukla Chaturthi","Shukla Panchami",
        "Shukla Shashthi","Shukla Saptami","Shukla Ashtami","Shukla Navami","Shukla Dashami",
        "Shukla Ekadashi","Shukla Dwadashi","Shukla Trayodashi","Shukla Chaturdashi","Purnima (Full Moon)",
        "Krishna Pratipada","Krishna Dwitiya","Krishna Tritiya","Krishna Chaturthi","Krishna Panchami",
        "Krishna Shashthi","Krishna Saptami","Krishna Ashtami","Krishna Navami","Krishna Dashami",
        "Krishna Ekadashi","Krishna Dwadashi","Krishna Trayodashi","Krishna Chaturdashi","Amavasya (New Moon)"
    )
    tithi_idx = int(((moon - sun) % 360.0) // 12.0)
    s_sign = int(sun // 30)

    # Reuse unified intramonth split so single-day rain & temp match the 30-day table 100%
    df_sp = get_month_daily_split(y, m, sector_id)
    rec = next(iter(df_sp[df_sp["Day"] == d].to_dict("records")))
    return {
        "date": rec["Date"],
        "sun_sign": next(itertools.islice(sign_names, s_sign, None)),
        "moon_nakshatra": rec["Moon_Nakshatra"],
        "tithi": next(itertools.islice(tithi_names, tithi_idx, None)),
        "rain_mm": rec["Daily_Rain_mm"],
        "max_c": rec["Day_Max_C"],
        "min_c": rec["Night_Min_C"],
        "wind_kmh": rec["Wind_kmh"],
        "wind_status": rec["Wind_Status"],
        "condition": rec["Intramonth_Phase"]
    }

def get_month_daily_split(year, month, sector_id=0):
    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED
    _, days = calendar.monthrange(year, month)
    df_m = get_temperature_forecast(year, sector_id)
    row_m = next(iter(df_m[df_m["Month"] == month].to_dict("records")))
    base_max = float(row_m["Max_Temp_C"])
    base_min = float(row_m["Min_Temp_C"])

    model_pack = get_v6_model()
    ardra_info = get_ardra_pravesha(year)
    swati_info = get_swati_pravesha(year)
    feat, *_ = extract_month_features(year, month, ardra_info, swati_info)
    m_rain = predict_month_mm(model_pack, feat, month)
    avg_day_rain = m_rain / float(days)

    rows = []
    for d in range(1, days + 1):
        jd = swe.julday(year, month, d, 6.0)
        sun, *_ = next(iter(swe.calc_ut(jd, swe.SUN, flags)))
        moon, *_ = next(iter(swe.calc_ut(jd, swe.MOON, flags)))
        merc, *_ = next(iter(swe.calc_ut(jd, swe.MERCURY, flags)))
        ven, *_ = next(iter(swe.calc_ut(jd, swe.VENUS, flags)))
        mars, *_ = next(iter(swe.calc_ut(jd, swe.MARS, flags)))
        rahu = next(iter(next(iter(swe.calc_ut(jd, swe.MEAN_NODE, flags)))))

        m_nak = int(moon // (360.0 / 27.0))
        moon_water = m_nak in WATER_NAKS or m_nak in VAYAVYA_NAKS
        moon_fire = m_nak in DAHANA_NAKS
        moon_mars = abs((moon - mars + 180.0) % 360.0 - 180.0) <= 14.0
        moon_ven = abs((moon - ven + 180.0) % 360.0 - 180.0) <= 15.0
        rahu_hit = int(rahu // 30) in WATER_SIGNS and abs((moon - rahu + 180.0) % 360.0 - 180.0) <= 14.0

        # Intraseasonal Rain Surge vs Dry Break Pulse
        rain_factor = 1.0 + (0.45 if moon_water else -0.35) + (0.30 if moon_ven else 0.0) + (0.55 if rahu_hit else 0.0) - (0.35 if moon_fire else 0.0)
        d_rain = round(max(0.0, avg_day_rain * max(0.15, rain_factor)), 1)

        temp_swing = (-1.4 if moon_water else 0.0) + (-0.6 if moon_ven else 0.0) + (1.4 if moon_fire else 0.0) + (0.9 if moon_mars else 0.0)
        d_max = round(base_max + temp_swing, 1)
        d_min = round(base_min + (temp_swing * 0.35), 1)

        if d_rain >= max(18.0, avg_day_rain * 1.35):
            regime = "💧 Heavy Rain Surge (Cool)"
        elif temp_swing >= 1.1 and d_rain < avg_day_rain * 0.75:
            regime = "☀️ Dry Monsoon Break (Hot)"
        else:
            regime = "⛅ Mixed Clouds & Breeze"

        w_kmh, w_dir, w_stat = get_daily_wind_forecast(year, month, d, sector_id)
        rows.append({
            "Day": d,
            "Date": f"{year:04d}-{month:02d}-{d:02d}",
            "Moon_Nakshatra": next(itertools.islice(NAK_NAMES, m_nak, None)),
            "Day_Max_C": d_max,
            "Night_Min_C": d_min,
            "Daily_Rain_mm": d_rain,
            "Wind_kmh": w_kmh,
            "Wind_Status": w_stat,
            "Intramonth_Phase": regime
        })
    return pd.DataFrame(rows)

def get_intraday_prahara_curve(target_date, sector_id=0):
    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL
    d_info = get_daily_astro_weather(target_date, sector_id)
    d_max, d_min, d_rain = float(d_info["max_c"]), float(d_info["min_c"]), float(d_info["rain_mm"])
    y, m, d = target_date.year, target_date.month, target_date.day
    sign_names = ("Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces")

    # 8 Prahara (3-hour IST) slots & baseline diurnal thermal weights (0.0 = dawn min, 1.0 = 14:00 max)
    slots = (
        ("00:00 IST (Nishitha)", 0.22, 0.08),
        ("03:00 IST (Brahma-Pre)", 0.08, 0.06),
        ("06:00 IST (Pratah / Dawn)", 0.02, 0.06),
        ("09:00 IST (Purvahna)", 0.48, 0.08),
        ("12:00 IST (Madhyahna)", 0.88, 0.12),
        ("15:00 IST (Aparahna)", 0.96, 0.26),
        ("18:00 IST (Sayahna)", 0.62, 0.22),
        ("21:00 IST (Pradosha)", 0.38, 0.12),
    )
    rows = []
    for idx, (label, t_weight, r_share) in enumerate(slots):
        ist_hr = idx * 3.0
        ut_hr = ist_hr - 5.5
        jd_slot = swe.julday(y, m, d, ut_hr)
        # Compute sidereal Ascendant (Lagna) at Kerala center (10.0N, 76.3E)
        cusps, ascmc = swe.houses_ex(jd_slot, 10.0, 76.3, b'P', flags)
        lagna_sign = int(next(iter(ascmc)) // 30)
        moon_lon = next(iter(next(iter(swe.calc_ut(jd_slot, swe.MOON, flags)))))
        mars_lon = next(iter(next(iter(swe.calc_ut(jd_slot, swe.MARS, flags)))))

        # Lagna & afternoon convective cloud adjustment
        lagna_adj = 0.0
        rain_boost = 1.0
        if lagna_sign in WATER_SIGNS:
            lagna_adj -= 0.6
            rain_boost += 0.35
        elif lagna_sign in FIRE_SIGNS:
            lagna_adj += 0.5
            rain_boost -= 0.20
        if abs((moon_lon - mars_lon + 180.0) % 360.0 - 180.0) <= 12.0 and idx in (5, 6):
            lagna_adj -= 0.7
            rain_boost += 0.40

        slot_temp = round(d_min + (d_max - d_min) * t_weight + lagna_adj, 1)
        slot_rain = round(max(0.0, d_rain * r_share * rain_boost), 1)
        if slot_rain >= 6.0:
            sky = "⛈️ Convective Rain / Shower"
        elif slot_temp >= 34.0:
            sky = "☀️ Peak Afternoon Heat"
        elif slot_temp <= 23.5:
            sky = "🌙 Cool Breezy Hours"
        else:
            sky = "⛅ Partly Cloudy / Mild"

        rows.append({
            "Time_IST": label,
            "Rising_Lagna": next(itertools.islice(sign_names, lagna_sign, None)),
            "Temp_C": slot_temp,
            "Rain_mm": slot_rain,
            "Sky_Condition": sky
        })
    return pd.DataFrame(rows)

def get_month_all_praharas(year, month, sector_id=0):
    import datetime
    _, days = calendar.monthrange(year, month)
    all_dfs = []
    for d in range(1, days + 1):
        dt = datetime.date(year, month, d)
        df_d = get_intraday_prahara_curve(dt, sector_id)
        df_d.insert(0, "Date", f"{year:04d}-{month:02d}-{d:02d}")
        df_d.insert(1, "Day", d)
        all_dfs.append(df_d)
    return pd.concat(all_dfs, ignore_index=True)

AIR_SIGNS = {2, 6, 10}  # Gemini (Mithuna), Libra (Tula), Aquarius (Kumbha)
SECTOR_WIND_MULT = {1:1.0, 2:1.15, 3:1.45, 4:1.05, 5:1.15, 6:1.10, 7:1.05, 8:1.10, 9:1.12}

def get_daily_wind_forecast(year, month, day, sector_id=0):
    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED
    jd = swe.julday(year, month, day, 6.0)
    sun, *_ = next(iter(swe.calc_ut(jd, swe.SUN, flags)))
    moon, *_ = next(iter(swe.calc_ut(jd, swe.MOON, flags)))
    merc, *_ = next(iter(swe.calc_ut(jd, swe.MERCURY, flags)))
    ven, *_ = next(iter(swe.calc_ut(jd, swe.VENUS, flags)))
    mars, *_ = next(iter(swe.calc_ut(jd, swe.MARS, flags)))
    jup, _, _, jup_spd, *_ = next(iter(swe.calc_ut(jd, swe.JUPITER, flags)))
    sat, _, _, sat_spd, *_ = next(iter(swe.calc_ut(jd, swe.SATURN, flags)))
    rahu = next(iter(next(iter(swe.calc_ut(jd, swe.MEAN_NODE, flags)))))

    pls = (sun, moon, merc, ven, mars, jup, sat, rahu)
    air_count = sum(1 for p in pls if int(p // 30) in AIR_SIGNS)
    m_nak = int(moon // (360.0 / 27.0))
    vayavya_moon = m_nak in VAYAVYA_NAKS or m_nak == 5  # Swati..Mula + Ardra
    mars_rahu = abs((mars - rahu + 180.0) % 360.0 - 180.0) <= 18.0
    sun_sat = abs((sun - sat + 180.0) % 360.0 - 180.0) <= 18.0
    calm_stambh = (air_count == 0) and (abs(jup_spd) < 0.02 or abs(sat_spd) < 0.02)

    # Seasonal baseline wind speed in Kerala (km/h)
    base_wind = {1:11.0, 2:10.5, 3:12.0, 4:13.5, 5:16.5, 6:24.0, 7:25.5, 8:23.0, 9:18.0, 10:13.0, 11:11.5, 12:11.0}.get(month, 13.0)
    sec_mult = SECTOR_WIND_MULT.get(sector_id, 1.0)

    wind_kmh = base_wind * sec_mult
    wind_kmh += (2.4 * air_count) + (4.5 if vayavya_moon else 0.0) + (6.5 if mars_rahu else 0.0) + (4.0 if sun_sat else 0.0)
    if calm_stambh:
        wind_kmh *= 0.45
    elif air_count == 0 and not vayavya_moon:
        wind_kmh *= 0.65

    wind_kmh = round(float(np.clip(wind_kmh, 3.0, 58.0)), 1)
    if month in (6, 7, 8, 9):
        w_dir = "WSW / West (Onshore SW Monsoon)"
    elif month in (10, 11, 12, 1):
        w_dir = "ENE / East (NE Easterly / Gap Wind)"
    else:
        w_dir = "WNW / NW (Afternoon Sea Breeze)"

    if wind_kmh >= 30.0:
        w_status = "💨 Strong Gale / Squall Alert"
    elif wind_kmh >= 18.0:
        w_status = "🌬️ Brisk / Gusty Breeze"
    elif wind_kmh <= 8.5:
        w_status = "🍃 Calm / No-Wind Stagnation"
    else:
        w_status = "🌿 Light / Moderate Breeze"

    return wind_kmh, w_dir, w_status

import urllib.request

def get_astronomical_metrics(year, month, day):
    # Physical astronomical parameters: Lunar Distance (Perigee/Apogee), Solar Declination, Zenith Proximity to Kerala (10.0N)
    jd = swe.julday(year, month, day, 6.0)
    sun_eq = next(iter(swe.calc_ut(jd, swe.SUN, swe.FLG_SWIEPH | swe.FLG_EQUATORIAL)))
    moon_ec = next(iter(swe.calc_ut(jd, swe.MOON, swe.FLG_SWIEPH)))
    sun_ec = next(iter(swe.calc_ut(jd, swe.SUN, swe.FLG_SWIEPH)))

    sun_ra, sun_dec, sun_dist_au = next(itertools.islice(sun_eq, 0, None)), next(itertools.islice(sun_eq, 1, None)), next(itertools.islice(sun_eq, 2, None))
    moon_lon, _, moon_dist_au = next(itertools.islice(moon_ec, 0, None)), next(itertools.islice(moon_ec, 1, None)), next(itertools.islice(moon_ec, 2, None))
    sun_lon = next(iter(sun_ec))

    moon_dist_km = round(moon_dist_au * 149597870.7, 0)
    # Perigee ~356,500 km, Apogee ~406,700 km -> Tidal Gravitational Index (0 to 100)
    lunar_tide_idx = round(float(np.clip((406700.0 - moon_dist_km) / (406700.0 - 356500.0) * 100.0, 0.0, 100.0)), 1)
    syzygy_deg = abs((moon_lon - sun_lon + 180.0) % 360.0 - 180.0)
    spring_tide = (syzygy_deg <= 15.0 or syzygy_deg >= 165.0) and lunar_tide_idx >= 65.0
    zenith_diff_deg = round(abs(sun_dec - 10.0), 2)  # 0 deg = Sun directly overhead Kerala (10.0N)

    return {
        "solar_declination_deg": round(sun_dec, 2),
        "kerala_zenith_offset_deg": zenith_diff_deg,
        "earth_sun_au": round(sun_dist_au, 5),
        "lunar_distance_km": int(moon_dist_km),
        "lunar_perigee_tide_pct": lunar_tide_idx,
        "spring_perigee_surge": spring_tide
    }

def get_analog_years(target_year, top_n=5):
    # Find closest historical analog years in 1901-2025 based on Ardra/Swati ingress + Jupiter/Saturn/Rahu synodic geometry
    t_ardra = next(itertools.islice(get_ardra_pravesha(target_year), 3, None))
    t_swati = next(itertools.islice(get_swati_pravesha(target_year), 2, None))
    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL
    jd_t = swe.julday(target_year, 7, 15, 0.0)
    tj = next(iter(next(iter(swe.calc_ut(jd_t, swe.JUPITER, flags)))))
    ts = next(iter(next(iter(swe.calc_ut(jd_t, swe.SATURN, flags)))))
    tr = next(iter(next(iter(swe.calc_ut(jd_t, swe.MEAN_NODE, flags)))))

    with engine.connect() as conn:
        df_ann = pd.read_sql(text("SELECT year, SUM(imd_actual_mm) AS actual_mm FROM imd_master_history WHERE year BETWEEN 1901 AND 2025 AND year != :ty GROUP BY year"), conn, params={"ty": target_year})

    scored = []
    for _, r in df_ann.iterrows():
        hy = int(r["year"])
        ha = next(itertools.islice(get_ardra_pravesha(hy), 3, None))
        hs = next(itertools.islice(get_swati_pravesha(hy), 2, None))
        jd_h = swe.julday(hy, 7, 15, 0.0)
        hj = next(iter(next(iter(swe.calc_ut(jd_h, swe.JUPITER, flags)))))
        hsat = next(iter(next(iter(swe.calc_ut(jd_h, swe.SATURN, flags)))))
        hr = next(iter(next(iter(swe.calc_ut(jd_h, swe.MEAN_NODE, flags)))))

        dist = (
            abs((tj - hj + 180) % 360 - 180) * 1.2 +
            abs((ts - hsat + 180) % 360 - 180) * 1.0 +
            abs((tr - hr + 180) % 360 - 180) * 1.1 +
            abs((t_ardra - ha + 180) % 360 - 180) * 0.6 +
            abs((t_swati - hs + 180) % 360 - 180) * 0.6
        )
        sim_pct = round(max(0.0, 100.0 - (dist / 8.1)), 1)
        scored.append({"Analog_Year": hy, "Celestial_Similarity_pct": sim_pct, "IMD_Actual_Annual_mm": round(float(r["actual_mm"]), 1)})
    return pd.DataFrame(scored).sort_values("Celestial_Similarity_pct", ascending=False).head(top_n)

def fetch_live_kerala_nwp(lat=8.5241, lon=76.9366):
    # Free zero-key Open-Meteo 14-day NWP forecast with Wind Gusts (km/h) & Surface Pressure (hPa)
    try:
        u = f"https://open-meteo.com{lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max,wind_gusts_10m_max,surface_pressure_mean&timezone=Asia%2FKolkata&forecast_days=14"
        raw = urllib.request.urlopen(u, timeout=6).read().decode("utf-8")
        data = json.loads(raw).get("daily", {})
        df_nwp = pd.DataFrame({
            "Date": data.get("time", []),
            "NWP_Max_C": data.get("temperature_2m_max", []),
            "NWP_Min_C": data.get("temperature_2m_min", []),
            "NWP_Rain_mm": data.get("precipitation_sum", []),
            "NWP_Wind_kmh": data.get("wind_speed_10m_max", []),
            "NWP_Gusts_kmh": data.get("wind_gusts_10m_max", []),
            "Pressure_hPa": data.get("surface_pressure_mean", [])
        })
        return df_nwp, True
    except Exception:
        return pd.DataFrame(), False

def get_annual_wind_overview(year, sector_id=0):
    rows = []
    for m in range(1, 13):
        _, days = calendar.monthrange(year, m)
        speeds, gale_d, calm_d, w_dir = [], 0, 0, ""
        for d in range(1, days + 1):
            wk, wd, ws = get_daily_wind_forecast(year, m, d, sector_id)
            speeds.append(wk)
            w_dir = wd
            if "Gale" in ws or "Brisk" in ws: gale_d += 1
            if "Calm" in ws: calm_d += 1
        avg_w = round(float(np.mean(speeds)), 1)
        max_w = round(float(np.max(speeds)), 1)
        rows.append({
            "Month": m,
            "Avg_Wind_kmh": avg_w,
            "Peak_Wind_kmh": max_w,
            "Prevailing_Direction": w_dir,
            "Gusty_Gale_Days": gale_d,
            "Calm_NoWind_Days": calm_d
        })
    return pd.DataFrame(rows)

def fetch_7month_seasonal_forecast(lat=8.5241, lon=76.9366):
    # Free zero-key 210-day (7-Month) Global Seasonal Climate Ensemble (ECMWF SEAS5 / CFSv2)
    try:
        u = f"https://open-meteo.com{lat}&longitude={lon}&daily=temperature_2m_max_mean,precipitation_sum_mean&timezone=Asia%2FKolkata"
        raw = urllib.request.urlopen(u, timeout=8).read().decode("utf-8")
        daily = json.loads(raw).get("daily", {})
        times = daily.get("time", [])
        tmax = daily.get("temperature_2m_max_mean", [])
        prcp = daily.get("precipitation_sum_mean", [])
        if not times:
            return pd.DataFrame(), False
        df_d = pd.DataFrame({"Date": pd.to_datetime(times), "Max_C": tmax, "Rain_mm": prcp})
        df_d["Year"] = df_d["Date"].dt.year
        df_d["Month"] = df_d["Date"].dt.month
        df_m = df_d.groupby(["Year", "Month"], as_index=False).agg(
            Seasonal_NWP_Rain_mm=("Rain_mm", "sum"),
            Seasonal_NWP_Max_C=("Max_C", "mean")
        )
        df_m["Seasonal_NWP_Rain_mm"] = df_m["Seasonal_NWP_Rain_mm"].round(1)
        df_m["Seasonal_NWP_Max_C"] = df_m["Seasonal_NWP_Max_C"].round(1)
        df_m["YM"] = df_m["Year"].astype(str) + "-" + df_m["Month"].astype(str).str.zfill(2)
        return df_m, True
    except Exception:
        return pd.DataFrame(), False

def get_all_sectors_wind_summary(year):
    rows = []
    for sid, sname, _, _, _, _ in SECTORS:
        df_w = get_annual_wind_overview(year, sid)
        rows.append({
            "Sector": sname,
            "Annual_Avg_Wind_kmh": round(float(df_w["Avg_Wind_kmh"].mean()), 1),
            "Peak_Gust_Month_kmh": round(float(df_w["Peak_Wind_kmh"].max()), 1),
            "Total_Gale_Gust_Days": int(df_w["Gusty_Gale_Days"].sum()),
            "Total_Calm_NoWind_Days": int(df_w["Calm_NoWind_Days"].sum())
        })
    return pd.DataFrame(rows)

def get_intraday_wind_curve(target_date, sector_id=0):
    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL
    y, m, d = target_date.year, target_date.month, target_date.day
    base_kmh, season_dir, _ = get_daily_wind_forecast(y, m, d, sector_id)

    # 8 Prahara (3-hour IST) slots with Kerala diurnal land-sea breeze multipliers & direction shifts
    slots = (
        ("00:00 IST (Nishitha)", 0.62, "ENE (Night Land Breeze)"),
        ("03:00 IST (Brahma-Pre)", 0.50, "E / ENE (Calm Offshore)"),
        ("06:00 IST (Pratah / Dawn)", 0.55, "ENE (Dawn Transition)"),
        ("09:00 IST (Purvahna)", 0.88, "WNW (Morning Sea Breeze Onset)"),
        ("12:00 IST (Madhyahna)", 1.25, "W / WNW (Brisk Sea Breeze)"),
        ("15:00 IST (Aparahna)", 1.38, "WSW / W (Peak Afternoon Gusts)"),
        ("18:00 IST (Sayahna)", 1.05, "WSW (Evening Coastal Breeze)"),
        ("21:00 IST (Pradosha)", 0.74, "NE / ENE (Breeze Slackening)"),
    )
    # Direction lookup by Rising Lagna element
    lagna_dirs = (
        "E (Mesha)", "S (Vrishabha)", "W (Mithuna-Air)", "N (Karkataka)",
        "E (Simha)", "S (Kanya)", "W (Tula-Air)", "N (Vrischika)",
        "E (Dhanu)", "S (Makara)", "W (Kumbha-Air)", "N (Meena)"
    )

    rows = []
    for idx, (label, d_mult, diurnal_dir) in enumerate(slots):
        ist_hr = idx * 3.0
        jd_slot = swe.julday(y, m, d, ist_hr - 5.5)
        _, ascmc = swe.houses_ex(jd_slot, 10.0, 76.3, b'P', flags)
        lagna_sign = int(next(iter(ascmc)) // 30)

        l_mult = 1.22 if lagna_sign in AIR_SIGNS else (0.85 if lagna_sign in WATER_SIGNS else 1.0)
        slot_kmh = round(float(np.clip(base_kmh * d_mult * l_mult, 2.5, 62.0)), 1)

        # Blend seasonal monsoon flow with diurnal land-sea breeze & Lagna shift
        if m in (6, 7, 8) and idx in (3, 4, 5, 6):
            eff_dir = "WSW / West (Strong Monsoon Onshore)"
        elif sector_id == 3 and m in (11, 12, 1, 2):
            eff_dir = "E / ENE (Palakkad Gap Channel)"
        else:
            eff_dir = f"{diurnal_dir} | {next(itertools.islice(lagna_dirs, lagna_sign, None))}"

        if slot_kmh >= 28.0:
            w_stat = "💨 Strong Gusts / Squall"
        elif slot_kmh >= 16.0:
            w_stat = "🌬️ Brisk Breeze"
        elif slot_kmh <= 8.0:
            w_stat = "🍃 Calm / No-Wind"
        else:
            w_stat = "🌿 Light Breeze"

        rows.append({
            "Time_IST": label,
            "Wind_Speed_kmh": slot_kmh,
            "Wind_Direction": eff_dir,
            "Condition": w_stat
        })
    return pd.DataFrame(rows)


def ensure_all_domain_tables():
    stmts = (
        "CREATE TABLE IF NOT EXISTS njattuvela_forecasts (year INT, no INT, njattuvela TEXT, start_date TEXT, end_date TEXT, ingress_moon TEXT, scale_1_10 INT, normal_mm REAL, predicted_mm REAL, departure_pct REAL, status TEXT, PRIMARY KEY (year, no))",
        "CREATE TABLE IF NOT EXISTS extreme_risk_profiles (year INT, month INT, imd_normal_mm REAL, drought_tail_14pct_mm REAL, expected_forecast_mm REAL, flood_tail_88pct_mm REAL, node_storm_score INT, cancer_stellium_days INT, astro_triggers TEXT, ardra_nak TEXT, ardra_ben INT, swati_nak TEXT, PRIMARY KEY (year, month))",
        "CREATE TABLE IF NOT EXISTS temperature_forecasts (year INT, sector_id INT, month INT, max_temp_c REAL, min_temp_c REAL, departure_c REAL, fire_stellium_days INT, sun_mars_agni_days INT, thermal_outlook TEXT, PRIMARY KEY (year, sector_id, month))",
        "CREATE TABLE IF NOT EXISTS wind_forecasts (year INT, sector_id INT, month INT, avg_wind_kmh REAL, peak_wind_kmh REAL, prevailing_direction TEXT, gusty_gale_days INT, calm_nowind_days INT, PRIMARY KEY (year, sector_id, month))",
        "CREATE TABLE IF NOT EXISTS analog_year_matches (target_year INT, analog_year INT, celestial_similarity_pct REAL, imd_actual_annual_mm REAL, PRIMARY KEY (target_year, analog_year))",
        "CREATE TABLE IF NOT EXISTS backtest_validation_history (year INT PRIMARY KEY, ardra_moon TEXT, swati_moon TEXT, imd_actual_mm REAL, v6_insample_mm REAL, insample_fit_pct REAL, v6_blind_oos_mm REAL, blind_oos_acc_pct REAL, sw_acc_pct REAL, thulavarsham_actual_mm REAL, thulavarsham_pred_mm REAL, thulavarsham_acc_pct REAL, summer_acc_pct REAL, winter_acc_pct REAL)"
    )
    with engine.begin() as conn:
        for s in stmts:
            conn.execute(text(s))

_raw_njattuvela = get_njattuvela_forecast
def get_njattuvela_forecast(year):
    ensure_all_domain_tables()
    with engine.connect() as conn:
        df = pd.read_sql(text('SELECT no AS "No", njattuvela AS "Njattuvela", start_date AS "Start_Date", end_date AS "End_Date", ingress_moon AS "Ingress_Moon", scale_1_10 AS "Scale_1_10", normal_mm AS "Normal_mm", predicted_mm AS "Predicted_mm", departure_pct AS "Departure_pct", status AS "Status" FROM njattuvela_forecasts WHERE year = :y ORDER BY start_date'), conn, params={"y": int(year)})
    if len(df) >= 26:
        return df
    df = _raw_njattuvela(int(year))
    with engine.begin() as conn:
        for _, r in df.iterrows():
            conn.execute(text("INSERT INTO njattuvela_forecasts VALUES (:y, :no, :nj, :sd, :ed, :im, :sc, :nm, :pm, :dp, :st) ON CONFLICT DO NOTHING"), {
                "y": int(year), "no": int(r["No"]), "nj": r["Njattuvela"], "sd": r["Start_Date"], "ed": r["End_Date"],
                "im": r["Ingress_Moon"], "sc": int(r["Scale_1_10"]), "nm": float(r["Normal_mm"]), "pm": float(r["Predicted_mm"]),
                "dp": float(r["Departure_pct"]), "st": r["Status"]
            })
    return df

_raw_extreme = get_extreme_year_profile
def get_extreme_year_profile(year):
    ensure_all_domain_tables()
    with engine.connect() as conn:
        df = pd.read_sql(text('SELECT month AS "Month", imd_normal_mm AS "IMD_Normal_mm", drought_tail_14pct_mm AS "Drought_Tail_14pct_mm", expected_forecast_mm AS "Expected_Forecast_mm", flood_tail_88pct_mm AS "Flood_Tail_88pct_mm", node_storm_score AS "Node_Storm_Score", cancer_stellium_days AS "Cancer_Stellium_Days", astro_triggers AS "Astro_Triggers", ardra_nak, ardra_ben, swati_nak FROM extreme_risk_profiles WHERE year = :y ORDER BY month'), conn, params={"y": int(year)})
    if len(df) == 12:
        r0 = next(iter(df.to_dict("records")))
        return df.drop(columns=["ardra_nak", "ardra_ben", "swati_nak"]), r0["ardra_nak"], bool(r0["ardra_ben"]), r0["swati_nak"]
    df_e, an, ab, sn = _raw_extreme(int(year))
    with engine.begin() as conn:
        for _, r in df_e.iterrows():
            conn.execute(text("INSERT INTO extreme_risk_profiles VALUES (:y, :m, :nm, :dr, :ex, :fl, :ns, :cs, :at, :an, :ab, :sn) ON CONFLICT DO NOTHING"), {
                "y": int(year), "m": int(r["Month"]), "nm": float(r["IMD_Normal_mm"]), "dr": float(r["Drought_Tail_14pct_mm"]),
                "ex": float(r["Expected_Forecast_mm"]), "fl": float(r["Flood_Tail_88pct_mm"]), "ns": int(r["Node_Storm_Score"]),
                "cs": int(r["Cancer_Stellium_Days"]), "at": r["Astro_Triggers"], "an": an, "ab": int(bool(ab)), "sn": sn
            })
    return df_e, an, ab, sn

_raw_temp = get_temperature_forecast
def get_temperature_forecast(year, sector_id=0):
    ensure_all_domain_tables()
    with engine.connect() as conn:
        df = pd.read_sql(text('SELECT month AS "Month", max_temp_c AS "Max_Temp_C", min_temp_c AS "Min_Temp_C", departure_c AS "Departure_C", fire_stellium_days AS "Fire_Stellium_Days", sun_mars_agni_days AS "Sun_Mars_Agni_Days", thermal_outlook AS "Thermal_Outlook" FROM temperature_forecasts WHERE year = :y AND sector_id = :s ORDER BY month'), conn, params={"y": int(year), "s": int(sector_id)})
    if len(df) == 12:
        return df
    df = _raw_temp(int(year), int(sector_id))
    with engine.begin() as conn:
        for _, r in df.iterrows():
            conn.execute(text("INSERT INTO temperature_forecasts VALUES (:y, :s, :m, :mx, :mn, :dp, :fs, :sm, :to) ON CONFLICT DO NOTHING"), {
                "y": int(year), "s": int(sector_id), "m": int(r["Month"]), "mx": float(r["Max_Temp_C"]), "mn": float(r["Min_Temp_C"]),
                "dp": float(r["Departure_C"]), "fs": int(r["Fire_Stellium_Days"]), "sm": int(r["Sun_Mars_Agni_Days"]), "to": r["Thermal_Outlook"]
            })
    return df

_raw_wind12 = get_annual_wind_overview
def get_annual_wind_overview(year, sector_id=0):
    ensure_all_domain_tables()
    with engine.connect() as conn:
        df = pd.read_sql(text('SELECT month AS "Month", avg_wind_kmh AS "Avg_Wind_kmh", peak_wind_kmh AS "Peak_Wind_kmh", prevailing_direction AS "Prevailing_Direction", gusty_gale_days AS "Gusty_Gale_Days", calm_nowind_days AS "Calm_NoWind_Days" FROM wind_forecasts WHERE year = :y AND sector_id = :s ORDER BY month'), conn, params={"y": int(year), "s": int(sector_id)})
    if len(df) == 12:
        return df
    df = _raw_wind12(int(year), int(sector_id))
    with engine.begin() as conn:
        for _, r in df.iterrows():
            conn.execute(text("INSERT INTO wind_forecasts VALUES (:y, :s, :m, :aw, :pw, :pd, :gd, :cd) ON CONFLICT DO NOTHING"), {
                "y": int(year), "s": int(sector_id), "m": int(r["Month"]), "aw": float(r["Avg_Wind_kmh"]), "pw": float(r["Peak_Wind_kmh"]),
                "pd": r["Prevailing_Direction"], "gd": int(r["Gusty_Gale_Days"]), "cd": int(r["Calm_NoWind_Days"])
            })
    return df

_raw_analog = get_analog_years
def get_analog_years(target_year, top_n=5):
    ensure_all_domain_tables()
    with engine.connect() as conn:
        df = pd.read_sql(text('SELECT analog_year AS "Analog_Year", celestial_similarity_pct AS "Celestial_Similarity_pct", imd_actual_annual_mm AS "IMD_Actual_Annual_mm" FROM analog_year_matches WHERE target_year = :ty ORDER BY celestial_similarity_pct DESC LIMIT :n'), conn, params={"ty": int(target_year), "n": int(top_n)})
    if len(df) >= top_n:
        return df
    df = _raw_analog(int(target_year), int(top_n))
    with engine.begin() as conn:
        for _, r in df.iterrows():
            conn.execute(text("INSERT INTO analog_year_matches VALUES (:ty, :ay, :cs, :im) ON CONFLICT DO NOTHING"), {
                "ty": int(target_year), "ay": int(r["Analog_Year"]), "cs": float(r["Celestial_Similarity_pct"]), "im": float(r["IMD_Actual_Annual_mm"])
            })
    return df

_raw_backtest = get_historical_backtest
def get_historical_backtest(start_yr=1975, end_yr=2026):
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.model_selection import GroupKFold, cross_val_predict
    ensure_all_domain_tables()
    with engine.connect() as conn:
        df = pd.read_sql(text('SELECT year AS "Year", ardra_moon AS "Ardra_Moon", swati_moon AS "Swati_Moon", imd_actual_mm AS "IMD_Actual_mm", v6_insample_mm AS "V6_InSample_mm", insample_fit_pct AS "InSample_Fit_pct", v6_blind_oos_mm AS "V6_Blind_OOS_mm", blind_oos_acc_pct AS "Blind_OOS_Acc_pct", sw_acc_pct AS "SW_Acc_pct", thulavarsham_actual_mm AS "Thulavarsham_Actual_mm", thulavarsham_pred_mm AS "Thulavarsham_Pred_mm", thulavarsham_acc_pct AS "Thulavarsham_Acc_pct", summer_acc_pct AS "Summer_Acc_pct", winter_acc_pct AS "Winter_Acc_pct" FROM backtest_validation_history WHERE year BETWEEN :y1 AND :y2 ORDER BY year'), conn, params={"y1": int(start_yr), "y2": int(end_yr)})
    if len(df) >= (end_yr - start_yr + 1):
        return df
    df = _raw_backtest(int(start_yr), int(end_yr))
    with engine.begin() as conn:
        for _, r in df.iterrows():
            conn.execute(text("INSERT INTO backtest_validation_history VALUES (:y, :am, :sm, :ia, :vi, :ifp, :vb, :boa, :swa, :ta, :tp, :tap, :sua, :wia) ON CONFLICT DO NOTHING"), {
                "y": int(r["Year"]), "am": r["Ardra_Moon"], "sm": r["Swati_Moon"], "ia": float(r["IMD_Actual_mm"]),
                "vi": float(r["V6_InSample_mm"]), "ifp": float(r["InSample_Fit_pct"]), "vb": float(r["V6_Blind_OOS_mm"]),
                "boa": float(r["Blind_OOS_Acc_pct"]), "swa": float(r["SW_Acc_pct"]), "ta": float(r["Thulavarsham_Actual_mm"]),
                "tp": float(r["Thulavarsham_Pred_mm"]), "tap": float(r["Thulavarsham_Acc_pct"]), "sua": float(r["Summer_Acc_pct"]),
                "wia": float(r["Winter_Acc_pct"])
            })
    return df

def prepopulate_all_tables(start_yr=1975, end_yr=2035):
    ensure_all_domain_tables()
    # 1. Pre-populate 1975-2026 52-Year Validation History
    get_historical_backtest(1975, 2026)
    # 2. Pre-populate key historic case-study years + 2026-2035 across all tables & sectors
    target_years = sorted(list(set(list(range(2015, 2036)) + [1992, 2007])))
    for y in target_years:
        predict_and_cache_year(y)
        get_njattuvela_forecast(y)
        get_extreme_year_profile(y)
        get_analog_years(y, 5)
        for sid in range(0, 10):
            get_temperature_forecast(y, sid)
            get_annual_wind_overview(y, sid)
    return len(target_years)
