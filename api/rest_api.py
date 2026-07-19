"""
rest_api.py
-----------
REST API exposing the partner warehouse and graph — the kind of self-service
layer operations teams would use for bulk lookups without engineering
support, and the integration surface other internal systems would call.

Run:
    uvicorn api.rest_api:app --reload --port 8000

Then browse http://localhost:8000/docs for interactive OpenAPI docs.
"""
import sqlite3
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))
DB_PATH = ROOT / "data" / "netpartner.db"

from graph.partner_graph import build_graph, incident_contacts, partner_footprint  # noqa: E402
from etl.validate import run_all as run_validation  # noqa: E402

app = FastAPI(
    title="NetPartner Hub API",
    description="Centralized network partner data platform — partners, contacts, "
                 "services, PoPs, incident contact lookup, and data quality reporting.",
    version="0.1.0",
)


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


class ServiceRenewal(BaseModel):
    service_id: str
    new_expiry_date: str


@app.get("/partners")
def list_partners(partner_type: str | None = None, region: str | None = None, status: str | None = None):
    conn = _db()
    query = "SELECT * FROM partners WHERE 1=1"
    params = []
    if partner_type:
        query += " AND partner_type = ?"
        params.append(partner_type)
    if region:
        query += " AND region = ?"
        params.append(region)
    if status:
        query += " AND status = ?"
        params.append(status)
    rows = [dict(r) for r in conn.execute(query, params)]
    conn.close()
    return {"count": len(rows), "partners": rows}


@app.get("/partners/{partner_id}")
def get_partner_footprint(partner_id: str):
    g = build_graph()
    fp = partner_footprint(g, partner_id)
    if fp is None:
        raise HTTPException(status_code=404, detail="Partner not found")
    return fp


@app.get("/incidents/{pop_code}/contacts")
def get_incident_contacts(pop_code: str):
    """Self-service tool: given a PoP experiencing a network incident,
    return the affected partners and their ranked escalation contacts."""
    g = build_graph()
    result = incident_contacts(g, pop_code)
    if not result:
        raise HTTPException(status_code=404, detail="No partners found for this PoP")
    return {"pop_code": pop_code, "affected_partners": result}


@app.get("/data-quality/report")
def data_quality_report():
    """Automated health check endpoint — duplicates, orphans, missing
    fields, staleness, expiring services."""
    report = run_validation()
    summary = {k: len(v) for k, v in report.items()}
    return {"summary": summary, "detail": report}


@app.post("/services/renew")
def renew_service(payload: ServiceRenewal):
    """Bulk-friendly self-service endpoint: operations teams update a
    service's renewal date without needing engineering support."""
    conn = _db()
    cur = conn.execute(
        "UPDATE services SET expiry_date = ? WHERE service_id = ?",
        (payload.new_expiry_date, payload.service_id),
    )
    conn.commit()
    updated = cur.rowcount
    conn.close()
    if not updated:
        raise HTTPException(status_code=404, detail="Service not found")
    return {"service_id": payload.service_id, "new_expiry_date": payload.new_expiry_date, "updated": True}


@app.get("/health")
def health():
    return {"status": "ok"}
