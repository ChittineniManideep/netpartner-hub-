# NetPartner Hub

A working prototype of a centralized **network partner data platform** —
the kind of system that manages ISPs, colocation facilities, hardware
vendors, and MSPs, their contacts, and their service agreements in one
place, with automation on top for onboarding, alerting, and incident
response.

Built as a portfolio project targeting an Automation Engineer role focused
on exactly this kind of platform. It's deliberately scoped to demonstrate
the parts of the stack I hadn't touched before applying — see the mapping
table below.

## What it does

1. **Migrates messy legacy data** — a PHP script normalizes a "wiki dump"
   style contacts export (whitespace, casing, email/phone validation,
   staleness flags).
2. **Ingests multiple source systems** into a single SQLite warehouse
   (spreadsheet CSVs, the PHP-cleaned JSON, a PoP reference file) — a
   stand-in for the Hive/Presto multi-source sync described in the JD.
3. **Runs automated data-quality checks**: near-duplicate partner
   detection (fuzzy name matching), orphaned contacts/services, missing
   required fields, stale contacts, and expiring service agreements.
4. **Models the partner ecosystem as a graph** (partners, contacts,
   services, PoPs as nodes; ownership/location/delivery as edges) using
   `networkx`, and uses graph traversal to answer the operational
   question that matters during an incident: *"who do I call?"*
5. **Exposes both REST and GraphQL APIs** over the same data — REST for
   simple CRUD/self-service operations, GraphQL for relationship-heavy
   queries (partner → contacts → services in one round trip).
6. **Orchestrates the whole pipeline as an Airflow DAG** with branching
   alert logic (only fires an alert task if the quality audit finds
   issues).
7. **Publishes a data-quality dashboard** as a standalone HTML report
   (partner counts by type/region/status, service value, and a live
   findings table).

## Architecture

```
legacy_migration/migrate_contacts.php   PHP: normalize legacy contact dump
              |
              v
etl/ingest.py                            Python: multi-source -> SQLite warehouse
              |
              v
etl/validate.py                          Data quality audit (dedup, orphans, staleness)
              |
      +-------+-------+
      v               v
graph/partner_graph.py       api/rest_api.py, api/graphql_api.py
(networkx entity graph,      (FastAPI + Strawberry — self-service
 incident contact lookup)     query layer over warehouse + graph)
      |
      v
monitoring/dashboard.py                  HTML data-quality / adoption dashboard
      |
      v
orchestration/netpartner_dag.py          Airflow DAG tying all of the above together
```

## Mapping to the job requirements

| JD requirement | Where it's covered |
|---|---|
| Python — scripting, API integrations, data manipulation | Entire `etl/`, `graph/`, `api/`, `monitoring/` |
| REST and/or GraphQL APIs | `api/rest_api.py` (FastAPI) and `api/graphql_api.py` (Strawberry) |
| SQL / ETL pipeline concepts | `etl/ingest.py`, SQLite warehouse schema |
| Airflow / job scheduling / orchestration | `orchestration/netpartner_dag.py` — daily DAG with branching alert logic |
| Data quality — validation, dedup, reconciliation | `etl/validate.py` — fuzzy dedup, orphan detection, missing-field checks |
| Automated alerting for stale/missing data | `orchestration/netpartner_dag.py` (`alert_on_findings` task), `validate.py` staleness checks |
| Auto-retrieve partner contacts during incidents | `graph/partner_graph.py::incident_contacts()`, exposed via `/incidents/{pop}/contacts` |
| Dashboards tracking data quality & adoption | `monitoring/dashboard.py` |
| **PHP/Hack (server-side scripting)** *(gap)* | `legacy_migration/migrate_contacts.php` — legacy data normalization |
| **Graph databases / entity management** *(gap)* | `graph/partner_graph.py` — networkx property graph modeling partners/contacts/services/PoPs as nodes and relations as typed edges |
| **Network infrastructure concepts** *(gap)* | Domain model built around ISPs, colocation, hardware vendors, MSPs, PoPs, and peering-style service types throughout the seed data and schema |
| **CRM / vendor management concepts** *(gap)* | `partner_footprint()` and `/partners/{id}` endpoint — the kind of 360° vendor view a vendor-management platform provides |
| Thrift / RPC frameworks *(gap, not covered)* | Not implemented — REST + GraphQL cover the API surface instead; happy to pick this up on the job |

I'm upfront that Thrift and hands-on telecom/peering experience are real
gaps this project narrows but doesn't fully close — the rest of the stack
(Python, SQL, ETL, orchestration, data quality, graph modeling, REST/GraphQL,
even a PHP legacy-data step) is built and tested end to end.

## Running it

```bash
pip install -r requirements.txt

# 1. Generate synthetic "legacy" partner data
python scripts/seed_data.py

# 2. Normalize the legacy contacts dump (PHP)
php legacy_migration/migrate_contacts.php data/contacts_wiki_dump.csv data/contacts_clean.json

# 3. Ingest everything into the warehouse
python etl/ingest.py

# 4. Run the data quality audit
python etl/validate.py

# 5. Query the partner graph directly
python graph/partner_graph.py DUB1              # who do I call for an incident at DUB1?
python graph/partner_graph.py --partner P1001    # full footprint for one partner

# 6. Bring up the APIs
uvicorn api.rest_api:app --reload --port 8000       # http://localhost:8000/docs
uvicorn api.graphql_api:app --reload --port 8001    # http://localhost:8001/graphql

# 7. Build the dashboard
python monitoring/dashboard.py   # writes dashboard.html

# 8. Tests
pytest tests/
```

`orchestration/netpartner_dag.py` is a standard Airflow 2.x DAG — drop it
into `$AIRFLOW_HOME/dags` to run the whole pipeline on a schedule with
branching alerts. Airflow itself isn't required to run steps 1–8 above.

## Tech stack

Python (ETL, graph modeling, APIs, dashboarding) · PHP (legacy data
migration) · SQLite (warehouse) · FastAPI + Strawberry GraphQL (API layer)
· networkx (entity graph) · Airflow (orchestration) · pytest (tests)

## Notes on the synthetic data

`scripts/seed_data.py` generates realistic-looking partner data with
intentionally injected data-quality problems (a near-duplicate partner
record, an orphaned contact, a missing renewal date) so the validation
logic has something real to catch — see `tests/test_validate.py`, which
asserts each of those seeded issues is actually detected.
