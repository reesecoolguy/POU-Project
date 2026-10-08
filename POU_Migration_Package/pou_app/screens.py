"""The screens. Each function returns a Screen. All logic is Power Fx; nothing here is executed by Python."""
from __future__ import annotations

from . import formulas as F
from .spec import Ctl, Screen
from .widgets import (AMBER, BLUE, CLEAR, GREEN, GREY, INK, NAVY, RED, WHITE, act, banner, btn, card, header, inp, lbl, picker, rect, runner, tmr)

SCREEN_PROPS = {"Fill": "RGBA(242, 242, 242, 1)"}
OPERATOR_GUARD = "If(IsBlank(varSession) And Not(varSupMode), Navigate(scrLogin, ScreenTransition.None))"

ADD_EDIT = "If(IsBlank(varReq) And Not(varBusy), DisplayMode.Edit, DisplayMode.Disabled)"


def qty_cell(p):  # the quantity text, trimmed
    return f"Trim(txtQty{p}.Text)"


def _scan_finish(p: str) -> str:
    """After a terminal answer on the Add/Remove screen: clear the entry; keep the item selected when the answer was a rejection."""
    return F.finish_common(
        f"""Reset(txtQty{p});
If(
    varOutKind = "bad",
    UpdateContext({{locSel: IfError(LookUp(POUStockLocations, StockKey = locSel.StockKey), locSel)}}),
    Reset(txtItem{p}); Reset(txtLoc{p}); Clear(colStock); UpdateContext({{locSel: Blank()}}); SetFocus(txtItem{p})
);
If(varOutKind = "ok" And varLogoutAfter, {F.logout_block()})""")


# =====================================================================================================================
def scr_login() -> Screen:
    badge_fn = f"""{F.ACT};
UpdateContext({{locBadgePending: false}});
If(
    varBusy Or IsBlank(varStation),
    false,
    With(
        {{b: Substitute(Trim(txtBadge.Text), "*", "")}},
        If(
            Len(b) < varScanMin,
            Set(varLoginMsg, "Scan your badge."),
            Set(varBusy, true);
            Reset(txtBadge);
            Set(varLogin, IfError(
                {F.SESSION_FLOW}.Run("LOGIN", b, varStation, "", Lower(User().Email)),
                {{ok: "no", code: "NETWORK", message: "Could not reach the server, so you are NOT signed in. Try again.", sessionId: "", employeeName: "", role: "", idleMinutes: ""}}));
            If(
                varLogin.ok = "yes",
                Set(varSession, varLogin.sessionId);
                Set(varEmpName, varLogin.employeeName);
                Set(varRole, varLogin.role);
                Set(varSupMode, false);
                Set(varLoginMsg, "");
                Set(varOutKind, ""); Set(varOutText, "");
                If(
                    IsBlank(varReq) And CountRows(Filter(colOutbox, Station = varStation)) > 0,
                    Set(varReq, First(Filter(colOutbox, Station = varStation)));
                    Set(varOutKind, "unconfirmed");
                    Set(varOutText, "An earlier request on this station was never confirmed (" & varReq.Summary & "). Do not re-enter it: press 'Retry same request'.")
                );
                Set(varLastActivity, Now());
                Navigate(scrScan, ScreenTransition.None),
                Set(varLoginMsg, varLogin.message)
            );
            Set(varBusy, false)
        )
    )
)"""
    sup_fn = f"""{F.ACT};
Set(varSession, "");
Set(varEmpName, varMeEmp.EmployeeName);
Set(varRole, varMeEmp.Role.Value);
Set(varSupMode, true);
Set(varLastActivity, Now());
Navigate(scrSupervisor, ScreenTransition.None)"""
    kids = [
        rect("recLoginBg", 0, 0, 1366, 768, NAVY),
        lbl("lblLoginTitle", '"Point-of-Use Inventory"', 0, 70, 1366, 60, 40, True, WHITE, align="Align.Center", note="Title"),
        lbl("lblLoginStation", 'If(IsBlank(varStation), "NO STATION SET UP ON THIS PC - see START_HERE / Admin: open the app with ?StationID=<id> or assign this Microsoft account to a station", "Station " & varStation)',
            100, 140, 1166, 60, 22, True, "RGBA(255, 230, 153, 1)", align="Align.Center", note="Station identity"),
        lbl("lblLoginPrompt", '"Scan your badge"', 0, 240, 1366, 50, 30, True, WHITE, align="Align.Center"),
        inp("txtBadge", "Scan badge", 443, 300, 480, 64, onchange="UpdateContext({locBadgePending: true, locLastKey: Now()})",
            display="If(varBusy Or IsBlank(varStation), DisplayMode.Disabled, DisplayMode.Edit)", size=28, tab=1,
            note="Scanner target. The value is cleared immediately after it is read."),
        btn("btnLogin", '"Sign in"', badge_fn, 543, 380, 280, 56, display="If(varBusy Or IsBlank(varStation), DisplayMode.Disabled, DisplayMode.Edit)", fill="RGBA(68, 114, 196, 1)", tab=2,
            note="Calls POU-Session (LOGIN). Also called by the scan timer."),
        lbl("lblLoginMsg", "varLoginMsg", 343, 450, 680, 70, 20, True, RED, fill=WHITE, visible="Not(IsBlank(varLoginMsg))", align="Align.Center", note="Why sign-in failed"),
        btn("btnSupSignIn", '"Continue as supervisor: " & Coalesce(varMeEmp.EmployeeName, "")', sup_fn, 443, 580, 480, 56,
            display="DisplayMode.Edit", fill="RGBA(84, 130, 53, 1)", visible="varIsPriv", tab=3,
            note="Only appears when the Microsoft account running the app is an active Supervisor/Admin in POUEmployees. Authority is re-checked by the server from the request Author."),
        lbl("lblLoginFoot", '"Signed in to Microsoft as " & User().Email & "  |  app build " & varBuild & "  |  " & If(varSettingsOk, "settings loaded", "SETTINGS NOT LOADED - using defaults")',
            0, 730, 1366, 30, 12, False, "RGBA(200, 200, 200, 1)", align="Align.Center", note="Which Microsoft account the app is running as (this is NOT the employee)"),
        tmr("tmrBadge", "150", "If(\n    locBadgePending And DateDiff(locLastKey, Now(), Milliseconds) >= varScanIdle,\n    Select(btnLogin)\n)", note="Debounce for the badge scan"),
        tmr("tmrLoginTick", "1000", "Set(varTick, Now())", note="Keeps the clock/idle variables moving"),
    ]
    return Screen("scrLogin", "Badge / session entry",
                  "Identifies the EMPLOYEE by badge. The badge is identification only: the session is bound server-side to the Microsoft account running the app and to this station. "
                  "A supervisor uses 'Continue as supervisor' with their OWN Microsoft sign-in; no badge or editable variable can grant authority.",
                  {"Fill": NAVY,
                   "OnVisible": f'''Set(varBusy, false);
Set(varLoginMsg, "");
Set(varSession, "");
Set(varSupMode, false);
UpdateContext({{locBadgePending: false, locLastKey: Now()}});
Reset(txtBadge);
SetFocus(txtBadge)'''}, kids)


# =====================================================================================================================
def scr_scan() -> Screen:
    p = "Scan"
    fin = _scan_finish(p)
    new_req = lambda typ, verb: F.begin_request(F.req_record(
        f'"{typ}"', "locSel.StockKey", "locSel.ItemID", "locSel.LocationCode", qty_cell(p), '""', '""', '""', '""', '""', '""',
        f'"{verb} " & {qty_cell(p)} & " x " & locSel.ItemID & " @ " & locSel.LocationCode & " by " & varEmpName & " at " & varStation'))
    can = lambda q: (f"And(Not(varBusy), IsBlank(varReq), Not(IsBlank(locSel)), Not(IsBlank(locSel.OnHandQty)), {q})")
    add_ok, rem_ok = can(F.qty_ok(qty_cell(p), "varMaxAdd")), can(F.qty_ok(qty_cell(p)))
    kids = header(p) + [runner(p, fin)] + picker(p, 80) + card(p, 196) + [
        lbl(f"lblStep3{p}", '"3  Quantity"', 24, 464, 300, 24, 14, True, GREY),
        inp(f"txtQty{p}", "Quantity", 24, 490, 200, 60, onchange=F.ACT, display=ADD_EDIT, size=30, tab=5, note="Whole number 1-9999. Anything else (a scanned barcode, text, 0, 1.5) is refused and never truncated."),
        lbl(f"lblQtyHint{p}",
            f'''If(
    IsBlank(txtQty{p}.Text), "",
    Not({F.qty_ok(f"txtQty{p}.Text")}), "Quantity must be a whole number from 1 to 9999. Was a barcode scanned into this box?",
    And(Not(IsBlank(locSel)), Not(IsBlank(locSel.OnHandQty)), Value(txtQty{p}.Text) > locSel.OnHandQty), "Only " & locSel.OnHandQty & " on hand here - REMOVE would be refused; ADD limit is " & varMaxAdd & ".",
    Value(txtQty{p}.Text) > varMaxAdd, "ADD is limited to " & varMaxAdd & " at once. Was a part number scanned here?",
    ""
)''', 240, 490, 800, 60, 14, True, "RGBA(156, 0, 6, 1)", note="Why the quantity is not accepted (never silently truncated)"),
        btn(f"btnAdd{p}", '"ADD"', act(f"If(\n    {add_ok},\n    {new_req('RECEIPT', 'ADD')};\n    Select(btnRun{p})\n)"),
            24, 568, 250, 76, display=f"If({add_ok}, DisplayMode.Edit, DisplayMode.Disabled)", fill="RGBA(84, 130, 53, 1)", size=26, visible="IsBlank(varReq)", tab=6,
            note="Creates a RECEIPT request once (new GUID), then posts it. Disabled while busy, while a request is unresolved, or when the entry is invalid."),
        btn(f"btnRemove{p}", '"REMOVE"', act(f"If(\n    {rem_ok},\n    {new_req('ISSUE', 'REMOVE')};\n    Select(btnRun{p})\n)"),
            290, 568, 250, 76, display=f"If({rem_ok}, DisplayMode.Edit, DisplayMode.Disabled)", fill="RGBA(192, 80, 77, 1)", size=26, visible="IsBlank(varReq)", tab=7,
            note="Creates an ISSUE request once, then posts it."),
        btn(f"btnRetry{p}", '"Retry same request (" & Left(varReq.RequestID, 8) & ")"', act(f"Select(btnRun{p})"), 24, 568, 516, 76,
            display="If(varBusy, DisplayMode.Disabled, DisplayMode.Edit)", fill="RGBA(191, 144, 0, 1)", size=22, visible="Not(IsBlank(varReq))", tab=6,
            note="Re-sends the SAME request number. Safe: the server de-duplicates by RequestID."),
        tmr(f"tmrPoll{p}", "varPollSec * 1000", F.poll_tick(fin), start="varPolling And Not(IsBlank(varReq))", note="Reads the request status while it is unconfirmed; never re-sends"),
    ] + banner(p)
    return Screen("scrScan", "Item / location scan: ADD and REMOVE",
                  "The everyday screen. ADD creates a RECEIPT request, REMOVE an ISSUE request. The app never changes a quantity itself: it files the request, asks the flow to process it, "
                  "and shows the outcome read back from the request row.",
                  {**SCREEN_PROPS, "OnVisible": f'''{OPERATOR_GUARD};
Set(varLastActivity, Now());
UpdateContext({{locSel: Blank(), locMsg: "", locPending: false, locLocPending: false, locLastKey: Now()}});
If(IsBlank(varReq), Clear(colStock); Reset(txtItem{p}); Reset(txtLoc{p}); Reset(txtQty{p}); SetFocus(txtItem{p}))'''}, kids)


# =====================================================================================================================
def scr_audit() -> Screen:
    p = "Audit"
    cnt = f"Trim(txtCount{p}.Text)"
    count_ok = f"IsMatch({cnt}, {F.COUNT_PATTERN})"
    fin = F.finish_common(f"""Reset(txtCount{p});
UpdateContext({{locReview: false, locSel: Blank(), locFresh: Blank()}});
Reset(txtItem{p}); Reset(txtLoc{p}); Clear(colStock); SetFocus(txtItem{p})""")
    var_expr = f"(Value({cnt}) - locFresh.OnHandQty)"
    stale = "And(locReview, Not(IsBlank(locFresh)), locFresh.StockVersion <> locVer)"
    big = f"And(locReview, Not(IsBlank(locFresh.OnHandQty)), Abs({var_expr}) >= varAuditVar)"
    make = F.begin_request(F.req_record(
        '"AUDIT"', "locSel.StockKey", "locSel.ItemID", "locSel.LocationCode", cnt, "Text(locVer)", '""', '""', '""', '""', '""',
        f'"COUNT " & {cnt} & " x " & locSel.ItemID & " @ " & locSel.LocationCode & " by " & varEmpName & " at " & varStation'))
    review = f"""{F.ACT};
IfError(
    UpdateContext({{locFresh: LookUp(POUStockLocations, StockKey = locSel.StockKey), locReview: true, locMsg: ""}}),
    UpdateContext({{locMsg: "Could not re-read the current quantity (network?). Nothing was changed. Press Review again."}})
)"""
    post = act(f"If(\n    And(Not(varBusy), IsBlank(varReq), locReview, Not(IsBlank(locSel)), {count_ok}, Not({stale})),\n    {make};\n    Select(btnRun{p})\n)")
    kids = header(p) + [runner(p, fin)] + picker(p, 80, on_select_extra=lambda e: f"locVer: {e}.StockVersion, locReview: false, locFresh: Blank()",
                              qty_ctl=f"txtCount{p}") + [
        lbl(f"lblAudName{p}", 'If(IsBlank(locSel), "", locSel.ItemName & "   |   " & locSel.ItemID & " @ " & locSel.LocationCode & "   (count started at record version " & locVer & ")")',
            24, 400, 1300, 36, 20, True, note="What is being counted. The system quantity is deliberately hidden until the count is entered (blind count)."),
        lbl(f"lblStep3{p}", '"3  Counted quantity (physical count, 0 or more)"', 24, 440, 600, 24, 14, True, GREY),
        inp(f"txtCount{p}", "Counted quantity", 24, 466, 240, 60, onchange=F.ACT + ";\nUpdateContext({locReview: false, locFresh: Blank()})",
            display="If(And(IsBlank(varReq), Not(IsBlank(locSel))), DisplayMode.Edit, DisplayMode.Disabled)", size=30, tab=5,
            note="Whole number 0-999999."),
        lbl(f"lblCountHint{p}", f'If(IsBlank(txtCount{p}.Text), "", Not({count_ok}), "Counted quantity must be a whole number, 0 or more. Was a barcode scanned into this box?", "")',
            280, 466, 820, 60, 14, True, "RGBA(156, 0, 6, 1)"),
        btn(f"btnReview{p}", '"Review count"', review, 24, 540, 240, 60, display=f"If(And(IsBlank(varReq), Not(IsBlank(locSel)), {count_ok}), DisplayMode.Edit, DisplayMode.Disabled)",
            fill="RGBA(68, 114, 196, 1)", visible="IsBlank(varReq)", tab=6, note="Re-reads the record and shows the variance before anything is filed"),
        lbl(f"lblReview{p}", f'''If(
    Not(locReview) Or IsBlank(locFresh), "",
    {stale}, "STOCK MOVED while you were counting: the record changed from version " & locVer & " to " & locFresh.StockVersion & " (an ADD, REMOVE or other posting happened). RECOUNT.",
    IsBlank(locFresh.OnHandQty), "FIRST COUNT. Counted " & {cnt} & ". There is no previous balance; this count becomes the verified starting quantity.",
    "Counted " & {cnt} & "   |   System says " & locFresh.OnHandQty & "   |   Variance " & Text({var_expr}, "+0;-0;0")
)''', 290, 540, 800, 92, 18, True, INK, fill=f"If({stale}, {RED}, {big}, {AMBER}, {BLUE})", visible="locReview", note="Result of the review"),
        btn(f"btnRecount{p}", '"Recount"', act(f"Reset(txtCount{p});\nUpdateContext({{locReview: false, locFresh: Blank(), locVer: LookUp(POUStockLocations, StockKey = locSel.StockKey).StockVersion, locSel: LookUp(POUStockLocations, StockKey = locSel.StockKey)}});\nSetFocus(txtCount{p})"),
            1110, 540, 200, 60, fill="RGBA(191, 144, 0, 1)", visible="locReview And IsBlank(varReq)", tab=8, note="Reloads the record and restarts the count from its current version"),
        btn(f"btnPostCount{p}", f'If({big}, "Variance is " & Text({var_expr}, "+0;-0;0") & " - I recounted. POST COUNT", "POST COUNT")', post, 24, 650, 520, 60,
            display=f"If(And(locReview, Not({stale}), Not(varBusy)), DisplayMode.Edit, DisplayMode.Disabled)",
            fill=f"If({big}, RGBA(192, 80, 77, 1), RGBA(84, 130, 53, 1))", size=18, visible="IsBlank(varReq)", tab=7,
            note="Variance >= AuditConfirmVariance needs this explicit second confirmation. If a supervisor approval is required the request waits (nothing changes until approved)."),
        btn(f"btnRetry{p}", '"Retry same request (" & Left(varReq.RequestID, 8) & ")"', act(f"Select(btnRun{p})"), 24, 650, 520, 60,
            display="If(varBusy, DisplayMode.Disabled, DisplayMode.Edit)", fill="RGBA(191, 144, 0, 1)", visible="Not(IsBlank(varReq))", tab=7),
        tmr(f"tmrPoll{p}", "varPollSec * 1000", F.poll_tick(fin), start="varPolling And Not(IsBlank(varReq))"),
    ] + banner(p, 716 - 0)
    # banner at the bottom edge is tight on this screen: shrink it
    kids[-1].props["Y"] = 712
    kids[-1].props["Height"] = 52
    return Screen("scrAudit", "Physical count / audit",
                  "Blind count. The record's StockVersion is captured when the item is selected (the count BEGINS); the request carries it as ExpectedVersion and the server refuses the count "
                  "(STALE_COUNT) if any posting happened since. Supervisor approval is required by default (RequireSupervisorForAudit).",
                  {**SCREEN_PROPS, "OnVisible": f'''{OPERATOR_GUARD};
Set(varLastActivity, Now());
UpdateContext({{locSel: Blank(), locMsg: "", locPending: false, locLocPending: false, locLastKey: Now(), locReview: false, locFresh: Blank(), locVer: 0}});
If(IsBlank(varReq), Clear(colStock); Reset(txtItem{p}); Reset(txtLoc{p}); Reset(txtCount{p}); SetFocus(txtItem{p}))'''}, kids)


# =====================================================================================================================
def scr_add() -> Screen:
    p = "AddItem"
    t = lambda n: f"Trim({n}{p}.Text)"
    item, name, mfr, desc = F.normalise(f"txtItemId{p}.Text"), t("txtName"), t("txtMfr"), t("txtDesc")
    loc, area, mn, mx = F.normalise(f"txtLocCode{p}.Text"), t("txtArea"), t("txtMin"), t("txtMax")
    num = f"IsMatch(%s, {F.COUNT_PATTERN})"
    loc_known = f"Not(IsBlank(LookUp(POULocations, LocationCode = {loc}, Active = true)))"
    id_ok = f'And(Len({item}) >= 1, Not("|" in {item}), Not(" " in {item}))'
    new_mode = 'locMode = "ITEM_CREATE"'
    item_exists = f"Not(IsBlank(LookUp(POUItems, ItemID = {item})))"
    ok = (f"And(Not(varBusy), IsBlank(varReq), {id_ok}, If({new_mode}, Len({name}) > 0 And Not({item_exists}), {item_exists}), "
          f"{loc_known}, {num % mn}, {num % mx}, If(And({num % mn}, {num % mx}), Value({mn}) <= Value({mx}), false))")
    payload = (f"JSON({{ItemID: {item}, ItemName: {name}, Description: {desc}, Manufacturer: {mfr}, LocationCode: {loc}, Area: {area}, "
               f"MinQty: Value({mn}), MaxQty: Value({mx})}}, JSONFormat.Compact)")
    make = F.begin_request(F.req_record(
        "locMode", '""', item, loc, '""', '""', '""', payload, '""', '""', '""',
        f'If({new_mode}, "NEW ITEM ", "NEW LOCATION ") & {item} & " @ " & {loc} & " by " & varEmpName & " at " & varStation'))
    fin = F.finish_common(f"""Reset(txtItemId{p}); Reset(txtName{p}); Reset(txtMfr{p}); Reset(txtDesc{p}); Reset(txtLocCode{p}); Reset(txtArea{p}); Reset(txtMin{p}); Reset(txtMax{p});
SetFocus(txtItemId{p})""")
    row = lambda i: 150 + 62 * i
    kids = header(p) + [runner(p, fin)] + [
        lbl(f"lblAddHelp{p}", '"A NEW ITEM adds the item master AND its first stocking location. To stock an EXISTING item (e.g. K102516) in another place, choose ADD LOCATION: the item is never duplicated, merged or renumbered."',
            24, 76, 1318, 50, 14, False, GREY),
        btn(f"btnModeNew{p}", '"NEW ITEM"', act('UpdateContext({locMode: "ITEM_CREATE"})'), 24, 100, 200, 44, fill=f"If({new_mode}, RGBA(31, 56, 100, 1), RGBA(150, 150, 150, 1))", tab=1),
        btn(f"btnModeLoc{p}", '"ADD LOCATION"', act('UpdateContext({locMode: "LOCATION_ADD"})'), 232, 100, 200, 44, fill=f"If({new_mode}, RGBA(150, 150, 150, 1), RGBA(31, 56, 100, 1))", tab=2),
        lbl(f"lblL1{p}", '"Item ID"', 24, row(0), 160, 40, 16, True), inp(f"txtItemId{p}", "Item ID (text; leading zeros kept)", 190, row(0) - 4, 380, 48, onchange=F.ACT, display=ADD_EDIT, tab=3),
        lbl(f"lblL2{p}", '"Name"', 24, row(1), 160, 40, 16, True, visible=new_mode), inp(f"txtName{p}", "Item name", 190, row(1) - 4, 700, 48, onchange=F.ACT, display=ADD_EDIT, visible=new_mode, tab=4),
        lbl(f"lblL3{p}", '"Manufacturer"', 24, row(2), 160, 40, 16, True, visible=new_mode), inp(f"txtMfr{p}", "Manufacturer (optional)", 190, row(2) - 4, 380, 48, onchange=F.ACT, display=ADD_EDIT, visible=new_mode, tab=5),
        lbl(f"lblL4{p}", '"Description"', 600, row(2), 130, 40, 16, True, visible=new_mode), inp(f"txtDesc{p}", "Description (optional)", 730, row(2) - 4, 600, 48, onchange=F.ACT, display=ADD_EDIT, visible=new_mode, tab=6),
        lbl(f"lblL5{p}", '"Location"', 24, row(3), 160, 40, 16, True), inp(f"txtLocCode{p}", "Location code (must exist in the location list)", 190, row(3) - 4, 380, 48, onchange=F.ACT, display=ADD_EDIT, tab=7),
        lbl(f"lblLocOk{p}", f'If(IsBlank(txtLocCode{p}.Text), "", {loc_known}, "Location found", "Unknown or inactive location - an admin adds locations")', 590, row(3), 600, 40, 14, True, GREY),
        lbl(f"lblL6{p}", '"Area"', 24, row(4), 160, 40, 16, True), inp(f"txtArea{p}", "Area (optional)", 190, row(4) - 4, 380, 48, onchange=F.ACT, display=ADD_EDIT, tab=8),
        lbl(f"lblL7{p}", '"Min / Max"', 24, row(5), 160, 40, 16, True),
        inp(f"txtMin{p}", "Min", 190, row(5) - 4, 180, 48, onchange=F.ACT, display=ADD_EDIT, tab=9), inp(f"txtMax{p}", "Max", 390, row(5) - 4, 180, 48, onchange=F.ACT, display=ADD_EDIT, tab=10),
        lbl(f"lblAddWhy{p}", f'''If(
    IsBlank(txtItemId{p}.Text), "",
    Not({id_ok}), "Item ID cannot contain spaces or the | character.",
    And({new_mode}, {item_exists}), "Item " & {item} & " already exists. Use ADD LOCATION to stock it somewhere else.",
    And(Not({new_mode}), Not({item_exists})), "Item " & {item} & " does not exist. Use NEW ITEM.",
    ""
)''', 590, row(0), 740, 40, 14, True, "RGBA(156, 0, 6, 1)"),
        lbl(f"lblAddNote{p}", 'If(varSupNewItem, "A supervisor must approve this before anything is created. Nothing is created until then, and no quantity is set: the first quantity comes from a supervisor-approved count.", "No quantity is set: the first quantity comes from a count.")',
            24, row(6), 1300, 40, 14, False, GREY),
        btn(f"btnAddSubmit{p}", 'If(' + new_mode + ', "REQUEST NEW ITEM", "REQUEST NEW LOCATION")', act(f"If(\n    {ok},\n    {make};\n    Select(btnRun{p})\n)"),
            24, 600, 420, 60, display=f"If({ok}, DisplayMode.Edit, DisplayMode.Disabled)", fill="RGBA(84, 130, 53, 1)", visible="IsBlank(varReq)", tab=11,
            note="Files ITEM_CREATE / LOCATION_ADD. The server re-validates everything, creates both rows idempotently, and sets NO quantity."),
        btn(f"btnRetry{p}", '"Retry same request (" & Left(varReq.RequestID, 8) & ")"', act(f"Select(btnRun{p})"), 24, 600, 420, 60,
            display="If(varBusy, DisplayMode.Disabled, DisplayMode.Edit)", fill="RGBA(191, 144, 0, 1)", visible="Not(IsBlank(varReq))", tab=11),
        tmr(f"tmrPoll{p}", "varPollSec * 1000", F.poll_tick(fin), start="varPolling And Not(IsBlank(varReq))"),
    ] + banner(p, 672)
    kids[-1].props["Height"] = 84
    return Screen("scrAddItem", "Add item / add stocking location",
                  "Two request types: ITEM_CREATE (new item master + first location) and LOCATION_ADD (existing item, additional location). Supervisor approval is on by default (RequireSupervisorForNewItem).",
                  {**SCREEN_PROPS, "OnVisible": f'''{OPERATOR_GUARD};
Set(varLastActivity, Now());
UpdateContext({{locMode: "ITEM_CREATE"}});
SetFocus(txtItemId{p})'''}, kids)


# =====================================================================================================================
def scr_low() -> Screen:
    p = "Low"
    flt = f'Filter(POUStockLocations, Active = true, LowStockFlag = true, StartsWith(ItemID, {F.normalise(f"txtFilter{p}.Text")}))'
    kids = header(p) + [
        lbl(f"lblLowTitle{p}", '"Low stock (On hand <= Min by default; the rule is the central LowStockRule setting)"', 24, 76, 1000, 30, 18, True),
        inp(f"txtFilter{p}", "Filter: item number starts with...", 24, 112, 360, 44, onchange=F.ACT, tab=1),
        lbl(f"lblLowCount{p}", f'CountRows(galLow{p}.AllItems) & " shown" & If(CountRows(galLow{p}.AllItems) >= varRowLimit, "  -  LIST MAY BE TRUNCATED at the app row limit of " & varRowLimit & ". The emailed low-stock report is complete.", "")',
            400, 112, 940, 44, 14, True, "RGBA(156, 87, 0, 1)"),
        lbl(f"lblLowHead{p}", '"Item                         Location        On hand   Min   Max   Suggested (Max - On hand)"', 24, 164, 1300, 30, 14, True, GREY),
        Ctl(f"galLow{p}", "gallery.galleryVertical",
            {"X": 24, "Y": 196, "Width": 1318, "Height": 530, "TemplateSize": 48,
             "Items": f'FirstN(SortByColumns({flt}, "ItemID", SortOrder.Ascending), varRowLimit)',
             "TemplateFill": f"If(Mod(ThisItem.ID, 2) = 0, {WHITE}, RGBA(247, 247, 247, 1))"},
            [lbl(f"lblLowRow{p}", 'ThisItem.ItemID & "   " & ThisItem.ItemName & "   |   " & ThisItem.LocationCode & "   |   on hand " & Coalesce(Text(ThisItem.OnHandQty), "-") & "   min " & Coalesce(Text(ThisItem.MinQty), "-") & "   max " & Coalesce(Text(ThisItem.MaxQty), "-") & "   |   suggest " & If(IsBlank(ThisItem.OnHandQty) Or IsBlank(ThisItem.MaxQty), "-", Max(0, ThisItem.MaxQty - ThisItem.OnHandQty))',
                 8, 6, 1300, 36, 15, False)],
            note="Delegable: Filter on Boolean columns + StartsWith + SortByColumns"),
        lbl(f"lblLowNote{p}", '"Suggestions only - they do NOT consider open purchase orders. No order is created."', 24, 730, 1000, 28, 12, False, GREY),
    ]
    return Screen("scrLowStock", "Low stock",
                  "Reads the server-maintained LowStockFlag. Items with no verified quantity are not listed as low stock (they appear in the data-health report).",
                  {**SCREEN_PROPS, "OnVisible": f"{OPERATOR_GUARD};\nSet(varLastActivity, Now());\nReset(txtFilter{p})"}, kids)


# =====================================================================================================================
def scr_history() -> Screen:
    p = "Hist"
    item = F.normalise(f"txtHistItem{p}.Text")
    ledger = (f'If(IsBlank({item}), FirstN(SortByColumns(POULedger, "ID", SortOrder.Descending), 60), '
              f'FirstN(SortByColumns(Filter(POULedger, ItemID = {item}), "ID", SortOrder.Descending), 60))')
    kids = header(p) + [
        lbl(f"lblReqTitle{p}", '"Requests from this station - with processing status"', 24, 76, 640, 28, 16, True),
        btn(f"btnRefresh{p}", '"Refresh"', act("Refresh(POURequests); Refresh(POULedger)"), 560, 72, 110, 34, fill="RGBA(68, 114, 196, 1)", size=12),
        Ctl(f"galReq{p}", "gallery.galleryVertical",
            {"X": 24, "Y": 110, "Width": 650, "Height": 600, "TemplateSize": 84,
             "Items": 'FirstN(SortByColumns(Filter(POURequests, StationID = varStation), "ID", SortOrder.Descending), 50)',
             "TemplateFill": f'Switch(ThisItem.RequestStatus.Value, "Succeeded", {GREEN}, "Rejected", {RED}, "Failed", {RED}, "AwaitingSupervisor", {AMBER}, "Pending", {AMBER}, "Processing", {AMBER}, {WHITE})'},
            [lbl(f"lblReqRow{p}", 'ThisItem.RequestType.Value & "  " & Coalesce(ThisItem.Title, "") & "\n" & ThisItem.RequestStatus.Value & If(ThisItem.IsOpen, "  (open)", "") & "  -  " & Coalesce(ThisItem.ResultMessage, "") & "\n" & Text(ThisItem.Created, "mmm d, h:mm AM/PM") & "  |  request " & Left(ThisItem.RequestID, 8) & If(ThisItem.InventoryEffect.Value = "Unknown", "  |  EFFECT UNKNOWN - tell a supervisor", "")',
                 8, 4, 634, 76, 12, False),
             btn(f"btnReCheck{p}", '"Re-check"', act(f"IfError({F.PROCESS_FLOW}.Run(ThisItem.RequestID), true);\nRefresh(POURequests)"), 540, 50, 96, 28, fill="RGBA(191, 144, 0, 1)", size=11,
                 visible='ThisItem.IsOpen And ThisItem.RequestStatus.Value <> "AwaitingSupervisor"', note="Asks the flow to finish an unfinished request. Idempotent: it cannot post twice.")],
            note="Delegable: Filter on indexed StationID, SortByColumns on ID"),
        lbl(f"lblLedTitle{p}", '"Ledger (every posted movement). Legacy = imported from the old workbook, not part of the balance."', 690, 76, 660, 28, 14, True),
        inp(f"txtHistItem{p}", "Item number (blank = latest 60)", 690, 110, 360, 40, onchange=F.ACT, tab=1),
        Ctl(f"galLed{p}", "gallery.galleryVertical",
            {"X": 690, "Y": 156, "Width": 660, "Height": 554, "TemplateSize": 66, "Items": ledger,
             "TemplateFill": f'If(ThisItem.Origin.Value = "Legacy", RGBA(237, 237, 237, 1), If(ThisItem.PostingState.Value = "Posted", {WHITE}, {AMBER}))'},
            [lbl(f"lblLedRow{p}", 'ThisItem.LedgerType.Value & If(ThisItem.Origin.Value = "Legacy", " (LEGACY)", "") & " " & ThisItem.ItemID & " @ " & Coalesce(ThisItem.LocationCode, "?") & "  delta " & Coalesce(Text(ThisItem.QtyDelta), "-") & "  -> " & Coalesce(Text(ThisItem.QtyAfter), "-") & "\n" & Coalesce(ThisItem.EmployeeName, ThisItem.LegacyUser, "?") & "  |  " & Coalesce(ThisItem.OccurredLocalText, ThisItem.LegacyTimestampText, Text(ThisItem.OccurredUtc, "mmm d, h:mm AM/PM")) & If(ThisItem.PostingState.Value <> "Posted", "  |  " & ThisItem.PostingState.Value, "")',
                 8, 4, 644, 58, 12, False)],
            note="Delegable: Filter on indexed ItemID, SortByColumns on ID, FirstN"),
    ]
    return Screen("scrHistory", "Transaction history and processing status",
                  "Left: this station's requests with their real status (AwaitingSupervisor / Pending / Succeeded / Rejected / Failed). Right: the append-only ledger. Times shown are the ledger's stored local text "
                  "(America/Chicago, written by the flow); the fallback uses this PC's time zone, which must be America/Chicago.",
                  {**SCREEN_PROPS, "OnVisible": f"{OPERATOR_GUARD};\nSet(varLastActivity, Now());\nReset(txtHistItem{p});\nRefresh(POURequests)"}, kids)


# =====================================================================================================================
def scr_supervisor() -> Screen:
    p = "Sup"
    tab = lambda n: f'locTab = "{n}"'
    approve_req = lambda decision: F.begin_request(F.req_record(
        '"APPROVE"', '""', '""', '""', '""', '""', '""', '""', "ThisItem.RequestID", f'"{decision}"', '""',
        f'"{decision.upper()} " & Left(ThisItem.RequestID, 8) & " " & ThisItem.RequestType.Value & " by " & varEmpName'))
    plain_fin = F.finish_common("Reset(txtQtySup); Reset(txtReasonSup); Reset(txtMinSup); Reset(txtMaxSup); Reset(txtAreaSup); "
                                "UpdateContext({locPickLedger: Blank()}); Refresh(POURequests)")
    # After an APPROVE request is recorded: ask the flow to process the TARGET and report ITS real outcome.
    approve_after = f"""If(
    varOutKind = "ok",
    IfError({F.PROCESS_FLOW}.Run(varReq.TargetRequestID), true);
    Set(varTgtRow, IfError(LookUp(POURequests, RequestID = varReq.TargetRequestID), Blank()));
    Set(varOutKind, If(varTgtRow.RequestStatus.Value = "Succeeded", "ok", Or(varTgtRow.RequestStatus.Value = "Rejected", varTgtRow.RequestStatus.Value = "Failed"), "bad", "wait"));
    Set(varOutText, "Decision recorded. The request is now: " & Coalesce(varTgtRow.RequestStatus.Value, "unknown") & ". " & Coalesce(varTgtRow.ResultMessage, ""))
);
{F.finish_common('Refresh(POURequests)')}"""
    fin = f'If(varReq.RequestType = "APPROVE",\n{approve_after},\n{plain_fin})'
    cnt, reason = f"Trim(txtQty{p}.Text)", f"Trim(txtReason{p}.Text)"
    cnt_ok = f"IsMatch({cnt}, {F.COUNT_PATTERN})"
    mk = lambda typ, qty, reason_, payload, rev, summ: F.begin_request(F.req_record(
        f'"{typ}"', "locSel.StockKey", "locSel.ItemID", "locSel.LocationCode", qty, '""', reason_, payload, '""', '""', rev, summ))
    mk_adj = mk("ADJUSTMENT", cnt, reason, '""', '""', f'"ADJUST " & locSel.ItemID & " @ " & locSel.LocationCode & " to " & {cnt} & " by " & varEmpName')
    mk_rev = mk("REVERSAL", '""', reason, '""', "locPickLedger.LedgerKey", '"REVERSE " & locPickLedger.LedgerKey & " by " & varEmpName')
    mk_open = mk("OPENING", cnt, reason, '""', '""', f'"OPENING " & {cnt} & " x " & locSel.ItemID & " @ " & locSel.LocationCode & " by " & varEmpName')
    payload = (f"JSON({{MinQty: If(IsBlank(txtMin{p}.Text), Blank(), Value(txtMin{p}.Text)), MaxQty: If(IsBlank(txtMax{p}.Text), Blank(), Value(txtMax{p}.Text)), "
               f"Area: If(IsBlank(txtArea{p}.Text), Blank(), Trim(txtArea{p}.Text)), Active: locParamActive}}, JSONFormat.Compact)")
    mk_par = mk("PARAM_UPDATE", '""', '""', payload, '""', '"SETTINGS " & locSel.ItemID & " @ " & locSel.LocationCode & " by " & varEmpName')
    gate = "Not(varBusy), IsBlank(varReq), varSupMode, Not(IsBlank(locSel))"
    sup_edit = f"If(And(Not(varBusy), IsBlank(varReq), varSupMode), DisplayMode.Edit, DisplayMode.Disabled)"
    on = lambda cond, body: act(f"If(\n    {cond},\n    {body};\n    Select(btnRun{p})\n)")
    adj_cond = f"And({gate}, {cnt_ok}, Len({reason}) > 0)"
    open_cond = f"And({gate}, {cnt_ok}, Len({reason}) > 0, varRole = \"Admin\")"
    rev_cond = f"And({gate}, Not(IsBlank(locPickLedger)), Len({reason}) > 0)"
    par_cond = f"And({gate}, Or(Not(IsBlank(txtMin{p}.Text)), Not(IsBlank(txtMax{p}.Text)), Not(IsBlank(txtArea{p}.Text)), Not(locParamActive = locSel.Active)))"
    mode = lambda cond: f"If({cond}, DisplayMode.Edit, DisplayMode.Disabled)"
    tabbtn = lambda key, cap, x, w: btn(f"btnTab{key}{p}", f'"{cap}"', act(f'UpdateContext({{locTab: "{key}"}})'), x, 72, w, 36,
                                        fill=f'If({tab(key)}, RGBA(31, 56, 100, 1), RGBA(150, 150, 150, 1))', size=13)
    picker_ctls = picker(p, 116, on_select_extra=lambda e: "locPickLedger: Blank(), locParamActive: " + e + ".Active", qty_ctl=f"txtQty{p}", gal_h=110)
    for c in picker_ctls:  # the picker is for every tab except the approvals queue
        if c.name != f"tmrScan{p}":
            old = c.props.get("Visible")
            c.props["Visible"] = f'Not({tab("Q")})' if not old else f'And(Not({tab("Q")}), {old})'
    kids = header(p) + [runner(p, fin)] + [
        tabbtn("Q", "Approvals", 24, 150), tabbtn("A", "Adjust / opening", 180, 170), tabbtn("R", "Reverse", 356, 150), tabbtn("P", "Min / Max / Area", 512, 170),
        lbl(f"lblSupWho{p}", 'If(varSupMode, "You act as " & varEmpName & " (" & User().Email & "). The SERVER decides your authority from this Microsoft sign-in and POUEmployees.", "Supervisor functions need \'Continue as supervisor\' on the sign-in screen, using your own Microsoft account.")',
            700, 68, 650, 44, 12, False, GREY),
        # ---------------- approvals queue
        lbl(f"lblQHead{p}", '"Waiting for a supervisor, oldest first. These requests have NOT changed any quantity yet."', 24, 118, 1000, 28, 14, True, GREY, visible=tab("Q")),
        btn(f"btnQRefresh{p}", '"Refresh"', act("Refresh(POURequests)"), 1230, 114, 112, 32, fill="RGBA(68, 114, 196, 1)", size=12, visible=tab("Q")),
        Ctl(f"galQueue{p}", "gallery.galleryVertical",
            {"X": 24, "Y": 150, "Width": 1318, "Height": 500, "TemplateSize": 80, "Visible": tab("Q"),
             "Items": 'FirstN(SortByColumns(Filter(POURequests, IsOpen = true, RequestStatus.Value = "AwaitingSupervisor"), "ID", SortOrder.Ascending), 100)'},
            [lbl(f"lblQRow{p}", 'ThisItem.RequestType.Value & "   " & Coalesce(ThisItem.Title, "") & "\n" & "Item " & Coalesce(ThisItem.ItemID, "-") & " @ " & Coalesce(ThisItem.LocationCode, "-") & "   qty " & Coalesce(Text(ThisItem.Quantity), "-") & "   counted-from version " & Coalesce(Text(ThisItem.ExpectedVersion), "-") & "\n" & Text(ThisItem.Created, "mmm d, h:mm AM/PM") & "  |  filed by account " & ThisItem.\'Created By\'.Email & "  |  request " & Left(ThisItem.RequestID, 8)',
                  8, 4, 940, 72, 13, False),
             btn(f"btnApprove{p}", '"APPROVE"', on("And(Not(varBusy), IsBlank(varReq), varSupMode)", approve_req("Approve")), 960, 18, 160, 44,
                 display=sup_edit, fill="RGBA(84, 130, 53, 1)",
                 note="Files an APPROVE request authored by YOUR Microsoft account, then lets the flow process the target. The server refuses self-approval."),
             btn(f"btnReject{p}", '"REJECT"', on("And(Not(varBusy), IsBlank(varReq), varSupMode)", approve_req("Reject")), 1130, 18, 160, 44,
                 display=sup_edit, fill="RGBA(192, 80, 77, 1)")],
            note="Delegable: Filter on Boolean IsOpen + choice .Value (confirm the delegation indicator in Studio) + SortByColumns on ID"),
    ] + picker_ctls + [
        lbl(f"lblSupSel{p}", 'If(IsBlank(locSel), "", locSel.ItemName & "\n" & locSel.ItemID & " @ " & locSel.LocationCode & "   on hand " & Coalesce(Text(locSel.OnHandQty), "-") & "   record version " & locSel.StockVersion & "   " & locSel.BalanceStatus.Value)',
            480, 234, 860, 100, 16, True, INK, visible=f'Not({tab("Q")})', note="Supervisors see the system quantity"),
        # ---------------- adjust / opening
        lbl(f"lblAdjHead{p}", '"ADJUSTMENT sets the quantity to the number you enter and records your reason. It is a new ledger entry, never an edit of history."', 24, 352, 1300, 28, 13, True, GREY, visible=tab("A")),
        lbl(f"lblQtyL{p}", '"New quantity"', 24, 392, 160, 40, 16, True, visible=tab("A")),
        inp(f"txtQty{p}", "New quantity", 190, 388, 200, 48, onchange=F.ACT, display=ADD_EDIT, visible=tab("A"), tab=5),
        lbl(f"lblReasonL{p}", '"Reason (required)"', 24, 452, 160, 40, 16, True, visible='Or(locTab = "A", locTab = "R")'),
        inp(f"txtReason{p}", "Why?", 190, 448, 700, 48, onchange=F.ACT, display=ADD_EDIT, visible='Or(locTab = "A", locTab = "R")', tab=6),
        btn(f"btnAdjust{p}", '"POST ADJUSTMENT"', on(adj_cond, mk_adj), 24, 516, 320, 56, display=mode(adj_cond), fill="RGBA(192, 80, 77, 1)",
            visible=tab("A") + " And IsBlank(varReq)", tab=7, note="Needs an authenticated supervisor; the server refuses it for anyone else."),
        btn(f"btnOpening{p}", '"SET OPENING BALANCE (admin, first time only)"', on(open_cond, mk_open), 360, 516, 460, 56, display=mode(open_cond), fill="RGBA(112, 48, 160, 1)",
            visible=tab("A") + " And IsBlank(varReq)", note="OPENING is accepted by the server only from an Admin and only on a record that has never had a balance."),
        # ---------------- reversal
        lbl(f"lblRevHead{p}", '"REVERSAL cancels one posted ADD or REMOVE with a new ledger entry. Pick the movement (newest first):"', 24, 352, 1300, 28, 13, True, GREY, visible=tab("R")),
        Ctl(f"galRev{p}", "gallery.galleryVertical",
            {"X": 24, "Y": 384, "Width": 1100, "Height": 170, "TemplateSize": 42, "Visible": tab("R"),
             "Items": 'If(IsBlank(locSel), Blank(), FirstN(SortByColumns(Filter(POULedger, StockKey = locSel.StockKey), "ID", SortOrder.Descending), 30))',
             "TemplateFill": f"If(ThisItem.LedgerKey = locPickLedger.LedgerKey, {BLUE}, {WHITE})",
             "OnSelect": f"{F.ACT};\nUpdateContext({{locPickLedger: ThisItem}})"},
            [lbl(f"lblRevRow{p}", 'ThisItem.LedgerKey & "  " & ThisItem.LedgerType.Value & "  delta " & Coalesce(Text(ThisItem.QtyDelta), "-") & "  " & Coalesce(ThisItem.OccurredLocalText, "") & "  " & Coalesce(ThisItem.EmployeeName, "")',
                  8, 4, 1080, 34, 13, False)]),
        btn(f"btnReverse{p}", '"POST REVERSAL"', on(rev_cond, mk_rev), 24, 612, 300, 48, display=mode(rev_cond), fill="RGBA(192, 80, 77, 1)", visible=tab("R") + " And IsBlank(varReq)"),
        # ---------------- parameters
        lbl(f"lblParHead{p}", '"Change Min / Max / Area, or deactivate. Leave a box empty to keep its value. This never changes a quantity."', 24, 352, 1300, 28, 13, True, GREY, visible=tab("P")),
        inp(f"txtMin{p}", "New Min", 24, 392, 180, 48, onchange=F.ACT, display=ADD_EDIT, visible=tab("P"), tab=5),
        inp(f"txtMax{p}", "New Max", 220, 392, 180, 48, onchange=F.ACT, display=ADD_EDIT, visible=tab("P"), tab=6),
        inp(f"txtArea{p}", "New Area", 416, 392, 300, 48, onchange=F.ACT, display=ADD_EDIT, visible=tab("P"), tab=7),
        btn(f"btnActive{p}", 'If(locParamActive, "ACTIVE (press to deactivate)", "INACTIVE (press to reactivate)")', act("UpdateContext({locParamActive: Not(locParamActive)})"), 732, 392, 330, 48,
            fill="RGBA(100, 100, 100, 1)", visible=tab("P"), size=13),
        btn(f"btnParam{p}", '"POST CHANGE"', on(par_cond, mk_par), 24, 462, 300, 56, display=mode(par_cond), fill="RGBA(192, 80, 77, 1)", visible=tab("P") + " And IsBlank(varReq)"),
        # ---------------- retry + poll
        btn(f"btnRetry{p}", '"Retry same request (" & Left(varReq.RequestID, 8) & ")"', act(f"Select(btnRun{p})"), 24, 612, 420, 48,
            display="If(varBusy, DisplayMode.Disabled, DisplayMode.Edit)", fill="RGBA(191, 144, 0, 1)", visible="Not(IsBlank(varReq))", note="Re-sends the SAME request number"),
        tmr(f"tmrPoll{p}", "varPollSec * 1000", F.poll_tick(fin), start="varPolling And Not(IsBlank(varReq))"),
    ] + banner(p, 668)
    kids[-1].props["Height"] = 88
    return Screen("scrSupervisor", "Supervisor console (own Microsoft sign-in)",
                  "Approve/reject waiting requests, post adjustments, reversals, parameter changes and (Admin) opening balances. Every action is a request authored by the supervisor's OWN Microsoft account; "
                  "the flow decides authority from that Author identity. Hiding this screen is convenience only.",
                  {**SCREEN_PROPS, "OnVisible": '''If(Not(varSupMode), Navigate(scrLogin, ScreenTransition.None));
Set(varLastActivity, Now());
UpdateContext({locTab: "Q", locSel: Blank(), locMsg: "", locPending: false, locLocPending: false, locLastKey: Now(), locPickLedger: Blank(), locParamActive: true});
Refresh(POURequests)'''}, kids)


# =====================================================================================================================
def scr_admin() -> Screen:
    p = "Admin"
    new_loc = F.normalise(f"txtNewLoc{p}.Text")
    kids = header(p) + [
        lbl(f"lblAdmTitle{p}", '"Settings (central configuration). Changes are versioned in SharePoint; flows read them on every run."', 24, 76, 1300, 30, 16, True),
        lbl(f"lblAdmWho{p}", 'If(varRole = "Admin", "", "Read only - you are not an Admin. SharePoint would refuse your edits anyway.")', 24, 104, 800, 28, 13, True, RED),
        inp(f"txtSetFilter{p}", "Filter by name...", 24, 136, 300, 40, onchange=F.ACT, tab=1),
        Ctl(f"galSet{p}", "gallery.galleryVertical",
            {"X": 24, "Y": 182, "Width": 900, "Height": 540, "TemplateSize": 52,
             "Items": f'SortByColumns(Filter(POUSettings, StartsWith(SettingKey, Trim(txtSetFilter{p}.Text))), "SettingKey", SortOrder.Ascending)'},
            [lbl(f"lblSetKey{p}", 'ThisItem.SettingKey', 8, 6, 330, 40, 14, True),
             inp(f"txtSetVal{p}", "value", 346, 4, 360, 44, default="ThisItem.SettingValue", display='If(varRole = "Admin", DisplayMode.Edit, DisplayMode.View)', size=14),
             btn(f"btnSetSave{p}", '"Save"', act(f'''IfError(
    Patch(POUSettings, ThisItem, {{SettingValue: Trim(txtSetVal{p}.Text)}});
    Notify("Saved " & ThisItem.SettingKey, NotificationType.Success),
    Notify("NOT saved: " & FirstError.Message, NotificationType.Error)
)'''), 720, 6, 100, 40, display='If(varRole = "Admin", DisplayMode.Edit, DisplayMode.Disabled)', fill="RGBA(84, 130, 53, 1)", size=13)],
            note="Direct Patch on POUSettings. Allowed only for POU Admins (SharePoint permission), not by this app's logic."),
        lbl(f"lblLocTitle{p}", '"Locations"', 950, 104, 390, 28, 16, True),
        inp(f"txtNewLoc{p}", "New location code", 950, 136, 250, 44, onchange=F.ACT, display='If(varRole = "Admin", DisplayMode.Edit, DisplayMode.Disabled)', tab=2),
        btn(f"btnNewLoc{p}", '"Add"', act(f'''If(
    Len({new_loc}) > 0 And IsBlank(LookUp(POULocations, LocationCode = {new_loc})),
    IfError(
        Patch(POULocations, Defaults(POULocations), {{Title: {new_loc}, LocationCode: {new_loc}, Description: "", Active: true}});
        Reset(txtNewLoc{p});
        Notify("Location added", NotificationType.Success),
        Notify("NOT added: " & FirstError.Message, NotificationType.Error)
    ),
    Notify("Enter a new location code that is not already in the list.", NotificationType.Warning)
)'''), 1210, 136, 130, 44, display='If(varRole = "Admin", DisplayMode.Edit, DisplayMode.Disabled)', fill="RGBA(84, 130, 53, 1)", tab=3),
        Ctl(f"galLocList{p}", "gallery.galleryVertical",
            {"X": 950, "Y": 186, "Width": 390, "Height": 250, "TemplateSize": 44, "Items": 'SortByColumns(POULocations, "LocationCode", SortOrder.Ascending)'},
            [lbl(f"lblLocRow{p}", 'ThisItem.LocationCode & If(ThisItem.Active, "", "  (inactive)")', 8, 4, 370, 36, 14, False)]),
        lbl(f"lblStnTitle{p}", '"Stations (editable; no code change needed to add a cabinet PC)"', 950, 446, 390, 28, 14, True),
        Ctl(f"galStn{p}", "gallery.galleryVertical",
            {"X": 950, "Y": 478, "Width": 390, "Height": 240, "TemplateSize": 44, "Items": 'SortByColumns(POUStations, "StationID", SortOrder.Ascending)'},
            [lbl(f"lblStnRow{p}", 'ThisItem.StationID & "  " & Coalesce(ThisItem.StationName, "") & If(ThisItem.Active, "", " (inactive)") & "  " & Coalesce(ThisItem.ExpectedAccountUPN, "")', 8, 4, 370, 36, 12, False)]),
        lbl(f"lblAdmNote{p}", '"Stations, employees and badge IDs are maintained in the SharePoint lists directly (admin only). Opening balances and adjustments are on the Supervisor screen."', 24, 726, 900, 32, 12, False, GREY),
    ]
    return Screen("scrAdmin", "Admin / settings",
                  "Edits central settings and the location list. The app only offers the controls; SharePoint permissions (POU Admins) are what allow or refuse the write.",
                  {**SCREEN_PROPS, "OnVisible": "If(Not(varSupMode), Navigate(scrLogin, ScreenTransition.None));\nSet(varLastActivity, Now());\nRefresh(POUSettings)"}, kids)


# =====================================================================================================================
def all_screens() -> list:
    return [scr_login(), scr_scan(), scr_audit(), scr_add(), scr_low(), scr_history(), scr_supervisor(), scr_admin()]


def app_props() -> dict:
    return {
        "StartScreen": "=scrLogin",
        "OnStart": f'''// 1. who/where: the Microsoft account running the app is NOT the employee
Set(varStation, Upper(Trim(Coalesce(Param("StationID"), LookUp(POUStations, Active = true, ExpectedAccountUPN = Lower(User().Email)).StationID, ""))));
Set(varBuild, "{{BUILD}}");
Set(varRowLimit, 500);
// 2. central settings (editable in POUSettings); defaults mirror schema/settings_defaults.json
Set(varSettingsOk, false);
IfError(ClearCollect(colSettings, POUSettings); Set(varSettingsOk, CountRows(colSettings) > 0), Clear(colSettings));
{F.settings_block()};
// 3. is this Microsoft account a supervisor/admin? Display only - the server decides authority from the request Author.
Set(varMeEmp, IfError(LookUp(POUEmployees, MicrosoftUPN = Lower(User().Email), Active = true), Blank()));
Set(varIsPriv, Not(IsBlank(varMeEmp)) And varMeEmp.Role.Value <> "Operator");
// 4. state
Set(varSession, ""); Set(varEmpName, ""); Set(varRole, ""); Set(varSupMode, false);
Set(varBusy, false); Set(varLastActivity, Now()); Set(varTick, Now());
Set(varLoginMsg, ""); Set(varOutKind, ""); Set(varOutText, ""); Set(varPolling, false); Set(varPollTries, 0);
Set(varLookupFailed, false); Set(varCreateFailed, false); Set(varSent, false);
Set(varLogin, {{ok: "no", code: "", message: "", sessionId: "", employeeName: "", role: "", idleMinutes: ""}});
Set(varResp, {{status: "", code: "", message: "", ledgerKey: "", effect: "", newOnHand: "", requestId: ""}});
Set(varFound, Blank()); Set(varRow, Blank()); Set(varTgtRow, Blank());
Set(varFinal, ""); Set(varText, ""); Set(varEffect, ""); Set(varShort, "");
// 5. the local outbox: a request that was filed but never confirmed survives a crash/restart and keeps its RequestID
ClearCollect(colOutbox, {{RequestID: "", SessionID: "", Station: "", RequestType: "", StockKey: "", ItemID: "", LocationCode: "", Quantity: "", ExpectedVersion: "", Reason: "", PayloadJson: "", TargetRequestID: "", Decision: "", ReversesLedgerKey: "", Summary: ""}});
Clear(colOutbox);
IfError(LoadData(colOutbox, "POUOutbox", true), true);
Set(varReq, Blank());
ClearCollect(colStock, {{ID: 0, StockKey: "", ItemID: "", LocationCode: "", ItemName: "", Area: "", MinQty: 0, MaxQty: 0, OnHandQty: 0, StockVersion: 0, LowStockFlag: false, Active: true}});
Clear(colStock)''',
        "OnError": "Notify(\"Something went wrong: \" & FirstError.Message & \". If you were submitting a request, do NOT enter it again - use 'Retry same request'.\", NotificationType.Error)",
    }
