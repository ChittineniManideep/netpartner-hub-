"""
graphql_api.py
--------------
GraphQL layer over the same warehouse, using strawberry-graphql. The JD
lists REST *and/or* GraphQL — this shows both, and GraphQL is a natural fit
for the partner/contact/service entity graph since callers usually want to
traverse relationships (e.g. "give me a partner and its contacts and
services in one query") rather than hit several REST endpoints.

Run:
    uvicorn api.graphql_api:app --reload --port 8001

Then browse http://localhost:8001/graphql for the interactive GraphiQL IDE.

Example query:
    query {
      partner(partnerId: "P1001") {
        partnerName
        partnerType
        contacts { name role email }
        services { serviceType expiryDate slaTier }
      }
    }
"""
import sqlite3
import sys
from pathlib import Path
from typing import List, Optional

import strawberry
from strawberry.fastapi import GraphQLRouter
from fastapi import FastAPI

ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))
DB_PATH = ROOT / "data" / "netpartner.db"


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@strawberry.type
class Contact:
    contact_id: str
    name: str
    role: str
    email: str
    phone: str


@strawberry.type
class Service:
    service_id: str
    service_type: str
    pop_code: str
    sla_tier: str
    expiry_date: str
    annual_value_eur: int


@strawberry.type
class Partner:
    partner_id: str
    partner_name: str
    partner_type: str
    region: str
    primary_pop: str
    status: str

    @strawberry.field
    def contacts(self) -> List[Contact]:
        conn = _db()
        rows = conn.execute(
            "SELECT * FROM contacts WHERE partner_id = ?", (self.partner_id,)
        ).fetchall()
        conn.close()
        return [Contact(contact_id=r["contact_id"], name=r["name"], role=r["role"],
                         email=r["email"], phone=r["phone"] or "") for r in rows]

    @strawberry.field
    def services(self) -> List[Service]:
        conn = _db()
        rows = conn.execute(
            "SELECT * FROM services WHERE partner_id = ?", (self.partner_id,)
        ).fetchall()
        conn.close()
        return [Service(service_id=r["service_id"], service_type=r["service_type"],
                         pop_code=r["pop_code"] or "", sla_tier=r["sla_tier"],
                         expiry_date=r["expiry_date"], annual_value_eur=r["annual_value_eur"])
                for r in rows]


def _partner_from_row(r) -> Partner:
    return Partner(partner_id=r["partner_id"], partner_name=r["partner_name"],
                    partner_type=r["partner_type"], region=r["region"],
                    primary_pop=r["primary_pop"] or "", status=r["status"])


@strawberry.type
class Query:
    @strawberry.field
    def partner(self, partner_id: str) -> Optional[Partner]:
        conn = _db()
        row = conn.execute("SELECT * FROM partners WHERE partner_id = ?", (partner_id,)).fetchone()
        conn.close()
        return _partner_from_row(row) if row else None

    @strawberry.field
    def partners(self, partner_type: Optional[str] = None, region: Optional[str] = None) -> List[Partner]:
        conn = _db()
        query = "SELECT * FROM partners WHERE 1=1"
        params = []
        if partner_type:
            query += " AND partner_type = ?"
            params.append(partner_type)
        if region:
            query += " AND region = ?"
            params.append(region)
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [_partner_from_row(r) for r in rows]


schema = strawberry.Schema(query=Query)
graphql_app = GraphQLRouter(schema)

app = FastAPI(title="NetPartner Hub GraphQL API")
app.include_router(graphql_app, prefix="/graphql")
