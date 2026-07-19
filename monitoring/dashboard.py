"""
dashboard.py
------------
Generates a standalone HTML data-quality / platform-adoption dashboard from
the warehouse and validation report — the "dashboards tracking data
quality, freshness, and platform adoption" and "scheduled reports on
automation ROI and data integrity metrics" asks in the JD, without needing
a BI server running in this sandbox.

Run:
    python monitoring/dashboard.py
    open dashboard.html
"""
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))
DB_PATH = ROOT / "data" / "netpartner.db"
OUT_PATH = ROOT / "dashboard.html"

from etl.validate import run_all  # noqa: E402


def _counts_by(conn, table, column):
    return conn.execute(
        f"SELECT {column} AS k, COUNT(*) AS n FROM {table} GROUP BY {column} ORDER BY n DESC"
    ).fetchall()


def _bar_rows(rows, max_width=240):
    if not rows:
        return "<p class='muted'>No data</p>"
    max_n = max(r["n"] for r in rows) or 1
    out = []
    for r in rows:
        width = int((r["n"] / max_n) * max_width) or 4
        out.append(
            f"<div class='bar-row'><span class='bar-label'>{r['k']}</span>"
            f"<span class='bar' style='width:{width}px'></span>"
            f"<span class='bar-value'>{r['n']}</span></div>"
        )
    return "".join(out)


def build_dashboard():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    n_partners = conn.execute("SELECT COUNT(*) n FROM partners").fetchone()["n"]
    n_contacts = conn.execute("SELECT COUNT(*) n FROM contacts").fetchone()["n"]
    n_services = conn.execute("SELECT COUNT(*) n FROM services").fetchone()["n"]
    total_value = conn.execute("SELECT SUM(annual_value_eur) v FROM services").fetchone()["v"] or 0

    by_type = _counts_by(conn, "partners", "partner_type")
    by_region = _counts_by(conn, "partners", "region")
    by_status = _counts_by(conn, "partners", "status")

    report = run_all()
    dq_summary = {k: len(v) for k, v in report.items()}
    total_issues = sum(dq_summary.values())
    quality_score = max(0, 100 - min(100, total_issues * 3))

    conn.close()

    dq_rows = "".join(
        f"<tr><td>{k.replace('_', ' ').title()}</td><td class='num'>{v}</td></tr>"
        for k, v in dq_summary.items()
    )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>NetPartner Hub — Platform Dashboard</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; background:#0f1216; color:#e6e9ef; margin:0; padding:32px; }}
  h1 {{ font-size:22px; margin-bottom:4px; }}
  .muted {{ color:#8b93a1; font-size:13px; }}
  .cards {{ display:flex; gap:16px; margin:24px 0; flex-wrap:wrap; }}
  .card {{ background:#171b21; border:1px solid #2a2f38; border-radius:10px; padding:18px 22px; min-width:160px; }}
  .card .n {{ font-size:28px; font-weight:600; }}
  .card .label {{ color:#8b93a1; font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
  .score {{ color: {"#5fd67d" if quality_score >= 80 else "#e8b34a" if quality_score >= 60 else "#e0625a"}; }}
  .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:24px; margin-top:24px; }}
  .panel {{ background:#171b21; border:1px solid #2a2f38; border-radius:10px; padding:18px 22px; }}
  .panel h2 {{ font-size:14px; text-transform:uppercase; letter-spacing:.04em; color:#8b93a1; margin-top:0; }}
  .bar-row {{ display:flex; align-items:center; gap:10px; margin:6px 0; font-size:13px; }}
  .bar-label {{ width:130px; }}
  .bar {{ background:#4c7cf0; height:10px; border-radius:4px; display:inline-block; }}
  .bar-value {{ color:#8b93a1; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  td {{ padding:6px 4px; border-bottom:1px solid #22262e; }}
  td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  footer {{ margin-top:32px; color:#57606f; font-size:12px; }}
</style></head>
<body>
  <h1>NetPartner Hub — Platform Dashboard</h1>
  <p class="muted">Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>

  <div class="cards">
    <div class="card"><div class="n">{n_partners}</div><div class="label">Partners</div></div>
    <div class="card"><div class="n">{n_contacts}</div><div class="label">Contacts</div></div>
    <div class="card"><div class="n">{n_services}</div><div class="label">Active Services</div></div>
    <div class="card"><div class="n">€{total_value:,.0f}</div><div class="label">Annual Service Value</div></div>
    <div class="card"><div class="n score">{quality_score}</div><div class="label">Data Quality Score</div></div>
  </div>

  <div class="grid">
    <div class="panel">
      <h2>Partners by Type</h2>
      {_bar_rows(by_type)}
    </div>
    <div class="panel">
      <h2>Partners by Region</h2>
      {_bar_rows(by_region)}
    </div>
    <div class="panel">
      <h2>Partners by Status</h2>
      {_bar_rows(by_status)}
    </div>
    <div class="panel">
      <h2>Data Quality Findings</h2>
      <table>{dq_rows}</table>
    </div>
  </div>

  <footer>NetPartner Hub · automated health-check + ETL portfolio project</footer>
</body></html>"""

    OUT_PATH.write_text(html)
    print(f"Dashboard written -> {OUT_PATH}")


if __name__ == "__main__":
    build_dashboard()
