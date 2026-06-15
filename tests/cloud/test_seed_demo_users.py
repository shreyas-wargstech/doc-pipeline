from passlib.hash import bcrypt

from scripts.seed_demo_users import DEMO_USERS, build_demo_rows


def test_build_demo_rows_covers_all_users_with_valid_hashes():
    rows = build_demo_rows("pw")
    assert [r["username"] for r in rows] == [u["username"] for u in DEMO_USERS]
    assert all(bcrypt.verify("pw", r["password_hash"]) for r in rows)
    assert not bcrypt.verify("wrong", rows[0]["password_hash"])


def test_build_demo_rows_includes_roles():
    rows = build_demo_rows("pw")
    assert [r["role"] for r in rows] == [u["role"] for u in DEMO_USERS]
    assert rows[0]["role"] == "administrator"
    assert rows[1]["role"] == "reviewer"
    assert rows[2]["role"] == "operator"
    assert rows[3]["role"] == "viewer"
