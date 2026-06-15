from passlib.hash import bcrypt

from scripts.add_dashboard_user import build_upsert_params


def test_build_upsert_params_includes_role():
    params = build_upsert_params("alice", "secret", "reviewer")
    assert params["username"] == "alice"
    assert params["role"] == "reviewer"
    assert bcrypt.verify("secret", params["password_hash"])


def test_build_upsert_params_defaults_to_viewer():
    params = build_upsert_params("alice", "secret")
    assert params["role"] == "viewer"
