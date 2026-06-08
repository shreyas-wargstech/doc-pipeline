from passlib.hash import bcrypt

from scripts.add_dashboard_user import build_upsert_params


def test_build_upsert_params_hashes_password():
    params = build_upsert_params("alice", "s3cret")
    assert params["username"] == "alice"
    assert bcrypt.verify("s3cret", params["password_hash"])
    assert not bcrypt.verify("wrong", params["password_hash"])
