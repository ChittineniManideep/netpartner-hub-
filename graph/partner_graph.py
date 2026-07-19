"""
partner_graph.py
-----------------
Models the partner ecosystem as a property graph (partners, contacts,
services, and PoPs as nodes; ownership/location/delivery relationships as
edges) using networkx as an in-process stand-in for a graph database like
Neo4j or Amazon Neptune.

This directly supports two JD asks:
  1. "Familiarity with graph databases or relationship/entity management
     systems" — the entity model itself.
  2. "Build tools that auto-retrieve relevant partner contacts during
     network incidents" — the incident_contacts() traversal below.

Run:
    python graph/partner_graph.py DUB1        # incident at PoP DUB1
    python graph/partner_graph.py --partner P1001
"""
import sqlite3
import sys
from pathlib import Path

import networkx as nx

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "netpartner.db"


def build_graph():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    g = nx.MultiDiGraph()

    for pop in conn.execute("SELECT * FROM pops"):
        g.add_node(f"pop:{pop['code']}", kind="PoP", city=pop["city"], region=pop["region"])

    for p in conn.execute("SELECT * FROM partners"):
        node = f"partner:{p['partner_id']}"
        g.add_node(node, kind="Partner", name=p["partner_name"], type=p["partner_type"],
                   status=p["status"], region=p["region"])
        if p["primary_pop"]:
            g.add_edge(node, f"pop:{p['primary_pop']}", relation="LOCATED_AT")

    for c in conn.execute("SELECT * FROM contacts"):
        node = f"contact:{c['contact_id']}"
        g.add_node(node, kind="Contact", name=c["name"], role=c["role"], email=c["email"],
                   phone=c["phone"], stale=bool(c["stale"]) if c["stale"] is not None else None)
        g.add_edge(node, f"partner:{c['partner_id']}", relation="POINT_OF_CONTACT_FOR")

    for s in conn.execute("SELECT * FROM services"):
        node = f"service:{s['service_id']}"
        g.add_node(node, kind="Service", type=s["service_type"], sla=s["sla_tier"],
                   expiry=s["expiry_date"], value=s["annual_value_eur"])
        g.add_edge(node, f"partner:{s['partner_id']}", relation="DELIVERED_BY")
        if s["pop_code"]:
            g.add_edge(node, f"pop:{s['pop_code']}", relation="DELIVERED_AT")

    conn.close()
    return g


def incident_contacts(g, pop_code, roles_priority=("NOC Escalation", "Technical Lead", "Account Manager")):
    """Given a PoP code experiencing an incident, walk the graph to find every
    partner delivering services there and rank their contacts by escalation
    priority. This is the automated 'who do I call' lookup the JD asks for."""
    pop_node = f"pop:{pop_code}"
    if pop_node not in g:
        return []

    # services delivered at this PoP -> their partners
    affected_partners = set()
    for service_node in g.predecessors(pop_node):
        if g.nodes[service_node].get("kind") != "Service":
            continue
        for _, partner_node, data in g.out_edges(service_node, data=True):
            if data.get("relation") == "DELIVERED_BY":
                affected_partners.add(partner_node)
    # also include the partner whose primary PoP this is
    for partner_node, _, data in g.in_edges(pop_node, data=True):
        if data.get("relation") == "LOCATED_AT":
            affected_partners.add(partner_node)

    results = []
    for partner_node in affected_partners:
        partner = g.nodes[partner_node]
        contacts = []
        for contact_node in g.predecessors(partner_node):
            if g.nodes[contact_node].get("kind") != "Contact":
                continue
            contacts.append({**g.nodes[contact_node], "node": contact_node})

        def rank(c):
            try:
                return roles_priority.index(c["role"])
            except ValueError:
                return len(roles_priority)

        contacts.sort(key=rank)
        results.append({
            "partner": partner["name"],
            "partner_type": partner["type"],
            "status": partner["status"],
            "contacts": contacts,
        })
    return results


def partner_footprint(g, partner_id):
    """All services, PoPs, and contacts attached to one partner — useful for
    onboarding review or vendor-management style lookups."""
    node = f"partner:{partner_id}"
    if node not in g:
        return None
    footprint = {"partner": g.nodes[node], "services": [], "contacts": [], "pops": set()}
    for pred in g.predecessors(node):
        kind = g.nodes[pred].get("kind")
        if kind == "Contact":
            footprint["contacts"].append(g.nodes[pred])
        elif kind == "Service":
            footprint["services"].append(g.nodes[pred])
    for _, succ, data in g.out_edges(node, data=True):
        if data.get("relation") == "LOCATED_AT":
            footprint["pops"].add(succ.replace("pop:", ""))
    footprint["pops"] = list(footprint["pops"])
    return footprint


if __name__ == "__main__":
    g = build_graph()
    print(f"Graph built: {g.number_of_nodes()} nodes, {g.number_of_edges()} edges")

    args = sys.argv[1:]
    if args and args[0] == "--partner":
        fp = partner_footprint(g, args[1])
        print(f"\nFootprint for {args[1]}:")
        print(f"  Partner: {fp['partner']['name']} ({fp['partner']['type']})")
        print(f"  PoPs: {fp['pops']}")
        print(f"  Services: {len(fp['services'])}, Contacts: {len(fp['contacts'])}")
    elif args:
        pop = args[0]
        print(f"\nIncident at {pop} -- affected partners & escalation contacts:")
        for entry in incident_contacts(g, pop):
            print(f"\n  {entry['partner']} ({entry['partner_type']}, {entry['status']})")
            for c in entry["contacts"][:3]:
                print(f"    - {c['role']}: {c['name']} | {c['email']} | {c['phone'] or 'no phone on file'}")
    else:
        print("Usage: python partner_graph.py <POP_CODE> | --partner <PARTNER_ID>")
