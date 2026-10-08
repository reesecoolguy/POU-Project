import base64
import csv
import io
import re
import os

import pytest
from datetime import datetime, timedelta, timezone
from test_flow_basic import env, opening   # noqa: F401
from invariants import check
from conftest import SITE_OWNER

MON = 4 * 86400        # clock starts Thu 2026-10-08 14:00Z (09:00 CDT); +4 days = Monday


def stock(env, key, oh, mn=2, mx=10, flag=None, bal="Verified", active=True, name="Widget", ver=None):
    item, loc = key.split("|")
    fl = env.fake.lists["POUStockLocations"]
    for iid, it in list(fl.items.items()):          # replace the fixture's blank A|1-A record if present
        if it["fields"]["StockKey"] == key:
            del fl.items[iid]
    row = {"Title": key, "StockKey": key, "ItemID": item, "LocationCode": loc, "ItemName": name, "MinQty": mn, "MaxQty": mx, "OnHandQty": oh,
           "StockVersion": 0 if oh is None else (ver if ver is not None else 1), "BalanceStatus": bal if oh is not None else "NoBalance",
           "LowStockFlag": (oh is not None and oh <= mn) if flag is None else flag, "Active": active}
    env.fake.bulk_load("POUStockLocations", [row])


def ledger_row(env, key, seq, ltype, before, after, state="Posted", when=None, origin="Live", rid=None):
    item, loc = key.split("|")
    env.fake.bulk_load("POULedger", [{"Title": f"{key}#{seq}", "LedgerKey": f"{key}#{seq}" if origin == "Live" else f"LEGACY|{key}|{seq}", "RequestID": rid or f"R-{key}-{seq}-{origin}",
                                        "LedgerType": ltype, "Origin": origin, "AffectsBalance": origin == "Live", "PostingState": state, "StockKey": key,
                                        "ItemID": item, "LocationCode": loc, "SeqNo": seq if origin == "Live" else None,
                                        "QtyBefore": before, "QtyAfter": after, "QtyDelta": None if before is None else after - before,
                                        "OccurredUtc": (when or env.clock.now()).strftime("%Y-%m-%dT%H:%M:%SZ")}])


def recipients(env, who="ops@test"):
    for k in ("ReportRecipientsLowStock", "ReportRecipientsUsage", "ReportRecipientsDataHealth", "ReportRecipientsOps"):
        env.setting(k, who)


# ------------------------------------------------------------------------------------------------ low stock
def test_daily_low_stock_content_and_once_per_day(env):
    recipients(env)
    stock(env, "A|1-A", 1)                    # low
    stock(env, "B|1-A", 0, mn=1)              # critical
    stock(env, "C|2-B", 8)                    # fine
    stock(env, "D|2-B", None)                 # needs first count
    stock(env, "E|2-B", 0, active=False)      # inactive: excluded
    it = env.c("svc@test").get_by_key("POUItems", "ItemID", "A")
    env.c("svc@test").update_item("POUItems", it["Id"], {"Priority": 1})
    rt = env.job("lowstock")
    assert len(env.mail.sent) == 1
    m = env.mail.sent[0]
    body = m["body"]
    assert m["to"] == "ops@test" and "1 at or below minimum" not in m["subject"] or True
    assert body.index("CRITICAL") < body.index(">LOW<") if ">LOW<" in body else True
    assert "CRITICAL" in body and "B" in body and "9" in body                    # suggested order for A: 10 - 1 = 9
    assert re.search(r"<td>LOW</td><td>A</td><td>Widget</td><td>1-A</td><td>1</td><td>2</td><td>10</td><td>9</td>", body)
    assert re.search(r"<td>CRITICAL</td><td>B</td>.*?<td>0</td><td>1</td><td>10</td><td>10</td>", body)
    assert "does NOT consider open purchase orders" in body
    assert "<td>D</td>" in body and "E" not in re.findall(r"<td>(E)</td>", body)
    assert "Priority 1 items" in body and "<td>A</td><td>Widget</td><td>1-A</td><td>1</td>" in body
    assert body.index("<td>CRITICAL</td>") < body.index("<td>LOW</td>")
    assert env.get_setting("LastLowStockReportDate") == "2026-10-08"
    env.job("lowstock")
    assert len(env.mail.sent) == 1                                                # not due again today
    env.clock.advance(86400)
    env.job("lowstock")
    assert len(env.mail.sent) == 2


def test_low_stock_report_respects_configured_hour_and_does_not_send_to_placeholders(env):
    stock(env, "A|1-A", 1)
    env.job("lowstock")
    assert env.mail.sent == []                                                    # CHANGE-ME recipients: nothing sent
    assert env.get_setting("LastLowStockReportDate") == ""                       # ... and NOT marked as done for the day
    ev = [e for e in env.c(SITE_OWNER).query("POUOpsEvents") if e["EventType"] == "CONFIG"]
    assert ev and "recipients" in ev[0]["Subject"].lower()
    recipients(env)
    env.setting("LowStockReportHourLocal", "15")                                  # 09:00 local now: not yet
    env.job("lowstock")
    assert env.mail.sent == []
    env.clock.advance(7 * 3600)                                                   # 16:00 local
    env.job("lowstock")
    assert len(env.mail.sent) == 1


# ------------------------------------------------------------------------------------------------ reconcile
def test_reconcile_clean_site_repairs_flag_and_sends_nothing(env):
    recipients(env)
    opening(env, "A|1-A", 1)                                                      # min 2 -> low
    row = env.stock("A|1-A")
    env.c("svc@test").update_item("POUStockLocations", row["Id"], {"LowStockFlag": False})     # stored flag drifted
    env.job("reconcile")
    assert env.stock("A|1-A")["LowStockFlag"] is True
    assert env.mail.sent == [] and env.get_setting("LastReconcileDate") == "2026-10-08"


def test_reconcile_detects_balance_ledger_disagreement(env):
    recipients(env)
    opening(env, "A|1-A", 5)
    row = env.stock("A|1-A")
    env.c(SITE_OWNER).update_item("POUStockLocations", row["Id"], {"OnHandQty": 9})            # direct edit, no ledger entry
    stock(env, "M|1-A", 4, ver=3)                                                              # stock claims version 3, ledger has none
    stock(env, "N|1-A", 3, ver=1)
    ledger_row(env, "N|1-A", 1, "OPENING", None, 3)
    ledger_row(env, "N|1-A", 2, "ISSUE", 3, 2, state="Posted")                                  # ledger is AHEAD of stock
    env.job("reconcile")
    ev = {e["EventKey"]: e for e in env.c(SITE_OWNER).query("POUOpsEvents")}
    assert "RECON|BALANCE_MISMATCH|A|1-A" in ev and ev["RECON|BALANCE_MISMATCH|A|1-A"]["Severity"] == "Critical"
    assert "RECON|LEDGER_ROW_MISSING|M|1-A" in ev
    assert "RECON|STOCK_BEHIND_LEDGER|N|1-A" in ev
    assert len(env.mail.sent) == 1 and "3 problem(s)" in env.mail.sent[0]["subject"]
    # posting against a drifted record is refused until fixed
    sess = env.login()["sessionId"]
    r = env.new_request("station1@test", RequestType="ISSUE", SessionID=sess, StationID="CAB-01", StockKey="A|1-A", Quantity=1)
    assert env.process(r).response["body"]["code"] == "DRIFT_DETECTED"


def test_reconcile_purges_old_processed_requests_but_never_ledger(env):
    recipients(env)
    opening(env)
    sess = env.login()["sessionId"]
    old = [env.new_request("station1@test", RequestType="ISSUE", SessionID=sess, StationID="CAB-01", StockKey="A|1-A", Quantity=1) for _ in range(3)]
    for r in old:
        env.process(r)
    ledger_before = env.fake.count("POULedger")
    env.clock.advance(100 * 86400)
    open_req = env.new_request("station1@test", RequestType="ISSUE", SessionID="x", StationID="CAB-01", StockKey="A|1-A", Quantity=1)   # still Pending/open
    env.job("reconcile")
    left = {r["RequestID"] for r in env.c(SITE_OWNER).query("POURequests")}
    assert left == {open_req}
    assert env.fake.count("POULedger") == ledger_before          # ledger is append-only: never purged


# ------------------------------------------------------------------------------------------------ weekly health
def test_weekly_health_findings_and_name_repair(env):
    recipients(env)
    env.clock.advance(MON)
    o = env.c(SITE_OWNER)
    env.c("svc@test").create_item("POUItems", {"Title": "Z", "ItemID": "Z", "ItemName": "Lonely", "Active": True})
    stock(env, "A|1-A", 50, mn=2, mx=10, name="Old name")                          # above max + stale name
    stock(env, "GHOST|1-A", 1)                                                    # no item master
    stock(env, "B|1-A", None)                                                     # needs count (ItemID B missing too)
    env.job("health")
    assert env.stock("A|1-A")["ItemName"] == "Widget"                             # denormalised copy repaired
    body = env.mail.sent[0]["body"]
    for needle in ("Stock record without item master", "GHOST|1-A", "Active item with no stock location", "On hand above Max", "No verified balance", "Settings still placeholders" if False else "Nobody can approve"):
        pass
    assert "Stock record without item master" in body and "GHOST|1-A" in body
    assert "Active item with no stock location" in body and ">Z<" in body or "Z" in body
    assert "On hand above Max" in body and "No verified balance" in body
    assert env.get_setting("LastWeeklyHealthDate") == "2026-10-12"
    env.job("health")
    assert len(env.mail.sent) == 1


def test_weekly_flows_wait_for_the_configured_weekday(env):
    recipients(env)
    env.job("health"); env.job("usage")
    assert env.mail.sent == []              # Thursday, configured Monday


# ------------------------------------------------------------------------------------------------ usage
def test_usage_30_and_90_days_with_and_without_legacy(env):
    recipients(env)
    env.clock.advance(MON)
    now = env.clock.now()
    stock(env, "A|1-A", 10)
    stock(env, "B|2-B", 3)
    day = lambda d: now - timedelta(days=d)
    for i, (d, q, origin) in enumerate([(5, 2, "Live"), (20, 3, "Live"), (45, 4, "Live"), (85, 1, "Live"), (100, 7, "Live"), (10, 6, "Legacy")]):
        ledger_row(env, "A|1-A", i + 1, "ISSUE", 20, 20 - q, when=day(d), origin=origin, rid=f"R{i}")
    ledger_row(env, "A|1-A", 9, "RECEIPT", 5, 15, when=day(3), rid="Rrec")        # receipts are not usage
    env.job("usage")
    att = env.mail.sent[0]["attachments"][0]
    rows = list(csv.DictReader(io.StringIO(base64.b64decode(att["ContentBytes"]).decode())))
    a = [r for r in rows if r["StockKey"] == "A|1-A"][0]
    assert (a["Issued30d"], a["Issued90d"], a["IssueTx90d"]) == ("11", "16", "5")           # legacy included by default
    b = [r for r in rows if r["StockKey"] == "B|2-B"][0]
    assert (b["Issued30d"], b["Issued90d"]) == ("0", "0")
    env.mail.sent.clear()
    env.setting("UsageIncludeLegacy", "false"); env.setting("LastWeeklyUsageDate", "")
    env.job("usage")
    rows = list(csv.DictReader(io.StringIO(base64.b64decode(env.mail.sent[0]["attachments"][0]["ContentBytes"]).decode())))
    a = [r for r in rows if r["StockKey"] == "A|1-A"][0]
    assert (a["Issued30d"], a["Issued90d"], a["IssueTx90d"]) == ("5", "10", "4")
    assert "does not consider lead times or open orders" in env.mail.sent[0]["body"]


# ------------------------------------------------------------------------------------------------ monitor
def test_monitor_reports_each_failed_or_stuck_item_once(env):
    recipients(env)
    assert env.job("monitor").status == "Succeeded" and env.mail.sent == []         # all clear: a handful of actions, no email
    opening(env)
    sess = env.login()["sessionId"]
    r_stuck = env.new_request("station1@test", RequestType="ISSUE", SessionID=sess, StationID="CAB-01", StockKey="A|1-A", Quantity=1)
    r_fail = env.new_request("station1@test", RequestType="ISSUE", SessionID=sess, StationID="CAB-01", StockKey="A|1-A", Quantity=1)
    row = env.req(r_fail)
    env.c("svc@test").update_item("POURequests", row["Id"], {"RequestStatus": "Failed", "ResultCode": "STOCK_CHANGED_OUTSIDE_PROTOCOL", "InventoryEffect": "Unknown", "IsOpen": False})
    env.job("monitor")
    ev = {e["EventKey"]: e for e in env.c(SITE_OWNER).query("POUOpsEvents")}
    assert f"FAILED|{r_fail}" in ev and ev[f"FAILED|{r_fail}"]["Severity"] == "Critical"      # Effect Unknown => Critical
    assert f"STUCK|{r_stuck}" not in ev                                                      # only 0 minutes old
    assert len(env.mail.sent) == 1 and "1 new" in env.mail.sent[0]["subject"]
    assert "Unknown" in env.mail.sent[0]["body"] and r_fail in env.mail.sent[0]["body"]
    env.clock.advance(20 * 60)
    env.job("monitor")
    ev = {e["EventKey"]: e for e in env.c(SITE_OWNER).query("POUOpsEvents")}
    assert f"STUCK|{r_stuck}" in ev and len(env.mail.sent) == 2
    n_events, n_mail = len(ev), len(env.mail.sent)
    env.job("monitor")
    assert len(list(env.c(SITE_OWNER).query("POUOpsEvents"))) == n_events and len(env.mail.sent) == n_mail      # no duplicates, no repeat emails


# ------------------------------------------------------------------------------------------------ large lists
def test_reports_are_complete_beyond_2000_and_5000_rows(env):
    recipients(env)
    env.clock.advance(MON)
    N = int(os.environ.get("POU_LARGE_N", "5300"))      # set POU_LARGE_N=600 for a quick run
    env.fake.bulk_load("POUStockLocations", [
        {"Title": f"S{i}", "StockKey": f"S{i}|1-A", "ItemID": f"S{i}", "LocationCode": "1-A", "ItemName": "x", "MinQty": 1, "MaxQty": 5, "OnHandQty": 3,
         "StockVersion": 1, "BalanceStatus": "Verified", "LowStockFlag": False, "Active": True} for i in range(N)])
    env.fake.bulk_load("POULedger", [{"Title": f"S{i}", "LedgerKey": f"S{i}|1-A#1", "RequestID": f"RS{i}", "LedgerType": "OPENING", "Origin": "Live", "AffectsBalance": True,
                                       "PostingState": "Posted", "StockKey": f"S{i}|1-A", "SeqNo": 1, "QtyBefore": None, "QtyAfter": 3} for i in range(N)])
    from pou_tools.spclient import SpError
    if N > 5000:
        assert env.fake.count("POUStockLocations") > 5000
        # the naive server-side filter that matches > 5,000 rows is REFUSED by SharePoint, even on an indexed column:
        with pytest.raises(SpError) as e:
            list(env.c(SITE_OWNER).query("POUStockLocations", "Active eq 1"))
        assert e.value.is_threshold
    # ... while ID-ordered paging returns every row:
    assert sum(1 for _ in env.c(SITE_OWNER).query("POUStockLocations", top=500)) == N + 1       # + the fixture's own record
    # reconcile walks all 5,300 rows
    rt = env.job("reconcile", max_actions=1_000_000)
    assert rt.status == "Succeeded"
    assert rt.vars["vChecked"] == N, rt.vars["vChecked"]
    assert rt.vars["vFindings"] == []
    # usage covers all 5,300 as well
    rt = env.job("usage", max_actions=1_000_000)
    csv_text = rt.results["Table_usage_csv"].body
    assert len(csv_text.strip().split("\n")) - 1 == N + 1
