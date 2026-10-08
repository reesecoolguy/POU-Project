import json
import pytest
from test_flow_basic import env, opening   # noqa: F401
from flowlab.connectors import FaultPlan, Rule, CallIndexPlan
from invariants import check
from conftest import SITE_OWNER


def mkissue(env, qty=1, sess=None):
    sess = sess or env.login()["sessionId"]
    return env.new_request("station1@test", RequestType="ISSUE", SessionID=sess, StationID="CAB-01", StockKey="A|1-A", Quantity=qty)


def n_actions(rt):
    return sum(1 for r in rt.results.values() if r.status != "Skipped")


def test_idle_sweeper_is_cheap(env):
    rt = env.sweep()
    assert rt.status == "Succeeded" and n_actions(rt) <= 8, n_actions(rt)
    assert len(rt.sp.calls) == 1


def test_requests_whose_instant_call_was_lost_are_processed_by_the_sweeper(env):
    opening(env)
    sess = env.login()["sessionId"]
    r = [mkissue(env, 1, sess) for _ in range(3)]            # app created them, but the call to the instant flow never arrived
    rt = env.sweep()
    assert all(env.req(x)["RequestStatus"] == "Pending" for x in r)      # too young: the instant flow gets a 30 s head start
    env.clock.advance(60)
    rt = env.sweep()
    assert [env.req(x)["RequestStatus"] for x in r] == ["Succeeded"] * 3
    assert env.stock("A|1-A")["OnHandQty"] == 2 and check(env, expect_complete=True) == []


def test_sweeper_resumes_a_run_that_died_after_writing_the_intent(env):
    opening(env)
    r = mkissue(env, 2)
    env.process(r, plan=FaultPlan([Rule("POST", r"POULedger.*items$", "after", nth=1)]))     # host dies right after the intent insert
    assert [l["PostingState"] for l in env.ledger("A|1-A") if l["LedgerType"] == "ISSUE"] == ["Intent"]
    assert env.stock("A|1-A")["OnHandQty"] == 5
    env.sweep()                                              # claim is fresh: left alone
    assert env.req(r)["RequestStatus"] == "Processing"
    env.clock.advance(200)
    env.sweep()
    assert env.req(r)["RequestStatus"] == "Succeeded"
    s = env.stock("A|1-A")
    assert (s["OnHandQty"], s["StockVersion"]) == (3, 2)
    assert check(env, expect_complete=True) == []


def test_sweeper_completes_stock_applied_but_ledger_not_posted(env):
    opening(env)
    r = mkissue(env, 1)
    rt = env.process(r, plan=FaultPlan([Rule("POST", r"POULedger.*items\(\d+\)", "throttle", nth=1)]))   # finalize-ledger write rejected (429); stock already applied
    b = rt.response["body"]
    assert b["status"] == "Processing" and b["code"] == "FINALIZING" and b["effect"] == "Applied" and "WAS updated" in b["message"]
    st = env.req(r)
    assert st["RequestStatus"] == "Processing" and env.stock("A|1-A")["OnHandQty"] == 4
    assert [l["PostingState"] for l in env.ledger("A|1-A") if l["LedgerType"] == "ISSUE"] == ["Intent"]
    env.clock.advance(200)
    env.sweep()
    assert env.req(r)["RequestStatus"] == "Succeeded"
    assert [l["PostingState"] for l in env.ledger("A|1-A") if l["LedgerType"] == "ISSUE"] == ["Posted"]
    assert env.stock("A|1-A")["OnHandQty"] == 4


def test_unanswered_supervisor_request_expires_with_nothing_changed(env):
    opening(env)
    sess = env.login()["sessionId"]
    a = env.new_request("station1@test", RequestType="AUDIT", SessionID=sess, StationID="CAB-01", StockKey="A|1-A", Quantity=4, ExpectedVersion=1)
    assert env.process(a).response["body"]["status"] == "AwaitingSupervisor"
    env.clock.advance(3600)
    env.sweep()
    assert env.req(a)["RequestStatus"] == "AwaitingSupervisor"
    env.clock.advance(25 * 3600)
    env.sweep()
    r = env.req(a)
    assert r["RequestStatus"] == "Rejected" and r["ResultCode"] == "EXPIRED" and r["InventoryEffect"] == "NotApplied" and r["IsOpen"] is False
    assert env.stock("A|1-A")["OnHandQty"] == 5


def test_request_that_keeps_failing_is_given_up_only_when_no_ledger_exists(env):
    opening(env)
    r = mkissue(env, 1)
    # every attempt dies before it can write the intent -> after MaxProcessAttempts the request is Failed/NotApplied (established: no ledger row)
    for i in range(7):
        env.clock.advance(200)
        env.process(r, plan=FaultPlan([Rule("GET", r"POUStockLocations", "before", nth=None)]))
    env.clock.advance(200)
    env.sweep()
    q = env.req(r)
    assert q["RequestStatus"] == "Rejected" and q["ResultCode"] == "GAVE_UP" and q["InventoryEffect"] == "NotApplied", q
    assert env.stock("A|1-A")["OnHandQty"] == 5 and len([l for l in env.ledger("A|1-A") if l["LedgerType"] == "ISSUE"]) == 0


def test_a_request_with_an_intent_is_never_given_up(env):
    opening(env)
    r = mkissue(env, 1)
    env.process(r, plan=FaultPlan([Rule("POST", r"POULedger.*items$", "after", nth=1)]))
    row = env.req(r)
    env.c(SITE_OWNER).update_item("POURequests", row["Id"], {"AttemptCount": 99})       # pretend it was retried many times
    env.clock.advance(200)
    env.sweep()
    assert env.req(r)["RequestStatus"] == "Succeeded" and env.stock("A|1-A")["OnHandQty"] == 4


def test_opening_batch_processed_by_one_sweep(env):
    svc = env.c("svc@test")
    for i in range(30):
        svc.create_item("POUStockLocations", {"Title": f"B{i}", "StockKey": f"B{i}|1-A", "ItemID": f"B{i}", "LocationCode": "1-A", "ItemName": "x", "MinQty": 1, "MaxQty": 9, "StockVersion": 0, "BalanceStatus": "NoBalance"})
    rids = [env.new_request(SITE_OWNER, RequestType="OPENING", StockKey=f"B{i}|1-A", ItemID=f"B{i}", LocationCode="1-A", Quantity=i, StationID="MIGRATION") for i in range(30)]
    env.clock.advance(60)
    env.sweep()
    assert [env.req(r)["RequestStatus"] for r in rids] == ["Succeeded"] * 30
    for i in range(30):
        s = env.stock(f"B{i}|1-A")
        assert (s["OnHandQty"], s["StockVersion"], s["BalanceStatus"]) == (i, 1, "Unverified")
    assert check(env, expect_complete=True) == []
