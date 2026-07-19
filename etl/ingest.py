"""
ingest.py
---------
Synchronizes partner data from multiple legacy source systems (spreadsheet
CSV exports, a PHP-migrated contacts JSON, and a PoP reference file) into a
single SQLite warehouse. This stands in for the kind of multi-source ETL
this role runs against Hive/Presto-backed systems in production.

Run:
    python etl/ingest.py
"""
import csv
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "netpartner.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS partners (
    partner_id TEXT PRIMARY KEY,
    partner_name TEXT,
    partner_type TEXT,
    region TEXT,
    primary_pop TEXT,
    status TEXT,
    onboarded_date TEXT,
    renewal_date TEXT
);

CREATE TABLE IF NOT EXISTS contacts (
    contact_id TEXT PRIMARY KEY,
    partner_id TEXT,
    name TEXT,
    role TEXT,
    email TEXT,
    phone TEXT,
    last_verified TEXT,
    stale INTEGER,
    email_valid INTEGER
);

CREATE TABLE IF NOT EXISTS services (
    service_id TEXT PRIMARY KEY,
    partner_id TEXT,
    service_type TEXT,
    pop_code TEXT,
    sla_tier TEXT,
    expiry_date TEXT,
    annual_value_eur INTEGER
);

CREATE TABLE IF NOT EXISTS pops (
    code TEXT PRIMARY KEY,
    city TEXT,
    region TEXT
);
"""


def load_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    return conn


def ingest_partners(conn):
    rows = load_csv(DATA_DIR / "partners_legacy_export.csv")
    conn.executemany(
        """INSERT OR REPLACE INTO partners
           (partner_id, partner_name, partner_type, region, primary_pop,
            status, onboarded_date, renewal_date)
           VALUES (:partner_id, :partner_name, :partner_type, :region,
                   :primary_pop, :status, :onboarded_date, :renewal_date)""",
        rows,
    )
    return len(rows)


def ingest_contacts(conn):
    # prefer the PHP-normalized output if it exists; fall back to raw CSV
    clean_path = DATA_DIR / "contacts_clean.json"
    if clean_path.exists():
        payload = json.loads(clean_path.read_text())
        rows = payload["records"]
        conn.executemany(
            """INSERT OR REPLACE INTO contacts
               (contact_id, partner_id, name, role, email, phone,
                last_verified, stale, email_valid)
               VALUES (:contact_id, :partner_id, :name, :role, :email, :phone,
                       :last_verified, :stale, :email_valid)""",
            [{**r, "stale": int(r["stale"]), "email_valid": int(r["email_valid"])} for r in rows],
        )
    else:
        rows = load_csv(DATA_DIR / "contacts_wiki_dump.csv")
        conn.executemany(
            """INSERT OR REPLACE INTO contacts
               (contact_id, partner_id, name, role, email, phone, last_verified)
               VALUES (:contact_id, :partner_id, :name, :role, :email, :phone, :last_verified)""",
            rows,
        )
    return len(rows)


def ingest_services(conn):
    rows = load_csv(DATA_DIR / "services_spreadsheet.csv")
    conn.executemany(
        """INSERT OR REPLACE INTO services
           (service_id, partner_id, service_type, pop_code, sla_tier,
            expiry_date, annual_value_eur)
           VALUES (:service_id, :partner_id, :service_type, :pop_code,
                   :sla_tier, :expiry_date, :annual_value_eur)""",
        rows,
    )
    return len(rows)


def ingest_pops(conn):
    rows = json.loads((DATA_DIR / "pops_reference.json").read_text())
    conn.executemany(
        "INSERT OR REPLACE INTO pops (code, city, region) VALUES (:code, :city, :region)",
        rows,
    )
    return len(rows)


def run():
    conn = get_connection()
    n_partners = ingest_partners(conn)
    n_contacts = ingest_contacts(conn)
    n_services = ingest_services(conn)
    n_pops = ingest_pops(conn)
    conn.commit()
    conn.close()
    print(f"Ingested -> partners:{n_partners} contacts:{n_contacts} "
          f"services:{n_services} pops:{n_pops}  ({DB_PATH})")


if __name__ == "__main__":
    run()
