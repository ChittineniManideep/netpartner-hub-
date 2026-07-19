"""
seed_data.py
------------
Generates synthetic "legacy" partner data the way it would realistically show
up before a centralization project: a messy CSV export from a spreadsheet,
an old wiki-style contacts dump, and a services table with some intentional
data-quality problems (duplicates, stale renewal dates, missing fields).

Domain: network partner ecosystem — ISPs, colocation facilities, hardware
vendors, and managed service providers (MSPs), each tied to one or more
Points of Presence (PoPs) and peering relationships.

Run:
    python scripts/seed_data.py
"""
import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(42)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

PARTNER_TYPES = ["ISP", "Colocation", "Hardware Vendor", "MSP"]
REGIONS = ["EMEA", "AMER", "APAC"]
POPS = [
    ("LHR1", "London", "EMEA"), ("DUB1", "Dublin", "EMEA"),
    ("FRA2", "Frankfurt", "EMEA"), ("AMS3", "Amsterdam", "EMEA"),
    ("JFK1", "New York", "AMER"), ("ORD2", "Chicago", "AMER"),
    ("SIN1", "Singapore", "APAC"), ("NRT2", "Tokyo", "APAC"),
]

PARTNER_NAMES = {
    "ISP": ["Meridian Networks", "Vantage Fiber", "NorthBridge Connect", "Halcyon IP Transit",
            "Coastal Peering Co", "Arcline Telecom"],
    "Colocation": ["Redstone DC", "Ironwood Colo", "Beacon Data Centers", "Granite Peering Hub",
                   "Lakeside Colocation"],
    "Hardware Vendor": ["Crestpoint Systems", "Wavefront Networking", "Solstice Hardware",
                         "Talon Optics"],
    "MSP": ["Pinnacle Managed IT", "Clearview Ops", "Fieldstone MSP", "Trueline Support"],
}

STATUSES = ["Active", "Active", "Active", "Pending Onboarding", "Under Review"]


def _rand_date(start_days_ago=900, end_days_future=400):
    delta = random.randint(-start_days_ago, end_days_future)
    return date.today() + timedelta(days=delta)


def gen_partners(n_per_type=6):
    rows = []
    pid = 1000
    for ptype, names in PARTNER_NAMES.items():
        for name in names[:n_per_type]:
            pid += 1
            pop = random.choice(POPS)
            row = {
                "partner_id": f"P{pid}",
                "partner_name": name,
                "partner_type": ptype,
                "region": pop[2],
                "primary_pop": pop[0],
                "status": random.choice(STATUSES),
                "onboarded_date": str(_rand_date(700, -30)),
                "renewal_date": str(_rand_date(-200, 300)),
            }
            rows.append(row)
    # inject a duplicate (slightly different casing/whitespace) — realistic legacy mess
    dup = dict(rows[3])
    dup["partner_id"] = "P9999"
    dup["partner_name"] = dup["partner_name"].upper() + "  "
    rows.append(dup)
    # inject a partner with a missing renewal date (data quality gap)
    rows[7]["renewal_date"] = ""
    return rows


def gen_contacts(partners):
    rows = []
    cid = 500
    roles = ["Account Manager", "NOC Escalation", "Billing Contact", "Technical Lead"]
    for p in partners:
        n_contacts = random.randint(1, 3)
        for _ in range(n_contacts):
            cid += 1
            rows.append({
                "contact_id": f"C{cid}",
                "partner_id": p["partner_id"],
                "name": f"Contact {cid}",
                "role": random.choice(roles),
                "email": f"contact{cid}@{p['partner_name'].split()[0].lower()}.example.com",
                "phone": f"+353-1-{random.randint(1000000,9999999)}" if random.random() > 0.15 else "",
                "last_verified": str(_rand_date(400, 0)),
            })
    # a couple of orphaned contacts (partner_id no longer exists) — legacy cleanup case
    rows.append({"contact_id": "C9001", "partner_id": "P0000", "name": "Orphan Contact",
                 "role": "Billing Contact", "email": "orphan@example.com", "phone": "",
                 "last_verified": str(_rand_date(1200, -600))})
    return rows


def gen_services(partners):
    rows = []
    sid = 200
    svc_types = ["IP Transit", "Cross-Connect", "Managed Firewall", "Hardware Maintenance",
                 "Peering Agreement", "Colo Rack Space"]
    for p in partners:
        for _ in range(random.randint(1, 2)):
            sid += 1
            rows.append({
                "service_id": f"S{sid}",
                "partner_id": p["partner_id"],
                "service_type": random.choice(svc_types),
                "pop_code": p["primary_pop"],
                "sla_tier": random.choice(["Gold", "Silver", "Bronze"]),
                "expiry_date": str(_rand_date(-60, 250)),
                "annual_value_eur": random.randint(15000, 250000),
            })
    return rows


def write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    partners = gen_partners()
    contacts = gen_contacts(partners)
    services = gen_services(partners)

    write_csv(DATA_DIR / "partners_legacy_export.csv", partners)
    write_csv(DATA_DIR / "contacts_wiki_dump.csv", contacts)
    write_csv(DATA_DIR / "services_spreadsheet.csv", services)

    with open(DATA_DIR / "pops_reference.json", "w") as f:
        json.dump([{"code": c, "city": city, "region": r} for c, city, r in POPS], f, indent=2)

    print(f"Generated {len(partners)} partners, {len(contacts)} contacts, "
          f"{len(services)} services -> {DATA_DIR}")
