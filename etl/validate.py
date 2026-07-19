"""
validate.py
-----------
Data quality checks against the warehouse: duplicate detection, missing
required fields, orphaned records (contacts/services pointing at partners
that don't exist), and stale renewal/expiry dates. This is the kind of
validation layer the JD calls out under "data quality principles" and
"automated health checks / audit scripts".

Run:
    python etl/validate.py
"""
import sqlite3
from datetime import date, datetime
from pathlib import Path
from difflib import SequenceMatcher

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "netpartner.db"


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def find_near_duplicate_partners(conn, threshold=0.9):
    """Legacy exports often have the same partner entered twice with
    different casing/whitespace/IDs. Flag likely duplicates by name
    similarity rather than exact match."""
    rows = conn.execute("SELECT partner_id, partner_name FROM partners").fetchall()
    normed = [(r["partner_id"], " ".join(r["partner_name"].split()).lower()) for r in rows]
    dupes = []
    for i in range(len(normed)):
        for j in range(i + 1, len(normed)):
            id_a, name_a = normed[i]
            id_b, name_b = normed[j]
            ratio = SequenceMatcher(None, name_a, name_b).ratio()
            if ratio >= threshold:
                dupes.append((id_a, id_b, round(ratio, 3)))
    return dupes


def find_orphaned_records(conn):
    orphan_contacts = conn.execute("""
        SELECT c.contact_id, c.partner_id FROM contacts c
        LEFT JOIN partners p ON c.partner_id = p.partner_id
        WHERE p.partner_id IS NULL
    """).fetchall()
    orphan_services = conn.execute("""
        SELECT s.service_id, s.partner_id FROM services s
        LEFT JOIN partners p ON s.partner_id = p.partner_id
        WHERE p.partner_id IS NULL
    """).fetchall()
    return orphan_contacts, orphan_services


def find_missing_required_fields(conn):
    missing_renewal = conn.execute(
        "SELECT partner_id, partner_name FROM partners WHERE renewal_date IS NULL OR renewal_date = ''"
    ).fetchall()
    missing_phone = conn.execute(
        "SELECT contact_id, partner_id FROM contacts WHERE phone IS NULL OR phone = ''"
    ).fetchall()
    return missing_renewal, missing_phone


def find_stale_or_expiring(conn, days_horizon=30):
    today = date.today().isoformat()
    expiring_services = conn.execute(
        """SELECT service_id, partner_id, service_type, expiry_date FROM services
           WHERE expiry_date <= date(?, ?)""",
        (today, f"+{days_horizon} days"),
    ).fetchall()
    stale_contacts = conn.execute(
        "SELECT contact_id, partner_id, last_verified FROM contacts WHERE stale = 1"
    ).fetchall()
    return expiring_services, stale_contacts


def run_all():
    conn = _connect()
    report = {}

    dupes = find_near_duplicate_partners(conn)
    report["near_duplicate_partners"] = dupes

    orphan_contacts, orphan_services = find_orphaned_records(conn)
    report["orphaned_contacts"] = [dict(r) for r in orphan_contacts]
    report["orphaned_services"] = [dict(r) for r in orphan_services]

    missing_renewal, missing_phone = find_missing_required_fields(conn)
    report["partners_missing_renewal_date"] = [dict(r) for r in missing_renewal]
    report["contacts_missing_phone"] = [dict(r) for r in missing_phone]

    expiring, stale = find_stale_or_expiring(conn)
    report["services_expiring_30d"] = [dict(r) for r in expiring]
    report["stale_contacts"] = [dict(r) for r in stale]

    conn.close()
    return report


def print_report(report):
    print("=== Data Quality Report ===")
    print(f"Near-duplicate partners:      {len(report['near_duplicate_partners'])}")
    for a, b, score in report["near_duplicate_partners"]:
        print(f"   {a} <-> {b}  (similarity {score})")
    print(f"Orphaned contacts:             {len(report['orphaned_contacts'])}")
    print(f"Orphaned services:             {len(report['orphaned_services'])}")
    print(f"Partners missing renewal date: {len(report['partners_missing_renewal_date'])}")
    print(f"Contacts missing phone:        {len(report['contacts_missing_phone'])}")
    print(f"Services expiring in 30 days:  {len(report['services_expiring_30d'])}")
    print(f"Stale contacts (>180d):        {len(report['stale_contacts'])}")


if __name__ == "__main__":
    print_report(run_all())
