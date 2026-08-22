from __future__ import annotations
import importlib


def module(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENSCANSTATION_DATA_DIR", str(tmp_path))
    import openscanstation.users as users
    return importlib.reload(users)


def test_user_authentication_and_public_output(tmp_path, monkeypatch):
    users = module(tmp_path, monkeypatch)
    public = users.upsert_user("admin", "long-password", role="admin", display_name="Administrator")
    assert "password_hash" not in public
    assert users.authenticate("admin", "long-password")["role"] == "admin"
    assert users.authenticate("admin", "wrong-password") is None


def test_signed_session_detects_tampering(tmp_path, monkeypatch):
    users = module(tmp_path, monkeypatch)
    account = users.upsert_user("markus", "long-password", role="user")
    token = users.create_session(account)
    assert users.verify_session(token)["username"] == "markus"
    assert users.verify_session(token + "x") is None


def test_last_admin_cannot_be_deleted(tmp_path, monkeypatch):
    users = module(tmp_path, monkeypatch)
    users.upsert_user("admin", "long-password", role="admin")
    try:
        users.delete_user("admin")
    except ValueError as exc:
        assert "Administrator" in str(exc)
    else:
        raise AssertionError("last admin deleted")


def test_user_can_select_scanners(tmp_path, monkeypatch):
    users = module(tmp_path, monkeypatch)
    users.upsert_user("markus", "long-password", role="user")
    result = users.set_scanners("markus", ["scanner-1", "scanner-1", "scanner-2"])
    assert result["scanners"] == ["scanner-1", "scanner-2"]
