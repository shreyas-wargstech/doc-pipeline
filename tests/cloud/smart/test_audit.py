import json
import pytest

from cloud.smart.audit import record_smart_action


@pytest.mark.asyncio
async def test_record_smart_action_writes_row():
    captured = {}

    class FakeSession:
        async def execute(self, stmt, params=None):
            captured["stmt"] = str(stmt)
            captured["params"] = params

    await record_smart_action(
        FakeSession(),
        action="match_auto_resolve",
        document_id="doc-1",
        page_num=None,
        reason="name variation: middle name omitted",
        before={"match_status": "manual_review"},
        after={"match_status": "matched"},
    )

    p = captured["params"]
    assert p["action"] == "smart.match_auto_resolve"
    assert p["document_id"] == "doc-1"
    assert p["result"] == "ok"
    assert p["username"] == "system"
    payload = json.loads(p["params"])
    assert payload["reason"] == "name variation: middle name omitted"
    assert payload["before"] == {"match_status": "manual_review"}
    assert payload["after"] == {"match_status": "matched"}
    assert "INSERT INTO audit_log" in captured["stmt"]


@pytest.mark.asyncio
async def test_record_smart_action_optional_fields():
    captured = {}

    class FakeSession:
        async def execute(self, stmt, params=None):
            captured["params"] = params

    await record_smart_action(
        FakeSession(), action="monitor_resume", document_id="doc-2", reason="stuck in structuring"
    )
    payload = json.loads(captured["params"]["params"])
    assert payload["before"] is None
    assert payload["after"] is None
    assert payload["page_num"] is None
