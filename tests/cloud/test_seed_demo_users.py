from passlib.hash import bcrypt

from scripts.seed_demo_users import DEMO_USERNAMES, build_demo_rows


def test_build_demo_rows_covers_all_users_with_valid_hashes():
    rows = build_demo_rows("pw")
    assert [r["username"] for r in rows] == list(DEMO_USERNAMES)
    assert all(bcrypt.verify("pw", r["password_hash"]) for r in rows)
    assert not bcrypt.verify("wrong", rows[0]["password_hash"])
