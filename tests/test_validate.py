"""
Basic tests for the data-quality module. Run with: pytest tests/
Assumes the DB has already been built (python scripts/seed_data.py && python etl/ingest.py).
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from etl.validate import run_all  # noqa: E402


def test_report_has_expected_keys():
    report = run_all()
    expected_keys = {
        "near_duplicate_partners", "orphaned_contacts", "orphaned_services",
        "partners_missing_renewal_date", "contacts_missing_phone",
        "services_expiring_30d", "stale_contacts",
    }
    assert expected_keys.issubset(report.keys())


def test_seeded_duplicate_is_caught():
    report = run_all()
    ids_flagged = {pair[0] for pair in report["near_duplicate_partners"]} | \
                  {pair[1] for pair in report["near_duplicate_partners"]}
    assert "P9999" in ids_flagged  # the intentionally injected duplicate


def test_seeded_orphan_contact_is_caught():
    report = run_all()
    orphan_ids = {c["contact_id"] for c in report["orphaned_contacts"]}
    assert "C9001" in orphan_ids


def test_missing_renewal_date_is_caught():
    report = run_all()
    assert len(report["partners_missing_renewal_date"]) >= 1
