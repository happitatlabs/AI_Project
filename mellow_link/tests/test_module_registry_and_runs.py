import uuid

import pytest

try:
    from fastapi.testclient import TestClient
    _has_fastapi = True
except ImportError:
    _has_fastapi = False

_app = None
_skip_reason = None


def _get_app():
    global _app, _skip_reason
    if _app is not None:
        return _app
    if _skip_reason is not None:
        return None
    if not _has_fastapi:
        _skip_reason = "FastAPI/testclient not installed"
        return None
    try:
        from mellow_link.main import app
        _app = app
        return _app
    except Exception as e:
        _skip_reason = f"Could not import app: {e}"
        return None


@pytest.fixture(scope="module")
def client():
    app = _get_app()
    if app is None:
        pytest.skip(_skip_reason or "FastAPI app not available")
    return TestClient(app)


def _user_headers():
    from mellow_link.infra.database import SessionLocal
    from mellow_link.infra import User, UserRole, create_default_folders_for_user, create_access_token

    username = f"mod_{uuid.uuid4().hex[:8]}"
    with SessionLocal() as db:
        user = User(username=username, hashed_password="test-hash", role=UserRole.USER.value)
        db.add(user)
        db.commit()
        db.refresh(user)
        create_default_folders_for_user(db, user.id, role=UserRole.USER.value)
        token = create_access_token(data={"sub": username}, role=user.role)
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def test_modules_api_lists_registered_modules(client):
    res = client.get("/api/modules")
    assert res.status_code == 200
    modules = res.json()["modules"]
    ids = {m["module_id"] for m in modules}
    assert {"sql_analytics", "research_assistant", "ai_workflow_console"}.issubset(ids)


def test_sql_analytics_run_has_module_metadata(client):
    headers = _user_headers()
    res = client.post(
        "/modules/sql_analytics/runs",
        headers={**headers, "Content-Type": "application/json"},
        json={"question": "지난 7일 환불률을 알려줘"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    run_id = data["run_id"]

    snap = client.get(f"/runs/{run_id}", headers=headers)
    assert snap.status_code == 200, snap.text
    body = snap.json()
    assert body["module_id"] == "sql_analytics"
    assert body["run_kind"] == "sql_analysis"
