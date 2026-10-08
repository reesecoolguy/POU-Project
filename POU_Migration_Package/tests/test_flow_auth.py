import json
import pytest
from test_flow_basic import env, opening   # noqa: F401  (fixtures)
from conftest import SITE_OWNER


def issue(env, sess, qty=1, caller="station1@test", key="A|1-A", **kw):
    return env.new_request(caller, RequestType="ISSUE", SessionID=sess, StationID=kw.pop("StationID", "CAB-01"), StockKey=key, Quantity=qty, **kw)


def test_login_rejects_unknown_and_inactive_badges(env):
    assert env.login("9999")["code"] == "INVALID_BADGE"
    assert env.login("1003")["code"] == "BADGE_INACTIVE"
    assert env.login("1001", station="NOPE")["code"] == "STATION_INVALID"
    ev = list(env.c(SITE_OWNER).query("POUOpsEvents"))
    assert any(e["EventType"] == "BADGE_FAILURES" for e in ev)
    # repeated failures de-duplicate into one event with a count
    env.login("9998")
    ev = [e for e in env.c(SITE_OWNER).query("POUOpsEvents") if e["EventType"] == "BADGE_FAILURES"]
    assert len(ev) == 1 and ev[0]["OccurrenceCount"] == 2
    assert env.fake.count("POUSessions") == 0


def test_login_creates_session_bound_to_calling_account(env):
    r = env.login()
    s = env.c(SITE_OWNER).get_by_key("POUSessions", "SessionID", r["sessionId"])
    assert s["AppAccountUPN"] == "station1@test" and s["SessionState"] == "Active" and r["idleMinutes"] == "3"


def test_station_expected_account_is_enforced(env):
    st = env.c(SITE_OWNER).get_by_key("POUStations", "StationID", "CAB-02")
    env.c(SITE_OWNER).update_item("POUStations", st["Id"], {"ExpectedAccountUPN": "station2@test"})
    assert env.login(station="CAB-02", caller="station1@test")["code"] == "STATION_ACCOUNT_MISMATCH"
    assert env.login(station="CAB-02", caller="station2@test")["ok"] == "yes"


def test_forged_or_missing_session_is_rejected(env):
    opening(env)
    for sid in ("", "deadbeef"):
        b = env.process(issue(env, sid)).response["body"]
        assert b["status"] == "Rejected" and b["code"] == "NO_SESSION" and b["effect"] == "NotApplied"
    assert env.stock("A|1-A")["OnHandQty"] == 5


def test_session_from_another_microsoft_account_is_rejected(env):
    opening(env)
    sess = env.login(caller="station1@test")["sessionId"]
    b = env.process(issue(env, sess, caller="station2@test"), caller="station2@test").response["body"]   # station2's account replays station1's session id
    assert b["code"] == "SESSION_ACCOUNT_MISMATCH"
    assert env.stock("A|1-A")["OnHandQty"] == 5


def test_session_idle_expiry_enforced_on_server(env):
    opening(env)
    sess = env.login()["sessionId"]
    env.clock.advance(11 * 60)
    b = env.process(issue(env, sess)).response["body"]
    assert b["code"] == "SESSION_EXPIRED"
    assert env.stock("A|1-A")["OnHandQty"] == 5


def test_badge_deactivated_after_login_is_rejected(env):
    opening(env)
    sess = env.login()["sessionId"]
    e = env.c(SITE_OWNER).get_by_key("POUEmployees", "BadgeID", "1001")
    env.c(SITE_OWNER).update_item("POUEmployees", e["Id"], {"Active": False})
    assert env.process(issue(env, sess)).response["body"]["code"] == "EMPLOYEE_INACTIVE"


def test_logout_ends_session(env):
    opening(env)
    r = env.login()
    out = env.run(env.flows["session"], ["LOGOUT", "", "", r["sessionId"], "station1@test"]).response["body"]
    assert out["ok"] == "yes"
    assert env.process(issue(env, r["sessionId"])).response["body"]["code"] == "SESSION_ENDED"
    # another account cannot end someone else's session
    r2 = env.login(badge="1002")
    bad = env.run(env.flows["session"], ["LOGOUT", "", "", r2["sessionId"], "station2@test"], caller="station2@test").response["body"]
    assert bad["ok"] == "no"


def test_unauthorized_adjustment_and_opening_and_approve_by_operator(env):
    opening(env)
    sess = env.login()["sessionId"]
    for t, extra in (("ADJUSTMENT", {"Reason": "because"}), ("REVERSAL", {"Reason": "x", "ReversesLedgerKey": "A|1-A#1"})):
        r = env.new_request("station1@test", RequestType=t, SessionID=sess, StationID="CAB-01", StockKey="A|1-A", Quantity=99, **extra)
        b = env.process(r).response["body"]
        assert b["code"] == "NOT_AUTHORIZED" and b["effect"] == "NotApplied", (t, b)
    r = env.new_request("station1@test", RequestType="OPENING", SessionID=sess, StationID="CAB-01", StockKey="A|1-A", Quantity=99)
    assert env.process(r).response["body"]["code"] == "NOT_AUTHORIZED"
    # an operator cannot approve their own request even with the right type
    a = env.new_request("station1@test", RequestType="AUDIT", SessionID=sess, StationID="CAB-01", StockKey="A|1-A", Quantity=4, ExpectedVersion=1)
    assert env.process(a).response["body"]["status"] == "AwaitingSupervisor"
    ap = env.new_request("station1@test", RequestType="APPROVE", TargetRequestID=a, Decision="Approve")
    assert env.process(ap).response["body"]["code"] == "NOT_AUTHORIZED"
    assert env.process(a).response["body"]["status"] == "AwaitingSupervisor"
    assert env.stock("A|1-A")["OnHandQty"] == 5


def test_operator_audit_waits_then_supervisor_approval_releases_it(env):
    opening(env)
    sess = env.login()["sessionId"]
    a = env.new_request("station1@test", RequestType="AUDIT", SessionID=sess, StationID="CAB-01", StockKey="A|1-A", Quantity=4, ExpectedVersion=1,
                        AuthorizedByUPN="sup@test")      # client-supplied field must be ignored
    b = env.process(a).response["body"]
    assert b["status"] == "AwaitingSupervisor" and b["effect"] == "NotApplied"
    assert env.req(a)["IsOpen"] is True and env.stock("A|1-A")["OnHandQty"] == 5
    # supervisor, signed in with their OWN Microsoft account, approves
    ap = env.new_request("sup@test", RequestType="APPROVE", TargetRequestID=a, Decision="Approve")
    assert env.process(ap, caller="sup@test").response["body"]["status"] == "Succeeded"
    assert env.req(a)["RequestStatus"] == "Pending"
    b = env.process(a).response["body"]
    assert b["status"] == "Succeeded", b
    s = env.stock("A|1-A")
    assert (s["OnHandQty"], s["BalanceStatus"], s["StockVersion"]) == (4, "Verified", 2)
    led = [l for l in env.ledger("A|1-A") if l["LedgerType"] == "AUDIT"][0]
    assert led["QtyBefore"] == 5 and led["QtyDelta"] == -1 and led["QtyAfter"] == 4 and led["AuthorizedByUPN"] == "sup@test" and led["EmployeeName"] == "Op One"
    assert env.req(a)["AuthorizedByUPN"] == "sup@test"


def test_supervisor_rejection_blocks_the_request(env):
    opening(env)
    sess = env.login()["sessionId"]
    a = env.new_request("station1@test", RequestType="AUDIT", SessionID=sess, StationID="CAB-01", StockKey="A|1-A", Quantity=4, ExpectedVersion=1)
    env.process(a)
    ap = env.new_request("sup@test", RequestType="APPROVE", TargetRequestID=a, Decision="Reject")
    env.process(ap, caller="sup@test")
    b = env.process(a).response["body"]
    assert b["status"] == "Rejected" and b["code"] == "SUPERVISOR_REJECTED" and b["effect"] == "NotApplied"
    assert env.stock("A|1-A")["OnHandQty"] == 5


def test_approval_by_non_supervisor_account_or_self_is_ignored(env):
    opening(env)
    sess = env.login()["sessionId"]
    a = env.new_request("station1@test", RequestType="AUDIT", SessionID=sess, StationID="CAB-01", StockKey="A|1-A", Quantity=4, ExpectedVersion=1)
    env.process(a)
    # station2 (not a supervisor) writes an APPROVE row directly
    ap = env.new_request("station2@test", RequestType="APPROVE", TargetRequestID=a, Decision="Approve")
    env.process(ap, caller="station2@test")
    env.c(SITE_OWNER)  # nothing released
    assert env.req(a)["RequestStatus"] == "AwaitingSupervisor"
    assert env.process(a).response["body"]["status"] == "AwaitingSupervisor"
    assert env.stock("A|1-A")["OnHandQty"] == 5


def test_supervisor_can_audit_directly_without_badge_session(env):
    opening(env)
    a = env.new_request("sup@test", RequestType="AUDIT", StationID="CAB-01", StockKey="A|1-A", Quantity=6, ExpectedVersion=1)
    b = env.process(a, caller="sup@test").response["body"]
    assert b["status"] == "Succeeded"
    led = [l for l in env.ledger("A|1-A") if l["LedgerType"] == "AUDIT"][0]
    assert led["EmployeeName"] == "Sue Super" and led["AuthorizedByUPN"] == "sup@test"


def test_stale_audit_is_rejected_and_requires_recount(env):
    opening(env)
    sess = env.login()["sessionId"]
    # count starts at version 1 ...
    a = env.new_request("sup@test", RequestType="AUDIT", StationID="CAB-01", StockKey="A|1-A", Quantity=5, ExpectedVersion=1)
    # ... but someone issues stock before the count is submitted
    env.process(issue(env, sess, 2))
    b = env.process(a, caller="sup@test").response["body"]
    assert b["status"] == "Rejected" and b["code"] == "STALE_COUNT" and b["effect"] == "NotApplied"
    assert "Recount" in b["message"] and env.stock("A|1-A")["OnHandQty"] == 3      # intervening movement NOT overwritten
    a2 = env.new_request("sup@test", RequestType="AUDIT", StationID="CAB-01", StockKey="A|1-A", Quantity=3, ExpectedVersion=2)
    assert env.process(a2, caller="sup@test").response["body"]["status"] == "Succeeded"


def test_first_count_of_blank_balance_establishes_it_without_inventing_before(env):
    a = env.new_request("sup@test", RequestType="AUDIT", StationID="CAB-01", StockKey="A|1-A", Quantity=7, ExpectedVersion=0)
    assert env.process(a, caller="sup@test").response["body"]["status"] == "Succeeded"
    l = env.ledger("A|1-A")[0]
    assert l["QtyBefore"] is None and l["QtyDelta"] is None and l["QtyAfter"] == 7
    assert env.stock("A|1-A")["BalanceStatus"] == "Verified"


def test_adjustment_requires_reason_and_supervisor(env):
    opening(env)
    r = env.new_request("sup@test", RequestType="ADJUSTMENT", StationID="CAB-01", StockKey="A|1-A", Quantity=9)
    assert env.process(r, caller="sup@test").response["body"]["code"] == "REASON_REQUIRED"
    r = env.new_request("sup@test", RequestType="ADJUSTMENT", StationID="CAB-01", StockKey="A|1-A", Quantity=9, Reason="found 4 in a drawer")
    assert env.process(r, caller="sup@test").response["body"]["status"] == "Succeeded"
    l = [x for x in env.ledger("A|1-A") if x["LedgerType"] == "ADJUSTMENT"][0]
    assert (l["QtyBefore"], l["QtyDelta"], l["QtyAfter"], l["Reason"]) == (5, 4, 9, "found 4 in a drawer")


def test_reversal_is_a_linked_new_entry_and_only_once(env):
    opening(env)
    sess = env.login()["sessionId"]
    env.process(issue(env, sess, 2))
    orig = [x for x in env.ledger("A|1-A") if x["LedgerType"] == "ISSUE"][0]
    r = env.new_request("sup@test", RequestType="REVERSAL", StationID="CAB-01", StockKey="A|1-A", ReversesLedgerKey=orig["LedgerKey"], Reason="wrong item scanned")
    assert env.process(r, caller="sup@test").response["body"]["status"] == "Succeeded"
    assert env.stock("A|1-A")["OnHandQty"] == 5
    rows = env.ledger("A|1-A")
    rev = [x for x in rows if x["LedgerType"] == "REVERSAL"][0]
    assert rev["ReversesLedgerKey"] == orig["LedgerKey"] and rev["QtyDelta"] == 2
    assert [x for x in rows if x["LedgerKey"] == orig["LedgerKey"]][0]["PostingState"] == "Posted"      # original untouched
    r2 = env.new_request("sup@test", RequestType="REVERSAL", StationID="CAB-01", StockKey="A|1-A", ReversesLedgerKey=orig["LedgerKey"], Reason="again")
    assert env.process(r2, caller="sup@test").response["body"]["code"] == "REVERSAL_ALREADY"


def test_same_part_at_two_locations_posts_independently(env):
    svc = env.c("svc@test")
    svc.create_item("POUStockLocations", {"Title": "A @ 2-B", "StockKey": "A|2-B", "ItemID": "A", "LocationCode": "2-B", "ItemName": "Widget", "MinQty": 1, "MaxQty": 5, "StockVersion": 0, "BalanceStatus": "NoBalance"})
    opening(env, "A|1-A", 5)
    opening(env, "A|2-B", 2)
    sess = env.login()["sessionId"]
    env.process(issue(env, sess, 1, key="A|2-B"))
    assert env.stock("A|1-A")["OnHandQty"] == 5 and env.stock("A|2-B")["OnHandQty"] == 1
    assert env.stock("A|2-B")["StockVersion"] == 2 and env.stock("A|1-A")["StockVersion"] == 1


def test_low_stock_flag_follows_rule(env):
    opening(env)   # min 2, on hand 5
    s = env.stock("A|1-A")
    assert s["LowStockFlag"] is False
    sess = env.login()["sessionId"]
    env.process(issue(env, sess, 3))     # 2 == min -> low under LE
    assert env.stock("A|1-A")["LowStockFlag"] is True
    row = env.c(SITE_OWNER).get_by_key("POUSettings", "SettingKey", "LowStockRule")
    env.c(SITE_OWNER).update_item("POUSettings", row["Id"], {"SettingValue": "LT"})
    env.process(env.new_request("station1@test", RequestType="RECEIPT", SessionID=sess, StationID="CAB-01", StockKey="A|1-A", Quantity=1))
    env.process(issue(env, sess, 1))     # 2 again, LT -> not low
    assert env.stock("A|1-A")["LowStockFlag"] is False


def test_item_create_needs_supervisor_and_creates_no_quantity(env):
    sess = env.login()["sessionId"]
    payload = json.dumps({"ItemID": " k999 ", "ItemName": "New part", "Description": "d", "Manufacturer": "Acme", "LocationCode": "1-A", "MinQty": 1, "MaxQty": 4, "Area": "Cab"})
    r = env.new_request("station1@test", RequestType="ITEM_CREATE", SessionID=sess, StationID="CAB-01", PayloadJson=payload)
    assert env.process(r).response["body"]["status"] == "AwaitingSupervisor"
    assert env.fake.count("POUItems") == 1
    ap = env.new_request("sup@test", RequestType="APPROVE", TargetRequestID=r, Decision="Approve")
    env.process(ap, caller="sup@test")
    b = env.process(r).response["body"]
    assert b["status"] == "Succeeded", b
    s = env.stock("K999|1-A")
    assert s["OnHandQty"] is None and s["BalanceStatus"] == "NoBalance" and s["StockVersion"] == 0 and s["ItemName"] == "New part"
    assert env.c(SITE_OWNER).get_by_key("POUItems", "ItemID", "K999")["ApprovedByUPN"] == "sup@test"
    # idempotent re-run
    assert env.process(r).response["body"]["status"] == "Succeeded"
    assert env.fake.count("POUItems") == 2 and env.fake.count("POUStockLocations") == 2


def test_item_create_rejects_duplicates_bad_location_and_bad_input(env):
    def go(payload, typ="ITEM_CREATE"):
        r = env.new_request("sup@test", RequestType=typ, StationID="CAB-01", PayloadJson=json.dumps(payload))
        return env.process(r, caller="sup@test").response["body"]
    assert go({"ItemID": "A", "ItemName": "dup", "LocationCode": "2-B", "MinQty": 1, "MaxQty": 2})["code"] == "ITEM_EXISTS"
    assert go({"ItemID": "B1", "ItemName": "x", "LocationCode": "ZZZ", "MinQty": 1, "MaxQty": 2})["code"] == "LOCATION_UNKNOWN"
    assert go({"ItemID": "B 1", "ItemName": "x", "LocationCode": "1-A", "MinQty": 1, "MaxQty": 2})["code"] == "PAYLOAD_INVALID"
    assert go({"ItemID": "B1", "ItemName": "x", "LocationCode": "1-A", "MinQty": 5, "MaxQty": 2})["code"] == "PAYLOAD_INVALID"
    assert go({"ItemID": "A", "LocationCode": "1-A", "MinQty": 1, "MaxQty": 2}, "LOCATION_ADD")["code"] == "STOCK_EXISTS"
    assert go({"ItemID": "NOPE", "LocationCode": "1-A", "MinQty": 1, "MaxQty": 2}, "LOCATION_ADD")["code"] == "ITEM_NOT_FOUND"
    # a second location for an existing item (the K102516 scenario) is a LOCATION_ADD
    b = go({"ItemID": "A", "LocationCode": "2-B", "MinQty": 1, "MaxQty": 2}, "LOCATION_ADD")
    assert b["status"] == "Succeeded" and env.stock("A|2-B")["ItemName"] == "Widget"
    assert env.fake.count("POUItems") == 1


def test_param_update_changes_min_max_and_flag_never_quantity(env):
    opening(env)
    r = env.new_request("sup@test", RequestType="PARAM_UPDATE", StationID="CAB-01", StockKey="A|1-A", PayloadJson=json.dumps({"MinQty": 6, "MaxQty": 12}))
    assert env.process(r, caller="sup@test").response["body"]["status"] == "Succeeded"
    s = env.stock("A|1-A")
    assert (s["MinQty"], s["MaxQty"], s["OnHandQty"], s["LowStockFlag"]) == (6, 12, 5, True)
    r = env.new_request("sup@test", RequestType="PARAM_UPDATE", StationID="CAB-01", StockKey="A|1-A", PayloadJson=json.dumps({"Active": False}))
    assert env.process(r, caller="sup@test").response["body"]["code"] == "NONZERO_STOCK"
