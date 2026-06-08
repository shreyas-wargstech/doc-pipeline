"""Guards the locked Neo4j constraint set (no live DB needed)."""
from __future__ import annotations

from shared.neo4j_client import CONSTRAINTS, DROP_CONSTRAINTS


def _joined():
    return " ".join(CONSTRAINTS + DROP_CONSTRAINTS)


def test_person_keyed_on_registration_no():
    j = _joined()
    assert "Person) REQUIRE p.registration_no IS UNIQUE" in j
    # old composite key is gone from the create set...
    assert "p.name, p.dob" not in " ".join(CONSTRAINTS)
    # ...and explicitly dropped for migration
    assert "DROP CONSTRAINT person_natural_key IF EXISTS" in " ".join(DROP_CONSTRAINTS)


def test_org_vendor_reference_constraints_present():
    j = " ".join(CONSTRAINTS)
    assert "Organization) REQUIRE o.name IS UNIQUE" in j
    assert "Vendor) REQUIRE v.name IS UNIQUE" in j
    assert "ReferenceRecord) REQUIRE r.registration_no IS UNIQUE" in j
