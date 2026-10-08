import pytest
from conftest import client_for, SITE_OWNER
from flowharness import Env


@pytest.fixture
def env(provisioned):
    f, url = provisioned
    clients = {}
    def get(upn):
        if upn not in clients:
            clients[upn] = client_for(f, upn, url)
        return clients[upn]
    e = Env(f, url, get)
    o = e.c(SITE_OWNER)
    # people
    o.create_item("POUEmployees", {"Title": "Op One", "BadgeID": "1001", "EmployeeName": "Op One", "Active": True, "Role": "Operator"})
    o.create_item("POUEmployees", {"Title": "Op Two", "BadgeID": "1002", "EmployeeName": "Op Two", "Active": True, "Role": "Operator"})
    o.create_item("POUEmployees", {"Title": "Gone", "BadgeID": "1003", "EmployeeName": "Gone", "Active": False, "Role": "Operator"})
    o.create_item("POUEmployees", {"Title": "Sue Super", "BadgeID": "2001", "EmployeeName": "Sue Super", "Active": True, "Role": "Supervisor", "MicrosoftUPN": "sup@test"})
    o.create_item("POUEmployees", {"Title": "Owner Admin", "BadgeID": "9001", "EmployeeName": "Owner Admin", "Active": True, "Role": "Admin", "MicrosoftUPN": SITE_OWNER})
    o.create_item("POUStations", {"Title": "CAB-01", "StationID": "CAB-01", "Active": True})
    o.create_item("POUStations", {"Title": "CAB-02", "StationID": "CAB-02", "Active": True})
    o.create_item("POULocations", {"Title": "1-A", "LocationCode": "1-A", "Active": True})
    o.create_item("POULocations", {"Title": "2-B", "LocationCode": "2-B", "Active": True})
    svc = e.c("svc@test")
    svc.create_item("POUItems", {"Title": "A", "ItemID": "A", "ItemName": "Widget"})
    svc.create_item("POUStockLocations", {"Title": "A @ 1-A", "StockKey": "A|1-A", "ItemID": "A", "LocationCode": "1-A", "ItemName": "Widget", "MinQty": 2, "MaxQty": 10, "StockVersion": 0, "BalanceStatus": "NoBalance"})
    return e


def opening(env, key="A|1-A", qty=5):
    rid = env.new_request(SITE_OWNER, RequestType="OPENING", StockKey=key, ItemID=key.split("|")[0], LocationCode=key.split("|")[1], Quantity=qty, StationID="MIGRATION")
    return rid, env.process(rid, caller=SITE_OWNER)


def test_opening_balance_posts_through_the_flow(env):
    rid, rt = opening(env)
    assert rt.response["body"]["status"] == "Succeeded", rt.response
    s = env.stock("A|1-A")
    assert (s["OnHandQty"], s["StockVersion"], s["BalanceStatus"]) == (5, 1, "Unverified")
    led = env.ledger("A|1-A")
    assert len(led) == 1 and led[0]["PostingState"] == "Posted" and led[0]["SeqNo"] == 1 and led[0]["LedgerType"] == "OPENING"
    assert led[0]["QtyBefore"] is None and led[0]["QtyDelta"] is None and led[0]["QtyAfter"] == 5
    r = env.req(rid)
    assert r["RequestStatus"] == "Succeeded" and r["InventoryEffect"] == "Applied" and r["IsOpen"] is False


def test_issue_and_receipt_chain(env):
    opening(env)
    sess = env.login()
    assert sess["ok"] == "yes" and sess["employeeName"] == "Op One", sess
    r1 = env.new_request("station1@test", RequestType="ISSUE", SessionID=sess["sessionId"], StationID="CAB-01", StockKey="A|1-A", ItemID="A", LocationCode="1-A", Quantity=2)
    rt = env.process(r1)
    b = rt.response["body"]
    assert b["status"] == "Succeeded" and b["newOnHand"] == "3", b
    r2 = env.new_request("station1@test", RequestType="RECEIPT", SessionID=sess["sessionId"], StationID="CAB-01", StockKey="A|1-A", ItemID="A", LocationCode="1-A", Quantity=4)
    assert env.process(r2).response["body"]["newOnHand"] == "7"
    s = env.stock("A|1-A")
    assert (s["OnHandQty"], s["StockVersion"]) == (7, 3)
    led = sorted(env.ledger("A|1-A"), key=lambda x: x["SeqNo"])
    assert [(l["SeqNo"], l["LedgerType"], l["QtyBefore"], l["QtyDelta"], l["QtyAfter"], l["PostingState"]) for l in led] == [
        (1, "OPENING", None, None, 5, "Posted"), (2, "ISSUE", 5, -2, 3, "Posted"), (3, "RECEIPT", 3, 4, 7, "Posted")]
    assert led[1]["EmployeeName"] == "Op One" and led[1]["BadgeID"] == "1001" and led[1]["StationID"] == "CAB-01"
    assert "Removed 2" in env.req(r1)["ResultMessage"]


def test_issue_more_than_on_hand_is_rejected_with_nothing_changed(env):
    opening(env)
    sess = env.login()
    r = env.new_request("station1@test", RequestType="ISSUE", SessionID=sess["sessionId"], StationID="CAB-01", StockKey="A|1-A", Quantity=6)
    b = env.process(r).response["body"]
    assert b["status"] == "Rejected" and b["code"] == "INSUFFICIENT_STOCK" and b["effect"] == "NotApplied"
    assert "Only 5 on hand" in b["message"]
    assert env.stock("A|1-A")["OnHandQty"] == 5 and len(env.ledger("A|1-A")) == 1


@pytest.mark.parametrize("qty,code", [(0, "INVALID_QUANTITY"), (2.5, "INVALID_QUANTITY")])
def test_invalid_quantities_rejected(env, qty, code):
    opening(env)
    sess = env.login()
    r = env.new_request("station1@test", RequestType="ISSUE", SessionID=sess["sessionId"], StationID="CAB-01", StockKey="A|1-A", Quantity=qty)
    b = env.process(r).response["body"]
    assert b["status"] == "Rejected" and b["code"] == code
    assert env.stock("A|1-A")["OnHandQty"] == 5


def test_receipt_over_limit_rejected(env):
    opening(env)
    sess = env.login()
    r = env.new_request("station1@test", RequestType="RECEIPT", SessionID=sess["sessionId"], StationID="CAB-01", StockKey="A|1-A", Quantity=501)
    b = env.process(r).response["body"]
    assert b["code"] == "QUANTITY_OVER_LIMIT" and "part number" in b["message"]
    assert env.stock("A|1-A")["OnHandQty"] == 5


def test_blank_balance_cannot_be_issued_or_received(env):
    sess = env.login()
    for t in ("ISSUE", "RECEIPT"):
        r = env.new_request("station1@test", RequestType=t, SessionID=sess["sessionId"], StationID="CAB-01", StockKey="A|1-A", Quantity=1)
        b = env.process(r).response["body"]
        assert b["code"] == "NO_BALANCE" and b["effect"] == "NotApplied", b
    assert env.stock("A|1-A")["OnHandQty"] is None


def test_unknown_stock_record(env):
    sess = env.login()
    r = env.new_request("station1@test", RequestType="ISSUE", SessionID=sess["sessionId"], StationID="CAB-01", StockKey="NOPE|1-A", Quantity=1)
    assert env.process(r).response["body"]["code"] == "STOCK_NOT_FOUND"


def test_double_processing_of_same_request_is_idempotent(env):
    opening(env)
    sess = env.login()
    r = env.new_request("station1@test", RequestType="ISSUE", SessionID=sess["sessionId"], StationID="CAB-01", StockKey="A|1-A", Quantity=2)
    b1 = env.process(r).response["body"]
    b2 = env.process(r).response["body"]
    b3 = env.process(r).response["body"]
    assert b1["status"] == b2["status"] == b3["status"] == "Succeeded"
    assert env.stock("A|1-A")["OnHandQty"] == 3 and len(env.ledger("A|1-A")) == 2
