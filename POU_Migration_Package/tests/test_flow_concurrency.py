"""Real threads running the generated flow JSON against the SharePoint model with random latency."""
import random
import threading
import time
import uuid

import pytest

from conftest import SITE_OWNER, client_for
from flowharness import Env
from invariants import check
import test_flow_faults as tf


def jitter(rng):
    def before(ctx):
        time.sleep(rng.random() * 0.002)
        return None
    return before


@pytest.fixture
def base(provisioned):
    f, url = provisioned
    f.add_member("POU Operators", "station3@test")
    return f, url


def mk(f, url, seed):
    e = tf._build_env(f, url, seed)
    f.fault_before = jitter(random.Random(seed))
    o = e.c(SITE_OWNER)
    o.create_item("POUEmployees", {"Title": "Op Two", "BadgeID": "1002", "EmployeeName": "Op Two", "Active": True, "Role": "Operator"})
    o.create_item("POUEmployees", {"Title": "Op Three", "BadgeID": "1003", "EmployeeName": "Op Three", "Active": True, "Role": "Operator"})
    o.create_item("POUStations", {"Title": "CAB-02", "StationID": "CAB-02", "Active": True})
    return e


def run_threads(fns):
    out = [None] * len(fns)
    errs = []
    def wrap(i, fn):
        try:
            out[i] = fn()
        except Exception as ex:      # noqa
            errs.append(ex)
    ts = [threading.Thread(target=wrap, args=(i, fn)) for i, fn in enumerate(fns)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errs, errs
    return out


def settle(e, rids, rounds=8):
    """What the 5-minute sweeper does: keep re-processing anything not terminal after the claim timeout."""
    for _ in range(rounds):
        pend = [r for r in rids if e.req(r)["RequestStatus"] in ("Pending", "Processing")]
        if not pend:
            return
        e.clock.advance(200)
        for r in pend:
            e.process(r)


@pytest.mark.parametrize("seed", range(25))
def test_two_operators_withdraw_the_last_unit(base, seed):
    f, url = base
    e = mk(f, url, seed)
    tf.opening(e, "A|1-A", 1) if hasattr(tf, "opening") else None
    from test_flow_basic import opening
    opening(e, "A|1-A", 1)
    s1 = e.login("1001", "CAB-01", "station1@test")["sessionId"]
    s2 = e.login("1002", "CAB-02", "station2@test")["sessionId"]
    r1 = e.new_request("station1@test", RequestType="ISSUE", SessionID=s1, StationID="CAB-01", StockKey="A|1-A", Quantity=1)
    r2 = e.new_request("station2@test", RequestType="ISSUE", SessionID=s2, StationID="CAB-02", StockKey="A|1-A", Quantity=1)
    run_threads([lambda: e.process(r1, caller="station1@test"), lambda: e.process(r2, caller="station2@test")])
    assert check(e) == []
    settle(e, [r1, r2])
    assert check(e, expect_complete=True) == []
    st = sorted(e.req(r)["RequestStatus"] for r in (r1, r2))
    assert st == ["Rejected", "Succeeded"], st
    rej = [e.req(r) for r in (r1, r2) if e.req(r)["RequestStatus"] == "Rejected"][0]
    assert rej["ResultCode"] == "INSUFFICIENT_STOCK" and rej["InventoryEffect"] == "NotApplied"
    s = e.stock("A|1-A")
    assert s["OnHandQty"] == 0 and s["StockVersion"] == 2
    assert len([l for l in e.ledger("A|1-A") if l["LedgerType"] == "ISSUE"]) == 1


@pytest.mark.parametrize("seed", range(6))
def test_many_operators_race_for_limited_stock(base, seed):
    f, url = base
    e = mk(f, url, 100 + seed)
    from test_flow_basic import opening
    opening(e, "A|1-A", 5)
    users = [("1001", "CAB-01", "station1@test"), ("1002", "CAB-02", "station2@test"), ("1003", "CAB-01", "station3@test")]
    sess = [e.login(b, st, u)["sessionId"] for b, st, u in users]
    rids, fns = [], []
    for i in range(9):
        b, st, u = users[i % 3]
        rid = e.new_request(u, RequestType="ISSUE", SessionID=sess[i % 3], StationID=st, StockKey="A|1-A", Quantity=1)
        rids.append(rid)
        fns.append(lambda rid=rid, u=u: e.process(rid, caller=u))
    run_threads(fns)
    assert check(e) == []
    settle(e, rids, rounds=12)
    assert check(e, expect_complete=True) == []
    sts = [e.req(r)["RequestStatus"] for r in rids]
    assert sts.count("Succeeded") == 5 and sts.count("Rejected") == 4, sts
    s = e.stock("A|1-A")
    assert s["OnHandQty"] == 0 and s["StockVersion"] == 6
    assert len([l for l in e.ledger("A|1-A") if l["LedgerType"] == "ISSUE"]) == 5


@pytest.mark.parametrize("seed", range(8))
def test_same_request_processed_by_three_workers_applies_once(base, seed):
    """Instant flow + sweeper + a retry all pick up the SAME RequestID simultaneously (double click / retry / resume)."""
    f, url = base
    e = mk(f, url, 200 + seed)
    from test_flow_basic import opening
    opening(e, "A|1-A", 5)
    s1 = e.login()["sessionId"]
    rid = e.new_request("station1@test", RequestType="ISSUE", SessionID=s1, StationID="CAB-01", StockKey="A|1-A", Quantity=2)
    # make workers think the claim is stale so all three try to take over
    out = run_threads([lambda: e.process(rid) for _ in range(3)])
    assert check(e) == []
    settle(e, [rid])
    assert check(e, expect_complete=True) == []
    s = e.stock("A|1-A")
    assert (s["OnHandQty"], s["StockVersion"]) == (3, 2)
    assert len([l for l in e.ledger("A|1-A") if l["LedgerType"] == "ISSUE"]) == 1
    assert e.req(rid)["RequestStatus"] == "Succeeded"


def test_duplicate_request_id_cannot_be_created_twice(base):
    f, url = base
    e = mk(f, url, 300)
    rid = str(uuid.uuid4())
    e.new_request("station1@test", RequestID=rid, RequestType="ISSUE", StockKey="A|1-A", Quantity=1)
    from pou_tools.spclient import SpError
    with pytest.raises(SpError) as ex:
        e.new_request("station1@test", RequestID=rid, RequestType="ISSUE", StockKey="A|1-A", Quantity=1)
    assert ex.value.is_duplicate


@pytest.mark.parametrize("seed", range(6))
def test_other_flows_editing_the_stock_row_do_not_break_posting(base, seed):
    """A second writer keeps touching non-quantity fields (changes the ETag) while postings run: 412s must be retried."""
    f, url = base
    e = mk(f, url, 400 + seed)
    from test_flow_basic import opening
    opening(e, "A|1-A", 8)
    s1 = e.login()["sessionId"]
    stop = threading.Event()
    svc = e.c("svc@test")
    def toucher():
        n = 0
        while not stop.is_set():
            row = svc.get_by_key("POUStockLocations", "StockKey", "A|1-A")
            try:
                svc.update_item("POUStockLocations", row["Id"], {"Area": f"touch{n}"}, etag=row["__metadata"]["etag"])
            except Exception:
                pass
            n += 1
            time.sleep(0.0005)
    th = threading.Thread(target=toucher); th.start()
    rids = [e.new_request("station1@test", RequestType="ISSUE", SessionID=s1, StationID="CAB-01", StockKey="A|1-A", Quantity=1) for _ in range(4)]
    run_threads([lambda rid=rid: e.process(rid) for rid in rids])
    stop.set(); th.join()
    settle(e, rids, rounds=10)
    assert check(e, expect_complete=True) == []
    s = e.stock("A|1-A")
    assert s["OnHandQty"] == 4 and s["StockVersion"] == 5


def test_out_of_band_edit_is_detected_not_silently_overwritten(base):
    f, url = base
    e = mk(f, url, 500)
    from test_flow_basic import opening
    opening(e, "A|1-A", 5)
    s1 = e.login()["sessionId"]
    # an admin / break-glass owner edits OnHandQty directly, bypassing the ledger
    row = e.stock("A|1-A")
    e.c(SITE_OWNER).update_item("POUStockLocations", row["Id"], {"OnHandQty": 50})
    rid = e.new_request("station1@test", RequestType="ISSUE", SessionID=s1, StationID="CAB-01", StockKey="A|1-A", Quantity=1)
    b = e.process(rid).response["body"]
    assert b["status"] == "Failed" and b["code"] == "DRIFT_DETECTED" and b["effect"] == "NotApplied"
    assert e.stock("A|1-A")["OnHandQty"] == 50 and len(e.ledger("A|1-A")) == 1
    ev = list(e.c(SITE_OWNER).query("POUOpsEvents"))
    assert any(x["EventType"] == "DRIFT" and x["Severity"] == "Critical" for x in ev)


def test_out_of_band_edit_between_intent_and_apply_voids_the_intent(base):
    f, url = base
    e = mk(f, url, 600)
    from test_flow_basic import opening
    from flowlab.connectors import FaultPlan, Rule
    opening(e, "A|1-A", 5)
    s1 = e.login()["sessionId"]
    rid = e.new_request("station1@test", RequestType="ISSUE", SessionID=s1, StationID="CAB-01", StockKey="A|1-A", Quantity=1)
    # crash right after the intent is written
    plan = FaultPlan([Rule("POST", r"POULedger.*items$", "after", nth=1)])
    e.process(rid, plan=plan)
    row = e.stock("A|1-A")
    e.c(SITE_OWNER).update_item("POUStockLocations", row["Id"], {"OnHandQty": 77})        # direct edit while the intent is pending
    e.clock.advance(300)
    b = e.process(rid).response["body"]
    assert b["status"] == "Failed" and b["code"] == "STOCK_CHANGED_OUTSIDE_PROTOCOL" and b["effect"] == "NotApplied"
    assert e.stock("A|1-A")["OnHandQty"] == 77
    voided = [l for l in e.ledger("A|1-A") if l["PostingState"] == "Voided"]
    assert len(voided) == 1 and voided[0]["LedgerKey"].startswith("VOID|")
    assert any(x["EventType"] == "STOCK_ANOMALY" for x in e.c(SITE_OWNER).query("POUOpsEvents"))
