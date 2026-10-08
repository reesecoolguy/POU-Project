"""Scheduled flows: daily low stock, nightly reconcile, weekly data health, weekly usage 30/90, hourly monitor.

All are hourly (or faster) 'ticks' that do a handful of actions unless due, so schedules, recipients and the time zone are
configuration (POUSettings), not flow edits. Every list read follows __next, so results stay complete past 2,000 / 5,000 rows.
Replenishment output is a SUGGESTION (Max - OnHand). No purchase-order or open-order data exists here, so none is considered.
"""
from __future__ import annotations

from .common import (DEFAULT_SITE_URL, L_EMPLOYEES, L_ITEMS, L_LEDGER, L_OPS, L_REQUESTS, L_SESSIONS, L_SETTINGS, L_STATIONS, L_STOCK,
                     cfg, cfgb, cfgi, load_settings, ops_event, preamble)
from .dsl import ALL, Block, Ex, Flow, X, and_, b, cat, coalesce, eq, f, if_, is_null, not_, nz, o, or_, qv, recurrence, v
from .helpers import local_fmt, ops_event_once, paged, recipients_ok, save_setting, send_report, tick_gate

HTML_CELL = "padding:2px 8px;border:1px solid #bbb"
ISO = "yyyy-MM-ddTHH:mm:ssZ"


def _html(title: str, intro: str, tables: list[tuple[str, Ex]], footer: str) -> str:
    parts = [f"<html><body style='font-family:Segoe UI,Arial,sans-serif;font-size:13px'><h3>{title}</h3><p>{intro}</p>"]
    out = ["@concat('" + parts[0].replace("'", "''") + "'"]
    for head, tbl in tables:
        out.append(", '<h4>" + head.replace("'", "''") + "</h4>', " + str(tbl))
    out.append(", '<p style=\"color:#555\">" + footer.replace("'", "''") + "</p></body></html>')")
    return "".join(out)


def _col(header: str, expr: str) -> dict:
    return {"header": header, "value": X(expr)}


# =====================================================================================================================
def build_lowstock(site_url: str = DEFAULT_SITE_URL) -> Flow:
    fl = Flow("POU-DailyLowStock", "POU - Daily low stock report", "Hourly tick; sends once per day at the configured local hour. Replenishment SUGGESTIONS only.", recurrence(hours=1))
    root = preamble(fl, site_url)
    load_settings(root)
    tick_gate(root, "LowStockReportHourLocal", "LastLowStockReportDate")
    for n, t, val in [("vLow", "array", []), ("vLowNext", "string", ""), ("vNoBal", "array", []), ("vNoBalNext", "string", ""), ("vP1", "array", [])]:
        root.init_var(n, t, val)
    sel = "StockKey,ItemID,ItemName,LocationCode,OnHandQty,MinQty,MaxQty,BalanceStatus"
    paged(root, "Low", L_STOCK, ["LowStockFlag eq 1 and Active eq 1"], sel, "vLow", "vLowNext", orderby="LocationCode,ItemID")
    paged(root, "NoBal", L_STOCK, ["BalanceStatus eq 'NoBalance' and Active eq 1"], sel, "vNoBal", "vNoBalNext", orderby="LocationCode,ItemID")
    root.select("Select_low_rows", X("variables('vLow')"), {
        "Item": X("item()?['ItemID']"), "Name": X("item()?['ItemName']"), "Location": X("item()?['LocationCode']"),
        "OnHand": X("item()?['OnHandQty']"), "Min": X("item()?['MinQty']"), "Max": X("item()?['MaxQty']"),
        "SuggestedOrder": X("if(less(sub(coalesce(item()?['MaxQty'], 0), coalesce(item()?['OnHandQty'], 0)), 0), 0, sub(coalesce(item()?['MaxQty'], 0), coalesce(item()?['OnHandQty'], 0)))"),
        "Status": X("if(equals(coalesce(item()?['OnHandQty'], 0), 0), 'CRITICAL', 'LOW')")})
    root.filter_array("Filter_critical", X("body('Select_low_rows')"), X("equals(item()?['Status'], 'CRITICAL')"))
    root.filter_array("Filter_low", X("body('Select_low_rows')"), X("equals(item()?['Status'], 'LOW')"))
    root.compose("Compose_ordered_rows", X("union(body('Filter_critical'), body('Filter_low'))"))
    cols = [_col(h, f"item()?['{k}']") for h, k in [("Status", "Status"), ("Item", "Item"), ("Name", "Name"), ("Location", "Location"),
                                                      ("On hand", "OnHand"), ("Min", "Min"), ("Max", "Max"), ("Suggested order qty (Max - On hand)", "SuggestedOrder")]]
    root.table("Table_low", X("outputs('Compose_ordered_rows')"), "HTML", cols)
    root.select("Select_nobal_rows", X("variables('vNoBal')"), {"Item": X("item()?['ItemID']"), "Name": X("item()?['ItemName']"), "Location": X("item()?['LocationCode']")})
    root.table("Table_nobal", X("body('Select_nobal_rows')"), "HTML", [_col(h, f"item()?['{k}']") for h, k in [("Item", "Item"), ("Name", "Name"), ("Location", "Location")]])
    # Priority 1 items on hand (requirement noted on the original Inventory sheet). Priority is blank in the workbook, so this is empty until populated.
    root.sp_get("Get_priority1_items", L_ITEMS, ["Priority eq 1 and Active eq 1"], select="ItemID,ItemName", top=200)

    def p1(b: Block):
        b.sp_get("Get_p1_stock", L_STOCK, ["ItemID eq '", qv(Ex("items('For_each_p1_item')?['ItemID']")), "' and Active eq 1"], select=sel, top=50)
        b.set_var("vP1", X("union(variables('vP1'), coalesce(body('Get_p1_stock')?['d']?['results'], createArray()))"), name="Append_p1_rows")
    root.foreach("For_each_p1_item", X("body('Get_priority1_items')?['d']?['results']"), p1)
    root.table("Table_p1", X("variables('vP1')"), "HTML", [_col(h, f"item()?['{k}']") for h, k in [("Item", "ItemID"), ("Name", "ItemName"), ("Location", "LocationCode"), ("On hand", "OnHandQty"), ("Min", "MinQty"), ("Max", "MaxQty")]])
    root.compose("Compose_counts", X("concat(string(length(variables('vLow'))), ' at or below minimum (', string(length(body('Filter_critical'))), ' CRITICAL = zero on hand); ', string(length(variables('vNoBal'))), ' need a first count')"))
    root.compose("Compose_body", _html(
        "POU low stock - daily",
        "Rule: LowStockRule setting (LE = on hand <= min, LT = on hand < min). <b>Suggested order quantity is a suggestion only (Max - On hand). "
        "It does NOT consider open purchase orders: this system holds no order data.</b>",
        [("Low stock", b("Table_low")), ("Needs a first count (no verified balance - not counted as low stock)", b("Table_nobal")), ("Priority 1 items - on hand", b("Table_p1"))],
        "Generated by POU-DailyLowStock. Counts: see subject. Change recipients/time in the POUSettings list."))
    send_report(root, "Send_low_stock_email", "ReportRecipientsLowStock", X("concat('POU low stock ', outputs('Compose_LocalDate'), ': ', outputs('Compose_counts'))"),
                X(o("Compose_body")),
                after_send=lambda a: save_setting(a, "LastLowStockReportDate", X(o("Compose_LocalDate")), ""),
                otherwise=lambda e: ops_event(e, "NoRcpt", "REPORT_RECIPIENTS_LOWSTOCK", "CONFIG", "Warning", "Low-stock report recipients not configured",
                                              "Setting ReportRecipientsLowStock is empty or still CHANGE-ME@... so the daily report was not emailed."))
    return fl


# =====================================================================================================================
def build_reconcile(site_url: str = DEFAULT_SITE_URL) -> Flow:
    fl = Flow("POU-Reconcile", "POU - Nightly balance-to-ledger reconciliation",
              "Hourly tick; once per night: proves OnHandQty == the ledger row for StockVersion, repairs LowStockFlag, raises ops events, purges old requests/sessions.", recurrence(hours=1))
    root = preamble(fl, site_url)
    load_settings(root)
    tick_gate(root, "ReconcileHourLocal", "LastReconcileDate")
    for n, t, val in [("vStock", "array", []), ("vStockNext", "string", ""), ("vFindings", "array", []), ("vFixed", "integer", 0), ("vChecked", "integer", 0)]:
        root.init_var(n, t, val)
    paged(root, "Stock", L_STOCK, None, "Id,StockKey,ItemID,OnHandQty,StockVersion,MinQty,LowStockFlag,BalanceStatus,Active", "vStock", "vStockNext")
    root.filter_array("Filter_rows_to_check", X("variables('vStock')"),
                      X("and(equals(item()?['Active'], true), not(and(equals(coalesce(item()?['StockVersion'], 0), 0), equals(item()?['OnHandQty'], null), equals(coalesce(item()?['LowStockFlag'], false), false))))"))

    def per_row(b: Block):
        it = lambda k: Ex(f"items('For_each_stock')?['{k}']")
        ver = Ex(f"int(coalesce({it('StockVersion')}, 0))")
        b.inc_var("vChecked", 1, name="Count_checked")
        b.sp_get("Get_ledger_pair", L_LEDGER,
                 ["LedgerKey eq '", qv(cat(it("StockKey"), "#", f("string", ver))), "' or LedgerKey eq '", qv(cat(it("StockKey"), "#", f("string", f("add", ver, 1)))), "'"],
                 select="LedgerKey,SeqNo,PostingState,QtyAfter,Created", top=5)
        b.filter_array("Pick_current", X("body('Get_ledger_pair')?['d']?['results']"), X(f"equals(item()?['SeqNo'], {ver})"))
        b.filter_array("Pick_next", X("body('Get_ledger_pair')?['d']?['results']"), X(f"equals(item()?['SeqNo'], add({ver}, 1))"))
        cur, nxt = Ex("first(body('Pick_current'))"), Ex("first(body('Pick_next'))")
        oh = it("OnHandQty")
        b.compose("Compose_problem", X(
            f"if(and(equals({ver}, 0), not(equals({oh}, null))), 'BALANCE_WITHOUT_LEDGER', "
            f"if(and(greater({ver}, 0), equals({cur}, null)), 'LEDGER_ROW_MISSING', "
            f"if(and(greater({ver}, 0), not(equals({cur}, null)), not(equals({cur}?['QtyAfter'], {oh}))), 'BALANCE_MISMATCH', "
            f"if(and(not(equals({nxt}, null)), equals({nxt}?['PostingState'], 'Posted')), 'STOCK_BEHIND_LEDGER', "
            f"if(and(not(equals({nxt}, null)), greater(sub(ticks(utcNow()), ticks(coalesce({nxt}?['Created'], utcNow()))), mul({cfgi('StaleIntentMinutes', 5)}, 12000000000))), 'STALE_INTENT', '')))))"))
        b.cond("If_problem", nz(o("Compose_problem")), lambda p: (
            ops_event(p, "Rec", cat("RECON|", o("Compose_problem"), "|", it("StockKey")), "RECONCILE", "Critical",
                      cat(o("Compose_problem"), ": ", it("StockKey")),
                      cat("On hand ", f("string", oh), ", stock version ", f("string", ver), ". Ledger row at that version: ",
                          f("string", Ex(f"coalesce({cur}?['QtyAfter'], 'none')")), ". Posting for this record is blocked until resolved (see docs/10_Maintenance.md).")),
            p.add("Add_finding", {"type": "AppendToArrayVariable", "inputs": {"name": "vFindings", "value": {
                "severity": "Critical", "area": "Balance vs ledger", "item": X(it("StockKey")), "detail": X(o("Compose_problem"))}}}, always=True)))
        # LowStockFlag is a STORED derived value (so Power Apps can filter on it with delegation): repair drift
        minq = it("MinQty")
        expected = f"and(not(equals({oh}, null)), not(equals({minq}, null)), if(equals({cfg('LowStockRule')}, 'LT'), less(coalesce({oh}, 0), coalesce({minq}, 0)), lessOrEquals(coalesce({oh}, 0), coalesce({minq}, 0))))"
        b.compose("Compose_expected_flag", X(expected))
        b.cond("If_flag_wrong", Ex(f"not(equals(coalesce({it('LowStockFlag')}, false), outputs('Compose_expected_flag')))"), lambda p: (
            p.attempt("Fix_flag", lambda s, n: s.sp_update(n, L_STOCK, X(it("Id")), {"LowStockFlag": X(o("Compose_expected_flag"))},
                                                           etag=X(Ex("items('For_each_stock')?['__metadata']?['etag']")))),
            p.cond("If_flag_fixed", Ex("equals(actions('Fix_flag')?['status'], 'Succeeded')"), lambda q: q.inc_var("vFixed", 1, name="Count_fixed"), always=True)))
    root.foreach("For_each_stock", X("body('Filter_rows_to_check')"), per_row)

    # retention: ledger rows are never deleted; processed requests and old sessions are
    root.compose("Compose_req_cutoff", X(f"addDays(utcNow(), mul(-1, {cfgi('RequestRetentionDays', 90)}), '{ISO}')"))
    root.compose("Compose_sess_cutoff", X(f"addDays(utcNow(), mul(-1, {cfgi('SessionRetentionDays', 30)}), '{ISO}')"))
    root.sp_get("Get_old_requests", L_REQUESTS, ["Created lt datetime'", o("Compose_req_cutoff"), "' and IsOpen eq 0"], select="Id", top=300)
    root.foreach("For_each_old_request", X("body('Get_old_requests')?['d']?['results']"),
                 lambda b: b.sp_delete("Purge_request", L_REQUESTS, X("items('For_each_old_request')?['Id']")))
    root.sp_get("Get_old_sessions", L_SESSIONS, ["Created lt datetime'", o("Compose_sess_cutoff"), "' and SessionState ne 'Active'"], select="Id", top=300, always=True)
    root.foreach("For_each_old_session", X("body('Get_old_sessions')?['d']?['results']"),
                 lambda b: b.sp_delete("Purge_session", L_SESSIONS, X("items('For_each_old_session')?['Id']")))
    root.table("Table_findings", X("variables('vFindings')"), "HTML", [_col(h, f"item()?['{k}']") for h, k in [("Severity", "severity"), ("Area", "area"), ("Item", "item"), ("Detail", "detail")]], always=True)
    root.cond("If_any_findings", Ex("greater(length(variables('vFindings')), 0)"), lambda t: send_report(
        t, "Send_reconcile_email", "ReportRecipientsDataHealth",
        X("concat('POU reconciliation ', outputs('Compose_LocalDate'), ': ', string(length(variables('vFindings'))), ' problem(s)')"),
        _html("POU nightly reconciliation", "These stock records do not match their ledger. Posting is blocked for them until fixed.",
              [("Findings", b("Table_findings"))], "Checked rows: see POUOpsEvents for history. Never edit OnHandQty directly: post an ADJUSTMENT or AUDIT.")))
    save_setting(root, "LastReconcileDate", X(o("Compose_LocalDate")), "")
    return fl


# =====================================================================================================================
def build_health(site_url: str = DEFAULT_SITE_URL) -> Flow:
    fl = Flow("POU-WeeklyHealth", "POU - Weekly data-health check",
              "Hourly tick; once per week: orphans, parameters, roles, placeholders; repairs the denormalised ItemName.", recurrence(hours=1))
    root = preamble(fl, site_url)
    load_settings(root)
    tick_gate(root, "WeeklyHourLocal", "LastWeeklyHealthDate", weekly=True)
    for n, t, val in [("vItems", "array", []), ("vItemsNext", "string", ""), ("vStock", "array", []), ("vStockNext", "string", ""),
                      ("vFindings", "array", []), ("vNameFixed", "integer", 0)]:
        root.init_var(n, t, val)
    paged(root, "Items", L_ITEMS, None, "Id,ItemID,ItemName,Active", "vItems", "vItemsNext")
    paged(root, "Stock", L_STOCK, None, "Id,StockKey,ItemID,ItemName,OnHandQty,MinQty,MaxQty,BalanceStatus,Active", "vStock", "vStockNext")
    root.sp_get("Get_employees", L_EMPLOYEES, None, select="BadgeID,Active,Role,MicrosoftUPN", top=500, always=True)
    root.sp_get("Get_stations", L_STATIONS, None, select="StationID,Active", top=200, always=True)
    root.select("Select_item_ids", X("variables('vItems')"), X("toUpper(item()?['ItemID'])"))
    root.select("Select_stock_item_ids", X("variables('vStock')"), X("toUpper(item()?['ItemID'])"))

    def finding(b: Block, name: str, sev: str, area: str, item, detail):
        b.add(name, {"type": "AppendToArrayVariable", "inputs": {"name": "vFindings", "value": {"severity": sev, "area": area, "item": item, "detail": detail}}}, always=True)

    # --- referential integrity
    root.filter_array("Filter_orphan_stock", X("variables('vStock')"), X("not(contains(body('Select_item_ids'), toUpper(item()?['ItemID'])))"))
    root.select("Select_orphan_keys", X("body('Filter_orphan_stock')"), X("item()?['StockKey']"), always=True)
    root.cond("If_orphan_stock", Ex("greater(length(body('Filter_orphan_stock')), 0)"), lambda t: finding(
        t, "Find_orphan_stock", "Critical", "Stock record without item master", Ex("join(take(body('Select_orphan_keys'), 20), ', ')"),
        X("concat(string(length(body('Filter_orphan_stock'))), ' stock record(s) have an ItemID missing from POUItems.')")), always=True)
    root.filter_array("Filter_items_without_stock", X("variables('vItems')"), X("and(equals(item()?['Active'], true), not(contains(body('Select_stock_item_ids'), toUpper(item()?['ItemID']))))"), always=True)
    root.select("Select_items_without_stock", X("body('Filter_items_without_stock')"), X("item()?['ItemID']"))
    root.cond("If_items_without_stock", Ex("greater(length(body('Filter_items_without_stock')), 0)"), lambda t: finding(
        t, "Find_items_without_stock", "Warning", "Active item with no stock location", Ex("join(take(body('Select_items_without_stock'), 20), ', ')"),
        X("concat(string(length(body('Filter_items_without_stock'))), ' active item(s) have no stocking location.')")), always=True)

    # --- denormalised ItemName repair (non-quantity field; ETag-protected)
    def fix_name(b: Block):
        it = lambda k: Ex(f"items('For_each_stock')?['{k}']")
        b.filter_array("Filter_item_for_stock", X("variables('vItems')"), X(f"equals(toUpper(item()?['ItemID']), toUpper({it('ItemID')}))"))
        b.compose("Compose_master_name", X("first(body('Filter_item_for_stock'))?['ItemName']"))
        b.cond("If_name_differs", Ex(f"and(not(equals(outputs('Compose_master_name'), null)), not(equals(coalesce({it('ItemName')}, ''), outputs('Compose_master_name'))))"), lambda p: (
            p.attempt("Fix_name", lambda s, n: s.sp_update(n, L_STOCK, X(it("Id")), {"ItemName": X(o("Compose_master_name"))},
                                                           etag=X(Ex("items('For_each_stock')?['__metadata']?['etag']")))),
            p.cond("If_name_fixed", Ex("equals(actions('Fix_name')?['status'], 'Succeeded')"), lambda q: q.inc_var("vNameFixed", 1, name="Count_name_fixed"), always=True)))
    root.foreach("For_each_stock", X("variables('vStock')"), fix_name, concurrency=1)

    # --- parameter sanity (counts only: no loops)
    root.filter_array("Filter_onhand_above_max", X("variables('vStock')"), X("and(equals(item()?['Active'], true), not(equals(item()?['OnHandQty'], null)), greater(coalesce(item()?['OnHandQty'], 0), coalesce(item()?['MaxQty'], 0)))"), always=True)
    root.filter_array("Filter_min_gt_max", X("variables('vStock')"), X("and(equals(item()?['Active'], true), greater(coalesce(item()?['MinQty'], 0), coalesce(item()?['MaxQty'], 0)))"))
    root.filter_array("Filter_max_zero", X("variables('vStock')"), X("and(equals(item()?['Active'], true), equals(coalesce(item()?['MaxQty'], 0), 0))"))
    root.filter_array("Filter_no_balance", X("variables('vStock')"), X("and(equals(item()?['Active'], true), equals(item()?['BalanceStatus'], 'NoBalance'))"))
    for nm, sev, area, msg in [("onhand_above_max", "Info", "On hand above Max", " record(s) hold more than Max (not capped; review at next count)."),
                               ("min_gt_max", "Warning", "Min above Max", " record(s) have Min greater than Max."),
                               ("max_zero", "Warning", "Max is zero", " record(s) have Max = 0 so suggested order is always 0."),
                               ("no_balance", "Warning", "No verified balance", " record(s) have no counted quantity: they cannot be issued or received until a supervisor counts them.")]:
        root.select(f"Select_{nm}_keys", X(f"body('Filter_{nm}')"), X("item()?['StockKey']"))
        root.cond(f"If_{nm}", Ex(f"greater(length(body('Filter_{nm}')), 0)"), (lambda nm, sev, area, msg: lambda t: finding(
            t, f"Find_{nm}", sev, area, Ex(f"join(take(body('Select_{nm}_keys'), 15), ', ')"), X(f"concat(string(length(body('Filter_{nm}'))), '{msg}')")))(nm, sev, area, msg), always=True)

    # --- people and configuration
    root.filter_array("Filter_approvers", X("body('Get_employees')?['d']?['results']"), X("and(equals(item()?['Active'], true), not(equals(item()?['Role'], 'Operator')), not(empty(coalesce(item()?['MicrosoftUPN'], ''))))"), always=True)
    root.cond("If_no_approvers", Ex("equals(length(body('Filter_approvers')), 0)"), lambda t: finding(
        t, "Find_no_approvers", "Critical", "Nobody can approve", "(all)", "No Active Supervisor/Admin has a MicrosoftUPN, so audits, new items and adjustments can never be approved."), always=True)
    root.select("Select_approver_upns", X("body('Filter_approvers')"), X("toLower(item()?['MicrosoftUPN'])"))
    root.cond("If_duplicate_upns", Ex("greater(length(body('Select_approver_upns')), length(union(body('Select_approver_upns'), createArray())))"), lambda t: finding(
        t, "Find_duplicate_upns", "Warning", "Duplicate MicrosoftUPN", "(employees)", "Two approvers share the same Microsoft account."), always=True)
    root.filter_array("Filter_active_stations", X("body('Get_stations')?['d']?['results']"), X("equals(item()?['Active'], true)"), always=True)
    root.cond("If_no_stations", Ex("equals(length(body('Filter_active_stations')), 0)"), lambda t: finding(
        t, "Find_no_stations", "Critical", "No active station", "(all)", "No station is Active in POUStations; every login will be refused."), always=True)
    root.filter_array("Filter_placeholder_settings", X("body('Get_settings')?['d']?['results']"), X("contains(coalesce(item()?['SettingValue'], ''), 'CHANGE-ME')"), always=True)
    root.select("Select_placeholder_keys", X("body('Filter_placeholder_settings')"), X("item()?['SettingKey']"))
    root.cond("If_placeholders", Ex("greater(length(body('Filter_placeholder_settings')), 0)"), lambda t: finding(
        t, "Find_placeholders", "Warning", "Settings still placeholders", Ex("join(body('Select_placeholder_keys'), ', ')"), "Report recipients are not configured, so reports are not being emailed."), always=True)
    root.compose("Compose_summary", X("concat(string(length(variables('vStock'))), ' stock records, ', string(length(variables('vItems'))), ' items checked; ', string(variables('vNameFixed')), ' item name(s) repaired; ', string(length(variables('vFindings'))), ' finding(s)')"), always=True)
    root.table("Table_findings", X("variables('vFindings')"), "HTML", [_col(h, f"item()?['{k}']") for h, k in [("Severity", "severity"), ("Area", "area"), ("Item(s)", "item"), ("Detail", "detail")]])
    send_report(root, "Send_health_email", "ReportRecipientsDataHealth", X("concat('POU weekly data health ', outputs('Compose_LocalDate'), ': ', outputs('Compose_summary'))"),
                _html("POU weekly data-health report", "Counts and findings from the whole item master and stock-location list.", [("Findings", b("Table_findings"))],
                      "Nothing is changed by this report except repairing the denormalised ItemName on stock records."),
                after_send=lambda a: save_setting(a, "LastWeeklyHealthDate", X(o("Compose_LocalDate")), ""))
    return fl


# =====================================================================================================================
def build_usage(site_url: str = DEFAULT_SITE_URL) -> Flow:
    fl = Flow("POU-WeeklyUsage", "POU - Weekly usage by item/location (30 and 90 days)",
              "Hourly tick; once per week. For every active stock record: units ISSUED in the last 30 and 90 days, from the ledger.", recurrence(hours=1))
    root = preamble(fl, site_url)
    load_settings(root)
    tick_gate(root, "WeeklyHourLocal", "LastWeeklyUsageDate", weekly=True)
    for n, t, val in [("vStock", "array", []), ("vStockNext", "string", ""), ("vUsage", "array", [])]:
        root.init_var(n, t, val)
    paged(root, "Stock", L_STOCK, None, "StockKey,ItemID,ItemName,LocationCode,OnHandQty,MinQty,MaxQty,Active", "vStock", "vStockNext")
    root.filter_array("Filter_active_stock", X("variables('vStock')"), X("equals(item()?['Active'], true)"))
    root.compose("Compose_d30", X(f"addDays(utcNow(), -30, '{ISO}')"))
    root.compose("Compose_d90", X(f"addDays(utcNow(), -90, '{ISO}')"))
    legacy = cfgb("UsageIncludeLegacy", "true")

    def per_stock(b: Block):
        it = lambda k: Ex(f"items('For_each_usage_stock')?['{k}']")
        b.sp_get("Get_issues90", L_LEDGER,
                 ["StockKey eq '", qv(it("StockKey")), "' and LedgerType eq 'ISSUE' and PostingState eq 'Posted' and OccurredUtc ge datetime'", o("Compose_d90"), "'"],
                 select="QtyDelta,OccurredUtc,Origin", top=500)
        b.compose("Compose_rows90", X("body('Get_issues90')?['d']?['results']"))
        b.filter_array("Filter_rows90", X("outputs('Compose_rows90')"), X(f"or({legacy}, equals(item()?['Origin'], 'Live'))"))
        b.filter_array("Filter_rows30", X("body('Filter_rows90')"), X("greaterOrEquals(item()?['OccurredUtc'], outputs('Compose_d30'))"))
        b.select("Select_q90", X("body('Filter_rows90')"), X("sub(0, int(coalesce(item()?['QtyDelta'], 0)))"))
        b.select("Select_q30", X("body('Filter_rows30')"), X("sub(0, int(coalesce(item()?['QtyDelta'], 0)))"))
        b.compose("Compose_sum90", X("xpath(xml(json(concat('{\"r\":{\"q\":', string(body('Select_q90')), '}}'))), 'sum(//q)')"))
        b.compose("Compose_sum30", X("xpath(xml(json(concat('{\"r\":{\"q\":', string(body('Select_q30')), '}}'))), 'sum(//q)')"))
        b.compose("Compose_usage_row", {
            "stockKey": X(it("StockKey")), "item": X(it("ItemID")), "name": X(f"coalesce({it('ItemName')}, '')"), "location": X(it("LocationCode")),
            "onHand": X(it("OnHandQty")), "issued30": X("outputs('Compose_sum30')"), "issued90": X("outputs('Compose_sum90')"),
            "tx90": X("length(body('Filter_rows90'))")})
        b.set_var("vUsage", X("union(variables('vUsage'), createArray(outputs('Compose_usage_row')))"), name="Append_usage_row")
    root.foreach("For_each_usage_stock", X("body('Filter_active_stock')"), per_stock)
    root.filter_array("Filter_used", X("variables('vUsage')"), X("greater(item()?['issued90'], 0)"))
    cols = [_col(h, f"item()?['{k}']") for h, k in [("Item", "item"), ("Name", "name"), ("Location", "location"), ("On hand", "onHand"), ("Issued 30 days", "issued30"),
                                                      ("Issued 90 days", "issued90"), ("Issue transactions (90d)", "tx90")]]
    root.table("Table_usage_html", X("body('Filter_used')"), "HTML", cols)
    root.table("Table_usage_csv", X("variables('vUsage')"), "CSV", [_col(h, f"item()?['{k}']") for h, k in
                                                                    [("StockKey", "stockKey"), ("Item", "item"), ("Name", "name"), ("Location", "location"), ("OnHand", "onHand"), ("Issued30d", "issued30"), ("Issued90d", "issued90"), ("IssueTx90d", "tx90")]])
    root.compose("Compose_usage_summary", X("concat(string(length(variables('vUsage'))), ' stock records; ', string(length(body('Filter_used'))), ' with issues in the last 90 days')"))
    send_report(root, "Send_usage_email", "ReportRecipientsUsage", X("concat('POU usage 30/90 days ', outputs('Compose_LocalDate'), ': ', outputs('Compose_usage_summary'))"),
                _html("POU usage by item/location", "Units ISSUED (removed) per stock record. Source: ledger rows with LedgerType=ISSUE and PostingState=Posted. "
                      "UsageIncludeLegacy controls whether pre-cutover workbook history is included. The attached CSV has every stock record; sort it by Issued90d.",
                      [("Items issued in the last 90 days (list is ordered by item, then location)", b("Table_usage_html"))],
                      "Usage is demand history, not a purchase recommendation: it does not consider lead times or open orders."),
                attachments=[{"Name": "POU_usage_30_90.csv", "ContentBytes": X("base64(body('Table_usage_csv'))")}],
                after_send=lambda a: save_setting(a, "LastWeeklyUsageDate", X(o("Compose_LocalDate")), ""))
    return fl


# =====================================================================================================================
def build_monitor(site_url: str = DEFAULT_SITE_URL) -> Flow:
    fl = Flow("POU-Monitor", "POU - Failed / stuck request monitor", "Hourly: raises ONE ops event (and one email) per failed or stuck request / ledger intent.", recurrence(hours=1))
    root = preamble(fl, site_url)
    root.sp_get("Probe_problem_requests", L_REQUESTS,
                ["RequestStatus eq 'Failed' or RequestStatus eq 'Pending' or RequestStatus eq 'Processing' or RequestStatus eq 'AwaitingSupervisor'"],
                select="Id,RequestID,RequestType,RequestStatus,Created,ClaimedUtc,ResultCode,InventoryEffect,StockKey", top=200)
    root.sp_get("Probe_open_intents", L_LEDGER, ["PostingState eq 'Intent'"], select="LedgerKey,RequestID,StockKey,Created", top=100)
    root.compose("Compose_nothing", X("and(empty(body('Probe_problem_requests')?['d']?['results']), empty(body('Probe_open_intents')?['d']?['results']))"))
    root.cond("If_nothing_to_report", eq(o("Compose_nothing"), True), lambda t: t.terminate("Stop_all_clear", "Succeeded"))
    load_settings(root)
    root.init_var("vNew", "array", [])
    age = lambda ts: f"sub(ticks(utcNow()), ticks({ts}))"

    def per_request(b: Block):
        it = lambda k: Ex(f"items('For_each_problem_request')?['{k}']")
        b.compose("Compose_class", X(
            f"if(equals({it('RequestStatus')}, 'Failed'), 'FAILED', "
            f"if(and(equals({it('RequestStatus')}, 'AwaitingSupervisor'), greater({age(str(it('Created')))}, 288000000000)), 'WAITING_APPROVAL', "
            f"if(and(or(equals({it('RequestStatus')}, 'Pending'), equals({it('RequestStatus')}, 'Processing')), greater({age(str(it('Created')))}, 9000000000)), 'STUCK', '')))"))
        b.cond("If_reportable", nz(o("Compose_class")), lambda p: ops_event_once(
            p, "Req", cat(o("Compose_class"), "|", it("RequestID")), cat("REQUEST_", o("Compose_class")),
            if_(eq(it("InventoryEffect"), "Unknown"), "Critical", if_(eq(o("Compose_class"), "FAILED"), "Warning", "Warning")),
            cat(o("Compose_class"), " request ", it("RequestType"), " ", f("string", coalesce(it("StockKey"), ""))),
            cat("RequestID ", it("RequestID"), " status ", it("RequestStatus"), " result ", f("string", coalesce(it("ResultCode"), "")),
                " effect ", f("string", coalesce(it("InventoryEffect"), "(none yet)")), ". Created ", it("Created"), "."), "vNew"))
    root.foreach("For_each_problem_request", X("body('Probe_problem_requests')?['d']?['results']"), per_request)

    def per_intent(b: Block):
        it = lambda k: Ex(f"items('For_each_open_intent')?['{k}']")
        b.cond("If_intent_old", Ex(f"greater({age(str(it('Created')))}, 9000000000)"), lambda p: ops_event_once(
            p, "Int", cat("INTENT|", it("LedgerKey")), "LEDGER_INTENT_STUCK", "Critical", cat("Ledger intent not completed: ", it("LedgerKey")),
            cat("Intent ", it("LedgerKey"), " for request ", it("RequestID"), " has been open since ", it("Created"), ". The sweeper should have finished it."), "vNew"))
    root.foreach("For_each_open_intent", X("body('Probe_open_intents')?['d']?['results']"), per_intent, always=True)
    root.table("Table_new", X("variables('vNew')"), "HTML", [_col(h, f"item()?['{k}']") for h, k in [("Severity", "severity"), ("Type", "type"), ("What", "subject"), ("Details", "details")]], always=True)
    root.cond("If_any_new", Ex("greater(length(variables('vNew')), 0)"), lambda t: send_report(
        t, "Send_ops_email", "ReportRecipientsOps", X("concat('POU ALERT: ', string(length(variables('vNew'))), ' new failed/stuck item(s)')"),
        _html("POU failed / stuck requests", "Each item below was newly detected. Inventory Effect = Applied means the quantity DID change.",
              [("New findings", b("Table_new"))], "Resolve in the POUOpsEvents list (tick Resolved). See docs/10_Maintenance.md for each EventType."),
        otherwise=lambda e: ops_event(e, "NoRcptOps", "REPORT_RECIPIENTS_OPS", "CONFIG", "Warning", "Ops alert recipients not configured",
                                      "Setting ReportRecipientsOps is empty or still CHANGE-ME@... so failed/stuck alerts are only visible in POUOpsEvents.")), always=True)
    return fl
