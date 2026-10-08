"""Crash / lost-response injection at EVERY SharePoint call of an ISSUE, then recovery by re-processing."""
import threading
import random
import pytest
from test_flow_basic import env, opening   # noqa: F401
from flowlab.connectors import CallIndexPlan
from invariants import check


def setup_issue(env, qty=2, on_hand=5):
    opening(env, "A|1-A", on_hand)
    sess = env.login()["sessionId"]
    rid = env.new_request("station1@test", RequestType="ISSUE", SessionID=sess, StationID="CAB-01", StockKey="A|1-A", Quantity=qty)
    return rid


def count_calls(env):
    rid = setup_issue(env)
    rt = env.process(rid)
    assert rt.response["body"]["status"] == "Succeeded"
    return len(rt.sp.calls)


def test_clean_run_call_count_is_reasonable(env):
    n = count_calls(env)
    assert 10 < n < 40, n


@pytest.mark.parametrize("when", ["before", "after", "lose", "throttle"])
def test_fault_at_every_call_then_recovery(provisioned, when):
    """For each call index: inject one fault, check invariants immediately, then recover and require the exact intended outcome."""
    from test_flow_basic import env as _env_fixture
    f, url = provisioned
    # discover the call count on a scratch site
    import conftest
    results = []
    n_calls = None
    index = 1
    while True:
        e = _build_env(f, url, index)
        rid = setup_issue(e)
        base = e.stock("A|1-A")["StockVersion"]
        plan = CallIndexPlan(index, when)
        rt = e.process(rid, plan=plan)
        if not plan.fired:
            break                           # ran past the last call: every call index has been exercised
        # ---- immediately after the fault: nothing inconsistent, and no false claims
        assert check(e) == [], (when, index, plan.fired, check(e))
        if rt.response:
            b = rt.response["body"]
            assert not (b["status"] == "Rejected" and b["effect"] == "NotApplied" and e.ledger("A|1-A")[1:]), ("false NotApplied", when, index, b)
            if b["status"] == "Succeeded":
                led = [l for l in e.ledger("A|1-A") if l["LedgerType"] == "ISSUE"]
                assert led and led[0]["PostingState"] == "Posted"
            if b["code"] == "UNCONFIRMED":
                assert "Do NOT repeat" in b["message"]
        # ---- recovery: time passes beyond the claim timeout, then the sweeper/instant flow re-processes
        for _ in range(4):
            e.clock.advance(200)
            e.process(rid)
        problems = check(e, expect_complete=True)
        assert problems == [], (when, index, plan.fired, problems)
        s = e.stock("A|1-A")
        assert (s["OnHandQty"], s["StockVersion"]) == (3, 2), (when, index, plan.fired, s)    # applied exactly once
        issues = [l for l in e.ledger("A|1-A") if l["LedgerType"] == "ISSUE"]
        assert len(issues) == 1 and issues[0]["PostingState"] == "Posted", (when, index, plan.fired)
        r = e.req(rid)
        assert r["RequestStatus"] == "Succeeded" and r["InventoryEffect"] == "Applied" and r["IsOpen"] is False, (when, index, r)
        results.append(index)
        index += 1
        assert index < 120
    # every SharePoint call of a clean ISSUE (16 today) was faulted once
    assert len(results) >= 14, results


def _build_env(f, url, salt):
    """Fresh stock/requests per trial on the shared provisioned site (unique keys are re-used by deleting rows)."""
    from conftest import client_for, SITE_OWNER
    from flowharness import Env
    import test_flow_basic as tb
    clients = {}
    def get(upn):
        if upn not in clients:
            clients[upn] = client_for(f, upn, url)
        return clients[upn]
    # reset all transactional/master lists
    for ln in ("POURequests", "POULedger", "POUSessions", "POUStockLocations", "POUItems", "POUEmployees", "POUStations", "POULocations", "POUOpsEvents"):
        f.lists[ln].items.clear()
    e = Env(f, url, get)
    o = e.c(SITE_OWNER)
    for r in ({"Title": "Op One", "BadgeID": "1001", "EmployeeName": "Op One", "Active": True, "Role": "Operator"},
              {"Title": "Sue", "BadgeID": "2001", "EmployeeName": "Sue Super", "Active": True, "Role": "Supervisor", "MicrosoftUPN": "sup@test"},
              {"Title": "Own", "BadgeID": "9001", "EmployeeName": "Owner Admin", "Active": True, "Role": "Admin", "MicrosoftUPN": SITE_OWNER}):
        o.create_item("POUEmployees", r)
    o.create_item("POUStations", {"Title": "CAB-01", "StationID": "CAB-01", "Active": True})
    o.create_item("POULocations", {"Title": "1-A", "LocationCode": "1-A", "Active": True})
    s = e.c("svc@test")
    s.create_item("POUItems", {"Title": "A", "ItemID": "A", "ItemName": "Widget"})
    s.create_item("POUStockLocations", {"Title": "A @ 1-A", "StockKey": "A|1-A", "ItemID": "A", "LocationCode": "1-A", "ItemName": "Widget", "MinQty": 2, "MaxQty": 10, "StockVersion": 0, "BalanceStatus": "NoBalance"})
    return e
