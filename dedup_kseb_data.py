import os
import glob
from sqlalchemy import text
from kseb_harvester import get_isolated_kseb_engine, init_kseb_tables, extract_date_from_filename

def cleanup_duplicates():
    eng, prefix = get_isolated_kseb_engine()
    init_kseb_tables(eng, prefix)

    with eng.begin() as c:
        # 1. Remove duplicate message_uid rows in email_ingest_log, keeping the earliest processed entry per report_date
        c.execute(text(f"""
            DELETE FROM {prefix}email_ingest_log
            WHERE message_uid NOT IN (
                SELECT MIN(message_uid)
                FROM {prefix}email_ingest_log
                GROUP BY report_date
            )
        """))

        # 2. Remove any duplicate rows in daily_power_summary by report_date (SQLite ctid/rowid safe)
        if prefix == "":
            c.execute(text("DELETE FROM daily_power_summary WHERE rowid NOT IN (SELECT MIN(rowid) FROM daily_power_summary GROUP BY report_date)"))
            c.execute(text("DELETE FROM reservoir_levels_inflow WHERE rowid NOT IN (SELECT MIN(rowid) FROM reservoir_levels_inflow GROUP BY report_date, reservoir_name)"))
            c.execute(text("DELETE FROM raw_energy_log_cells WHERE rowid NOT IN (SELECT MIN(rowid) FROM raw_energy_log_cells GROUP BY report_date, sheet_name, row_idx)"))
        else:
            c.execute(text(f"DELETE FROM {prefix}daily_power_summary a USING {prefix}daily_power_summary b WHERE a.ctid > b.ctid AND a.report_date = b.report_date"))
            c.execute(text(f"DELETE FROM {prefix}reservoir_levels_inflow a USING {prefix}reservoir_levels_inflow b WHERE a.ctid > b.ctid AND a.report_date = b.report_date AND a.reservoir_name = b.reservoir_name"))
            c.execute(text(f"DELETE FROM {prefix}raw_energy_log_cells a USING {prefix}raw_energy_log_cells b WHERE a.ctid > b.ctid AND a.report_date = b.report_date AND a.sheet_name = b.sheet_name AND a.row_idx = b.row_idx"))

        cnt_dates = c.execute(text(f"SELECT COUNT(*) FROM {prefix}daily_power_summary")).scalar()
        cnt_logs = c.execute(text(f"SELECT COUNT(*) FROM {prefix}email_ingest_log")).scalar()

    # 3. Remove duplicate downloaded .xls files representing the same report_date
    dl_dir = os.path.expanduser("~/kseb_telemetry_worker/downloads")
    seen_dates = set()
    removed_files = 0
    for fp in sorted(glob.glob(os.path.join(dl_dir, "*.xls*"))):
        rd = extract_date_from_filename(os.path.basename(fp))
        if rd:
            if rd in seen_dates:
                os.remove(fp)
                removed_files += 1
            else:
                seen_dates.add(rd)

    print(f"Deduplication complete: {cnt_dates} unique dates in DB | {cnt_logs} unique ingest logs | {removed_files} duplicate .xls files deleted.")

if __name__ == "__main__":
    cleanup_duplicates()
