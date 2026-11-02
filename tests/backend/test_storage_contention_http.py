"""Authorized reads report real inspection contention as temporary unavailability."""

from test_task_runtime import api as api


def test_exclusive_writer_returns_safe_busy_then_explicit_read_refresh_recovers(api):
    with api.store._connection() as holder:
        holder.execute("BEGIN EXCLUSIVE")
        response = api.client.get("/api/v1/authorization")
        assert response.status_code == 503, response.text
        assert response.json()["code"] == "storage_busy"
        assert response.headers["Retry-After"] == "1"
        assert "database" not in response.text.lower()
        holder.execute("ROLLBACK")
    assert api.client.get("/api/v1/authorization").json()["state"] == "active"
    with api.store.read() as unit:
        assert unit.households.current().revision == 1
        assert len(unit.audit.entries("home")) == 1
