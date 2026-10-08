"""The request-processing core shared by POU-ProcessRequest (instant) and POU-Sweeper (scheduled).

DESIGN RULES (see docs/05_Posting_Design.md):
  1. A request is an instruction. Only a POULedger row in PostingState=Posted is a completed movement.
  2. Stock is never changed unless a ledger Intent row already exists for the request. So "no ledger row for this RequestID"
     (established by a successful query) is the ONLY basis for saying 'nothing was changed' (InventoryEffect=NotApplied).
  3. Per-stock serialisation = unique LedgerKey (StockKey#SeqNo): only one writer can create seq n+1. Duplicate protection =
     unique RequestID in the ledger. If-Match on the stock row protects against any other writer.
  4. The Response action always runs. Its defaults say 'Processing / UNCONFIRMED - do not repeat'; only an explicit
     assignment after verified facts changes that. Scope status is never relied upon.
  5. Expressions are null-safe and never rely on and()/or() short-circuiting. Conditions never reference the output of an
     action that might have been skipped: cross-stage state lives in variables.
  6. An existing ledger row for the RequestID is honoured BEFORE any authorization check: authorization is evaluated once, when
     the intent is created, so a later badge deactivation cannot turn an already-recorded movement into a false 'rejected'.
  7. Every expression stays far below the 8,192-character limit (one small Compose per rule).
"""
from __future__ import annotations

from .common import (L_EMPLOYEES, L_ITEMS, L_LEDGER, L_LOCATIONS, L_REQUESTS, L_SESSIONS, L_STATIONS, L_STOCK, LEDGER_SELECT,
                     MESSAGES, REQ_SELECT, STOCK_SELECT, TERMINAL, cfg, cfgb, cfgi, load_settings, ops_event)
from .dsl import (ALL, Block, Ex, X, and_, cat, coalesce, eq, f, first_nonempty, if_, is_null, not_, nz, o, ok, or_, qv, v)

QTY_TYPES = ["ISSUE", "RECEIPT", "AUDIT", "OPENING", "ADJUSTMENT", "REVERSAL"]
ALL_TYPES = QTY_TYPES + ["ITEM_CREATE", "LOCATION_ADD", "PARAM_UPDATE", "APPROVE"]
ISO = "yyyy-MM-ddTHH:mm:ssZ"
LOCAL_FMT = "yyyy-MM-dd HH:mm:ss"


def _pick(comp, key) -> Ex: return Ex(f"outputs('{comp}')?['{key}']")
def req(k) -> Ex: return _pick("Compose_Req", k)
def sess(k) -> Ex: return _pick("Compose_Session", k)
def semp(k) -> Ex: return _pick("Compose_SessEmp", k)
def stn(k) -> Ex: return _pick("Compose_Station", k)
def stk(k) -> Ex: return _pick("Compose_Stock", k)
def itn(k) -> Ex: return _pick("Compose_Intent", k)
def orig(k) -> Ex: return Ex(f"variables('vRev')?['orig']?['{k}']")
ORIG = Ex("variables('vRev')?['orig']")
def plan(k) -> Ex: return _pick("Compose_Plan", k)
def arr(*items) -> Ex: return f("createArray", *items)
def in_(x, items) -> Ex: return f("contains", arr(*items), x)
def num(x) -> Ex: return Ex(f"coalesce({x}, 0)")
def is_int(x) -> Ex: return and_(not_(is_null(x)), eq(f("mod", num(x), 1), 0))
def s_(x) -> Ex: return f("string", x)
def code_if(cond, code) -> str: return if_(cond, code, "")


def msg_of(code) -> Ex:
    if isinstance(code, Ex):
        return Ex(f"coalesce(outputs('Compose_Messages')?[{code}], {code})")
    return Ex(f"coalesce(outputs('Compose_Messages')?['{code}'], '{code}')")


def checks(blk: Block, prefix: str, items: list, chunk_chars: int = 2600):
    """Evaluate rules (each yields a reject code or '') in a few Composes, then take the first non-empty code.
    Chunked so every expression stays far below the 8,192-character limit (asserted by tests/test_flow_static.py)."""
    chunks, cur, size = [], [], 0
    for label, expr in items:
        if cur and size + len(str(expr)) > chunk_chars:
            chunks.append(cur); cur, size = [], 0
        cur.append((label, expr)); size += len(str(expr))
    if cur:
        chunks.append(cur)
    outs = []
    for i, ch in enumerate(chunks, 1):
        n = f"{prefix}_Rules{i}_" + "_".join(l for l, _ in ch[:1]) + (f"_to_{ch[-1][0]}" if len(ch) > 1 else "")
        blk.compose(n, X(first_nonempty([Ex(str(e)) for _, e in ch])))
        outs.append(o(n))
    name = f"{prefix}_Result"
    if len(outs) == 1:
        blk.compose(name, X(outs[0]))
    else:
        blk.compose(name, X(first_nonempty(outs)))
    return name


T = req("RequestType")
CONT = eq(Ex("variables('vRes')?['outcome']"), "continue")
INTENT_NONE = eq(v("vIntent"), "none")
RUN = and_(CONT, INTENT_NONE)


def vres(k) -> Ex:
    return Ex(f"variables('vRes')?['{k}']")


def result(blk: Block, name, status, code, message=None, effect=None, finalize=True, outcome="done", ledger=None, newonhand=None, auth_by=None, **kw):
    """ONE SetVariable that replaces the whole outcome object (keeps the action count low and the state atomic)."""
    obj = {"outcome": outcome, "status": status, "code": code,
           "message": message if message is not None else msg_of(code),
           "finalize": "yes" if finalize else "no", "effect": effect if effect is not None else "",
           "ledger": ledger if ledger is not None else "", "newOnHand": newonhand if newonhand is not None else "",
           "authBy": auth_by if auth_by is not None else ""}
    return blk.set_var("vRes", obj, name=name, **kw)


def reject(blk, name, code, message=None, **kw):
    return result(blk, name, "Rejected", code, message, effect="NotApplied", **kw)


DEFAULT_MESSAGE = ("Not confirmed yet. Do NOT repeat this action: it may already have been recorded. "
                   "The system is still checking and will finish it automatically.")
RES_DEFAULT = {"outcome": "continue", "status": "Processing", "code": "UNCONFIRMED", "message": DEFAULT_MESSAGE, "finalize": "no",
               "effect": "", "ledger": "", "newOnHand": "", "authBy": ""}
AUTH_DEFAULT = {"isSup": False, "isAdmin": False, "name": "", "decision": "", "approver": ""}
REV_DEFAULT = {"orig": None, "existing": False}
VAR_DEFAULTS = [("vRes", "object", RES_DEFAULT), ("vAuth", "object", AUTH_DEFAULT), ("vRev", "object", REV_DEFAULT), ("vAttempt", "integer", 0), ("vIntent", "string", "none"), ("vSeq", "integer", 0),
                ("vApplied", "string", "no"), ("vApplyTries", "integer", 0), ("vAttempts", "integer", 0), ("vSessionItem", "string", "")]


def init_vars(blk: Block):
    for n, t, val in VAR_DEFAULTS:
        blk.init_var(n, t, val)


def reset_vars(blk: Block):
    blk.set_many("Reset_vars", {n: val for n, _, val in VAR_DEFAULTS})


# =====================================================================================================================
def build_core(c: Block):
    load_settings(c)
    c.compose("Compose_Messages", MESSAGES)
    c.sp_get("Get_request", L_REQUESTS, ["RequestID eq '", qv(o("Compose_RequestIdIn")), "'"], select=REQ_SELECT, expand="Author", top=2)
    c.compose("Compose_Req", X("first(body('Get_request')?['d']?['results'])"))
    c.cond("If_request_missing", is_null(o("Compose_Req")),
           lambda t: result(t, "Result_not_found", "NotFound", "REQUEST_NOT_FOUND",
                            "That request was not found. If you just created it, wait a moment; otherwise it was never recorded.", finalize=False))
    stage_triage_claim(c)
    stage_existing_ledger(c)
    c.cond("Stage_giveup", and_(RUN, Ex(f"greater(variables('vAttempts'), {cfgi('MaxProcessAttempts', 5)})")),
           lambda t: reject(t, "Result_gave_up", "GAVE_UP"))   # no ledger row exists here, so NotApplied is established
    c.cond("Stage_context_auth", RUN, stage_context_auth)
    c.cond("Dispatch_quantity", and_(RUN, in_(T, QTY_TYPES)), stage_post_loop)
    c.cond("Dispatch_master", and_(RUN, in_(T, ["ITEM_CREATE", "LOCATION_ADD"])), stage_master)
    c.cond("Dispatch_param", and_(RUN, eq(T, "PARAM_UPDATE")), stage_param)
    c.cond("Dispatch_approve", and_(RUN, eq(T, "APPROVE")), stage_approve)
    c.cond("Stage_apply", and_(CONT, eq(v("vIntent"), "ours")), stage_apply)
    stage_finalize(c)


# ---------------------------------------------------------------------------------------------------------------------
def stage_triage_claim(c: Block):
    c.compose("Compose_Status", X(coalesce(req("RequestStatus"), "")))
    c.cond("If_already_terminal", and_(CONT, in_(o("Compose_Status"), TERMINAL)),
           lambda t: result(t, "Result_stored", Ex("outputs('Compose_Status')"), X(coalesce(req("ResultCode"), "")),
                            X(coalesce(req("ResultMessage"), "")), effect=X(coalesce(req("InventoryEffect"), "")),
                            finalize=False, ledger=X(coalesce(req("LedgerKey"), ""))))
    c.compose("Compose_ClaimDecision", X(
        "if(and(equals(outputs('Compose_Status'), 'Processing'), "
        f"less(sub(ticks(utcNow()), ticks(coalesce({req('ClaimedUtc')}, '2000-01-01T00:00:00Z'))), mul({cfgi('StaleClaimSeconds', 120)}, 10000000))), 'busy', 'claim')"))
    c.cond("If_busy_elsewhere", and_(CONT, eq(o("Compose_ClaimDecision"), "busy")),
           lambda t: result(t, "Result_busy", "Processing", "IN_PROGRESS",
                            "Being processed right now. Do not repeat; the status will update.", finalize=False))
    attempts = f"if(equals(outputs('Compose_Status'), 'AwaitingSupervisor'), 1, add(int(coalesce({req('AttemptCount')}, 0)), 1))"

    def claim(t: Block):
        t.attempt("Claim_request", lambda s, n: s.sp_update(
            n, L_REQUESTS, X(req("Id")),
            {"RequestStatus": "Processing", "ProcessingRunId": X("workflow()['run']['name']"), "ClaimedUtc": X(f"utcNow('{ISO}')"),
             "AttemptCount": X(attempts), "IsOpen": True},
            etag=X(Ex("outputs('Compose_Req')?['__metadata']?['etag']"))))
        t.cond("If_claim_lost", Ex(f"not({ok('Claim_request')})"),
               lambda u: result(u, "Result_claim_lost", "Processing", "CLAIM_LOST",
                                "Another worker is processing this request. Do not repeat; the status will update.", finalize=False),
               lambda u: u.set_var("vAttempts", X(attempts), name="Set_vAttempts"), always=True)
    c.cond("Stage_claim", CONT, claim)


def stage_existing_ledger(c: Block):
    """Honour an existing ledger row for this RequestID BEFORE any authorization (design rule 6)."""
    def existing(t: Block):
        t.sp_get("Get_existing_ledger", L_LEDGER, ["RequestID eq '", qv(o("Compose_RequestIdIn")), "'"], select=LEDGER_SELECT, top=2)
        t.compose("Compose_ExistingLedger", X("first(body('Get_existing_ledger')?['d']?['results'])"))
        t.cond("If_existing_posted", Ex("and(not(equals(outputs('Compose_ExistingLedger'), null)), equals(outputs('Compose_ExistingLedger')?['PostingState'], 'Posted'))"),
               lambda u: (u.compose("Compose_PostedMessage", X(success_message("Compose_ExistingLedger"))),
                          result(u, "Result_already_posted", "Succeeded", "OK", X(o("Compose_PostedMessage")), effect="Applied",
                                 ledger=X(Ex("outputs('Compose_ExistingLedger')?['LedgerKey']")),
                                 newonhand=X(s_(Ex("outputs('Compose_ExistingLedger')?['QtyAfter']"))),
                                 auth_by=X(coalesce(Ex("outputs('Compose_ExistingLedger')?['AuthorizedByUPN']"), "")))))
        t.cond("If_existing_intent", Ex("and(not(equals(outputs('Compose_ExistingLedger'), null)), equals(outputs('Compose_ExistingLedger')?['PostingState'], 'Intent'))"),
               lambda u: u.set_var("vIntent", "ours", name="Set_vIntent_resume"))
    c.cond("Stage_existing_ledger", and_(CONT, in_(T, QTY_TYPES)), existing)


# ---------------------------------------------------------------------------------------------------------------------
def stage_context_auth(t: Block):
    t.sp_get("Get_session", L_SESSIONS, ["SessionID eq '", qv(coalesce(req("SessionID"), "NONE")), "'"],
             select="Id,SessionID,BadgeID,EmployeeName,StationID,AppAccountUPN,LastActivityUtc,SessionState", top=2)
    t.compose("Compose_Session", X("first(body('Get_session')?['d']?['results'])"))
    t.sp_get("Get_session_employee", L_EMPLOYEES, ["BadgeID eq '", qv(coalesce(sess("BadgeID"), "NONE")), "'"],
             select="Id,BadgeID,EmployeeName,Active,Role,MicrosoftUPN", top=2)
    t.compose("Compose_SessEmp", X("first(body('Get_session_employee')?['d']?['results'])"))
    t.sp_get("Get_station", L_STATIONS, ["StationID eq '", qv(coalesce(req("StationID"), "NONE")), "'"],
             select="Id,StationID,Active,ExpectedAccountUPN", top=2)
    t.compose("Compose_Station", X("first(body('Get_station')?['d']?['results'])"))
    t.compose("Compose_AuthorEmail", X("toLower(coalesce(outputs('Compose_Req')?['Author']?['EMail'], ''))"))
    t.compose("Compose_NeedsAuthority", X(or_(
        and_(eq(T, "AUDIT"), cfgb("RequireSupervisorForAudit", "true")),
        and_(in_(T, ["ITEM_CREATE", "LOCATION_ADD"]), cfgb("RequireSupervisorForNewItem", "true")),
        eq(T, "PARAM_UPDATE"))))

    def privileged(p: Block):
        """Supervisor/admin lookups: skipped for ISSUE/RECEIPT, which always need a badge session and never need authority."""
        p.sp_get("Get_privileged", L_EMPLOYEES, ["Active eq 1 and Role ne 'Operator'"], select="Id,BadgeID,EmployeeName,Role,MicrosoftUPN", top=200)
        p.sp_get("Get_approvals", L_REQUESTS, ["TargetRequestID eq '", qv(o("Compose_RequestIdIn")), "' and RequestType eq 'APPROVE'"],
                 select="Id,Decision,Author/EMail", expand="Author", orderby="ID desc", top=10)
        p.filter_array("Filter_priv_with_upn", X("body('Get_privileged')?['d']?['results']"), X("not(empty(coalesce(item()?['MicrosoftUPN'], '')))"))
        p.select("Select_priv_upns", X("body('Filter_priv_with_upn')"), X("toLower(item()?['MicrosoftUPN'])"))
        p.filter_array("Filter_author_emp", X("body('Filter_priv_with_upn')"), X("equals(toLower(item()?['MicrosoftUPN']), outputs('Compose_AuthorEmail'))"))
        p.compose("Compose_AuthorEmp", X("first(body('Filter_author_emp'))"))
        p.filter_array("Filter_valid_approvals", X("body('Get_approvals')?['d']?['results']"), X(
            "and(contains(body('Select_priv_upns'), toLower(coalesce(item()?['Author']?['EMail'], ''))), "
            "not(equals(toLower(coalesce(item()?['Author']?['EMail'], '')), outputs('Compose_AuthorEmail'))), "
            "not(equals(toLower(coalesce(item()?['Author']?['EMail'], '')), toLower(coalesce(outputs('Compose_SessEmp')?['MicrosoftUPN'], '')))))"))
        p.compose("Compose_Approval", X("first(body('Filter_valid_approvals'))"))
        p.set_var("vAuth", {
            "isSup": X("and(not(empty(outputs('Compose_AuthorEmail'))), contains(body('Select_priv_upns'), outputs('Compose_AuthorEmail')))"),
            "isAdmin": X("and(not(empty(outputs('Compose_AuthorEmail'))), equals(coalesce(outputs('Compose_AuthorEmp')?['Role'], ''), 'Admin'))"),
            "name": X("coalesce(outputs('Compose_AuthorEmp')?['EmployeeName'], outputs('Compose_AuthorEmail'))"),
            "decision": X("coalesce(outputs('Compose_Approval')?['Decision'], '')"),
            "approver": X("toLower(coalesce(outputs('Compose_Approval')?['Author']?['EMail'], ''))")}, name="Set_vAuth")
    t.cond("If_privileged_lookup", Ex(str(not_(in_(T, ["ISSUE", "RECEIPT"])))), privileged)

    isSup, isAdmin = Ex("variables('vAuth')?['isSup']"), Ex("variables('vAuth')?['isAdmin']")
    decision = Ex("variables('vAuth')?['decision']")
    sr = or_(not_(isSup), in_(T, ["ISSUE", "RECEIPT"]))      # a badge session is required unless the request is authored by an authenticated supervisor
    checks(t, "Auth", [
        ("type_known", code_if(not_(in_(T, ALL_TYPES)), "UNKNOWN_TYPE")),
        ("type_authority", code_if(or_(and_(in_(T, ["ADJUSTMENT", "REVERSAL", "APPROVE"]), not_(isSup)), and_(eq(T, "OPENING"), not_(isAdmin))), "NOT_AUTHORIZED")),
        ("session_missing", code_if(and_(sr, is_null(o("Compose_Session"))), "NO_SESSION")),
        ("session_state", code_if(and_(sr, not_(eq(coalesce(sess("SessionState"), ""), "Active"))), "SESSION_ENDED")),
        ("session_account", code_if(and_(sr, not_(eq(f("toLower", coalesce(sess("AppAccountUPN"), "")), o("Compose_AuthorEmail")))), "SESSION_ACCOUNT_MISMATCH")),
        ("session_idle", code_if(and_(sr, f("greater",
                                             f("sub", f("ticks", coalesce(req("Created"), "2000-01-01T00:00:00Z")),
                                               f("ticks", coalesce(sess("LastActivityUtc"), req("Created"), "2000-01-01T00:00:00Z"))),
                                             f("mul", cfgi("ServerSessionMaxIdleMinutes", 10), 600000000))), "SESSION_EXPIRED")),
        ("employee_active", code_if(and_(sr, or_(is_null(o("Compose_SessEmp")), not_(eq(semp("Active"), True)))), "EMPLOYEE_INACTIVE")),
        ("station_active", code_if(and_(sr, or_(is_null(o("Compose_Station")), not_(eq(stn("Active"), True)))), "STATION_INVALID")),
        ("station_match", code_if(and_(sr, not_(eq(coalesce(sess("StationID"), ""), coalesce(req("StationID"), "")))), "STATION_MISMATCH")),
        ("station_account", code_if(and_(sr, nz(coalesce(stn("ExpectedAccountUPN"), "")),
                                         not_(eq(f("toLower", coalesce(stn("ExpectedAccountUPN"), "")), o("Compose_AuthorEmail")))), "STATION_ACCOUNT_MISMATCH")),
        ("supervisor_rejected", code_if(and_(o("Compose_NeedsAuthority"), not_(isSup), eq(decision, "Reject")), "SUPERVISOR_REJECTED")),
    ])
    t.compose("Compose_AuthBy", X(if_(isSup, o("Compose_AuthorEmail"), if_(eq(decision, "Approve"), Ex("variables('vAuth')?['approver']"), ""))))
    t.compose("Compose_Actor", {"badge": X(if_(isSup, "", coalesce(sess("BadgeID"), ""))),
                                "name": X(if_(isSup, Ex("variables('vAuth')?['name']"), coalesce(sess("EmployeeName"), "")))})
    t.set_var("vSessionItem", X(s_(coalesce(sess("Id"), ""))), name="Set_vSessionItem")
    t.cond("If_reject_auth", nz(o("Auth_Result")),
           lambda u: reject(u, "Result_auth_reject", Ex("outputs('Auth_Result')"), X(msg_of(Ex("outputs('Auth_Result')")))))
    t.cond("If_await_supervisor", and_(CONT, o("Compose_NeedsAuthority"), not_(isSup), not_(eq(decision, "Approve"))),
           lambda u: result(u, "Result_await", "AwaitingSupervisor", "NEEDS_SUPERVISOR",
                            "Waiting for a supervisor to approve. They approve from their own device; nothing has been changed yet.",
                            effect="NotApplied"))


# ---------------------------------------------------------------------------------------------------------------------
def success_message(comp: str) -> Ex:
    """Human message from a ledger row held in Compose <comp>."""
    g = lambda k: Ex(f"outputs('{comp}')?['{k}']")
    item = f"concat({g('ItemID')}, ' @ ', {g('LocationCode')})"
    return Ex(
        f"if(equals({g('LedgerType')}, 'ISSUE'), concat('Removed ', string(sub(0, int(coalesce({g('QtyDelta')}, 0)))), ' x ', {item}, '. On hand now ', string({g('QtyAfter')}), '.'), "
        f"if(equals({g('LedgerType')}, 'RECEIPT'), concat('Added ', string(coalesce({g('QtyDelta')}, 0)), ' x ', {item}, '. On hand now ', string({g('QtyAfter')}), '.'), "
        f"if(equals({g('LedgerType')}, 'AUDIT'), concat('Count recorded for ', {item}, ': ', string({g('QtyAfter')}), if(equals({g('QtyBefore')}, null), ' (first count - no previous balance).', concat(' (system had ', string({g('QtyBefore')}), ').'))), "
        f"if(equals({g('LedgerType')}, 'OPENING'), concat('Opening balance recorded for ', {item}, ': ', string({g('QtyAfter')}), '.'), "
        f"concat({g('LedgerType')}, ' recorded for ', {item}, '. On hand now ', string({g('QtyAfter')}), '.')))))")


def stage_post_loop(t: Block):
    """Validate, then create the ledger intent (unique LedgerKey = compare-and-swap). Re-reads and retries on contention."""
    t.set_many("Post_init", {"vAttempt": 0})

    def body(l: Block):
        l.inc_var("vAttempt", 1, name="Loop_inc_attempt")
        l.sp_get("Get_stock", L_STOCK, ["StockKey eq '", qv(coalesce(req("StockKey"), "NONE")), "'"], select=STOCK_SELECT, top=2)
        l.compose("Compose_Stock", X("first(body('Get_stock')?['d']?['results'])"))
        l.cond("If_stock_missing", and_(RUN, is_null(o("Compose_Stock"))), lambda u: reject(u, "Result_stock_missing", "STOCK_NOT_FOUND"))
        def reversal_lookup(r: Block):
            r.sp_get("Get_original_ledger", L_LEDGER, ["LedgerKey eq '", qv(coalesce(req("ReversesLedgerKey"), "NONE")), "'"], select=LEDGER_SELECT, top=2)
            r.sp_get("Get_reversal_existing", L_LEDGER,
                     ["ReversesLedgerKey eq '", qv(coalesce(req("ReversesLedgerKey"), "NONE")), "' and PostingState ne 'Voided'"], select="Id,LedgerKey,PostingState", top=2)
            r.set_var("vRev", {"orig": X("first(body('Get_original_ledger')?['d']?['results'])"),
                               "existing": X("not(empty(body('Get_reversal_existing')?['d']?['results']))")}, name="Set_vRev")
        l.cond("If_reversal_lookup", and_(RUN, eq(T, "REVERSAL")), reversal_lookup)
        Q, before, ver = req("Quantity"), stk("OnHandQty"), num(stk("StockVersion"))
        rev_after = f("sub", num(before), num(orig("QtyDelta")))
        checks(l, "Post", [
            ("stock_active", code_if(not_(eq(stk("Active"), True)), "STOCK_INACTIVE")),
            ("qty_positive", code_if(and_(in_(T, ["ISSUE", "RECEIPT"]), or_(not_(is_int(Q)), f("less", num(Q), 1))), "INVALID_QUANTITY")),
            ("count_valid", code_if(and_(in_(T, ["AUDIT", "OPENING", "ADJUSTMENT"]), or_(not_(is_int(Q)), f("less", num(Q), 0))), "INVALID_COUNT")),
            ("receipt_limit", code_if(and_(eq(T, "RECEIPT"), f("greater", num(Q), cfgi("MaxAddQty", 500))), "QUANTITY_OVER_LIMIT")),
            ("has_balance", code_if(and_(in_(T, ["ISSUE", "RECEIPT", "ADJUSTMENT", "REVERSAL"]), is_null(before)), "NO_BALANCE")),
            ("verified_only", code_if(and_(in_(T, ["ISSUE", "RECEIPT"]), not_(cfgb("AllowIssueAgainstUnverified", "true")),
                                           not_(eq(stk("BalanceStatus"), "Verified"))), "BALANCE_UNVERIFIED")),
            ("enough_stock", code_if(and_(eq(T, "ISSUE"), f("greater", num(Q), num(before))), "INSUFFICIENT_STOCK")),
            ("audit_has_version", code_if(and_(eq(T, "AUDIT"), is_null(req("ExpectedVersion"))), "MISSING_EXPECTED_VERSION")),
            ("audit_not_stale", code_if(and_(eq(T, "AUDIT"), not_(is_null(req("ExpectedVersion"))), not_(eq(num(req("ExpectedVersion")), ver))), "STALE_COUNT")),
            ("opening_allowed", code_if(and_(eq(T, "OPENING"), not_(and_(is_null(before), eq(ver, 0)))), "OPENING_NOT_ALLOWED")),
            ("reason_given", code_if(and_(in_(T, ["ADJUSTMENT", "REVERSAL"]), f("empty", f("trim", coalesce(req("Reason"), "")))), "REASON_REQUIRED")),
            ("rev_target", code_if(and_(eq(T, "REVERSAL"), is_null(ORIG)), "REVERSAL_TARGET_MISSING")),
            ("rev_posted", code_if(and_(eq(T, "REVERSAL"), not_(is_null(ORIG)),
                                        or_(not_(eq(orig("PostingState"), "Posted")), not_(eq(orig("AffectsBalance"), True)),
                                            not_(in_(orig("LedgerType"), ["ISSUE", "RECEIPT"])))), "REVERSAL_NOT_POSTED")),
            ("rev_same_stock", code_if(and_(eq(T, "REVERSAL"), not_(is_null(ORIG)),
                                            not_(eq(coalesce(orig("StockKey"), ""), coalesce(req("StockKey"), "")))), "REVERSAL_WRONG_STOCK")),
            ("rev_once", code_if(and_(eq(T, "REVERSAL"), eq(Ex("variables('vRev')?['existing']"), True)), "REVERSAL_ALREADY")),
            ("rev_non_negative", code_if(and_(eq(T, "REVERSAL"), not_(is_null(ORIG)), not_(is_null(before)), f("less", rev_after, 0)), "REVERSAL_NEGATIVE")),
        ])
        pr = o("Post_Result")
        dyn = X(Ex(
            f"if(equals({pr}, 'INSUFFICIENT_STOCK'), concat('Only ', string({num(before)}), ' on hand - cannot remove ', string({num(Q)}), '. Nothing was changed.'), "
            f"if(equals({pr}, 'QUANTITY_OVER_LIMIT'), concat('Quantity ', string({num(Q)}), ' is over the limit of ', string({cfgi('MaxAddQty', 500)}), ' for one ADD - was a part number scanned into Quantity? Nothing was changed.'), "
            f"if(equals({pr}, 'STALE_COUNT'), concat('Stock changed since you started counting (it is now version ', string({ver}), ', on hand ', string({num(before)}), '). Recount. Nothing was changed.'), "
            f"coalesce(outputs('Compose_Messages')?[{pr}], {pr}))))"))
        l.cond("If_post_reject", and_(RUN, nz(pr)), lambda u: reject(u, "Result_post_reject", Ex(str(pr)), dyn))

        def plan_ok(p: Block):
            after = if_(eq(T, "ISSUE"), f("sub", before, Q), if_(eq(T, "RECEIPT"), f("add", before, Q), if_(eq(T, "REVERSAL"), rev_after, Q)))
            delta = if_(eq(T, "ISSUE"), f("sub", 0, Q), if_(eq(T, "RECEIPT"), Q, if_(eq(T, "OPENING"), None,
                        if_(eq(T, "REVERSAL"), f("sub", 0, num(orig("QtyDelta"))), if_(is_null(before), None, f("sub", Q, before))))))
            p.compose("Compose_Plan", {"seq": X(f("add", ver, 1)), "before": X(before), "after": X(f("int", after)),
                                       "delta": X(if_(is_null(delta), None, f("int", delta)))})
            p.sp_get("Get_prev_ledger", L_LEDGER,
                     ["LedgerKey eq '", qv(if_(f("greater", ver, 0), cat(stk("StockKey"), "#", s_(ver)), "NONE")), "'"], select=LEDGER_SELECT, top=2)
            p.compose("Compose_Prev", X("first(body('Get_prev_ledger')?['d']?['results'])"))
            # chain integrity: version 0 must have no balance; version n must equal the Posted/Intent row n's QtyAfter
            p.compose("Compose_ChainBad", X(if_(eq(ver, 0), not_(is_null(before)),
                                                 or_(is_null(o("Compose_Prev")), not_(in_(_pick("Compose_Prev", "PostingState"), ["Posted", "Intent"])),
                                                     not_(eq(_pick("Compose_Prev", "QtyAfter"), before))))))

            def chain_bad(u: Block):
                ops_event(u, "Drift", cat("DRIFT|", stk("StockKey")), "DRIFT", "Critical", cat("Balance does not match ledger: ", stk("StockKey")),
                          cat("StockKey ", stk("StockKey"), " has OnHandQty=", s_(before), " version ", s_(ver),
                              " but the ledger row for that version is missing or disagrees. Posting is blocked for this record until reconciled. Request ",
                              o("Compose_RequestIdIn"), "."))
                result(u, "Result_drift", "Failed", "DRIFT_DETECTED", effect="NotApplied", always=True)
            p.cond("If_chain_bad", eq(o("Compose_ChainBad"), True), chain_bad)

            def create_intent(q: Block):
                q.attempt("Create_intent", lambda s, n: s.sp_create(n, L_LEDGER, {
                    "Title": cat(stk("StockKey"), " #", s_(plan("seq"))),
                    "LedgerKey": cat(stk("StockKey"), "#", s_(plan("seq"))), "RequestID": X(o("Compose_RequestIdIn")), "LedgerType": X(T),
                    "Origin": "Live", "AffectsBalance": True, "PostingState": "Intent",
                    "StockKey": X(stk("StockKey")), "ItemID": X(stk("ItemID")), "LocationCode": X(stk("LocationCode")),
                    "SeqNo": X(plan("seq")), "QtyDelta": X(plan("delta")), "QtyBefore": X(plan("before")), "QtyAfter": X(plan("after")),
                    "BadgeID": X(Ex("outputs('Compose_Actor')?['badge']")), "EmployeeName": X(Ex("outputs('Compose_Actor')?['name']")),
                    "StationID": X(coalesce(req("StationID"), "")), "AuthorizedByUPN": X(o("Compose_AuthBy")),
                    "OccurredUtc": X(coalesce(req("Created"), Ex(f"utcNow('{ISO}')"))),
                    "OccurredLocalText": X(f"convertFromUtc(coalesce({req('Created')}, utcNow('{ISO}')), coalesce({cfg('DisplayTimeZoneWindows')}, 'Central Standard Time'), '{LOCAL_FMT}')"),
                    "Reason": X(coalesce(req("Reason"), "")), "ReversesLedgerKey": X(coalesce(req("ReversesLedgerKey"), "")),
                }))
                q.cond("If_intent_created", ok("Create_intent"),
                       lambda u: u.set_many("Set_intent_ours", {"vIntent": "ours", "vSeq": X(plan("seq"))}),
                       lambda e: (e.sp_get("Get_ledger_after_create", L_LEDGER, ["RequestID eq '", qv(o("Compose_RequestIdIn")), "'"], select=LEDGER_SELECT, top=2),
                                  e.compose("Compose_AfterCreate", X("first(body('Get_ledger_after_create')?['d']?['results'])")),
                                  e.cond("If_ours_after_failed_create", Ex("not(equals(outputs('Compose_AfterCreate'), null))"),
                                         lambda w: w.set_var("vIntent", "ours", name="Set_vIntent_after_create"),
                                         lambda w: w.delay("Wait_for_contention", 2))),
                       always=True)
            p.cond("If_create_intent", RUN, create_intent)
        l.cond("If_plan_ok", and_(RUN, eq(o("Post_Result"), "")), plan_ok)

    t.until("Until_intent", or_(eq(vres("outcome"), "done"), eq(v("vIntent"), "ours"), f("greaterOrEquals", v("vAttempt"), 4)), body, count=6)
    # still no intent after the retries: give the claim back; the sweeper retries (nothing has been written)
    t.cond("If_contention_exhausted", RUN,
           lambda u: result(u, "Result_contention", "Pending", "CONTENTION",
                            "Busy - another transaction on this item is finishing. It will be retried automatically; do not repeat it."))


# ---------------------------------------------------------------------------------------------------------------------
def stage_apply(t: Block):
    """The intent row is ours. Make the stock row match it (idempotent), then mark the ledger row Posted."""
    t.sp_get("Get_intent_row", L_LEDGER, ["RequestID eq '", qv(o("Compose_RequestIdIn")), "'"], select=LEDGER_SELECT + ",AuthorizedByUPN", top=2)
    t.compose("Compose_Intent", X("first(body('Get_intent_row')?['d']?['results'])"))
    t.cond("If_intent_row_missing", is_null(o("Compose_Intent")),
           lambda u: result(u, "Result_intent_missing", "Processing", "INTENT_NOT_FOUND",
                            "Could not read the record just written. Do not repeat; it will be re-checked automatically.", finalize=False))

    def apply_body(a: Block):
        a.set_many("Apply_init", {"vApplyTries": 0, "vApplied": "no"})

        def loop(l: Block):
            l.inc_var("vApplyTries", 1, name="Apply_inc_tries")
            l.sp_get("Get_stock_apply", L_STOCK, ["StockKey eq '", qv(itn("StockKey")), "'"], select=STOCK_SELECT, top=2)
            l.compose("Compose_StockApply", X("first(body('Get_stock_apply')?['d']?['results'])"))
            sv, oh = _pick("Compose_StockApply", "StockVersion"), _pick("Compose_StockApply", "OnHandQty")
            seq, qa, qb = itn("SeqNo"), itn("QtyAfter"), itn("QtyBefore")
            l.compose("Compose_ApplyState", X(
                f"if(equals(outputs('Compose_StockApply'), null), 'anomaly', "
                f"if(and(equals({sv}, {seq}), equals({oh}, {qa})), 'applied', "
                f"if(and(equals({sv}, sub({seq}, 1)), if(equals({qb}, null), equals({oh}, null), equals({oh}, {qb}))), 'unapplied', 'anomaly')))"))
            l.cond("If_state_applied", and_(CONT, eq(o("Compose_ApplyState"), "applied")),
                   lambda u: u.set_var("vApplied", "yes", name="Set_vApplied_already"))
            minq = _pick("Compose_StockApply", "MinQty")
            low = and_(not_(is_null(minq)), if_(eq(cfg("LowStockRule"), "LT"), f("less", qa, minq), f("lessOrEquals", qa, minq)))

            def do_apply(u: Block):
                u.attempt("Apply_stock", lambda s, n: s.sp_update(
                    n, L_STOCK, X(_pick("Compose_StockApply", "Id")),
                    {"OnHandQty": X(qa), "StockVersion": X(seq),
                     "BalanceStatus": X(if_(eq(itn("LedgerType"), "OPENING"), "Unverified",
                                            if_(eq(itn("LedgerType"), "AUDIT"), "Verified", coalesce(_pick("Compose_StockApply", "BalanceStatus"), "NoBalance")))),
                     "LowStockFlag": X(low), "LastLedgerKey": X(itn("LedgerKey")), "LastPostedUtc": X(f"utcNow('{ISO}')"),
                     "LastCountedUtc": X(if_(in_(itn("LedgerType"), ["AUDIT", "OPENING"]), Ex(f"utcNow('{ISO}')"), _pick("Compose_StockApply", "LastCountedUtc")))},
                    etag=X(Ex("outputs('Compose_StockApply')?['__metadata']?['etag']"))))
                u.cond("If_apply_ok", ok("Apply_stock"), lambda w: w.set_var("vApplied", "yes", name="Set_vApplied_ok"), always=True)
            l.cond("If_state_unapplied", and_(CONT, eq(o("Compose_ApplyState"), "unapplied")), do_apply)

            def anomaly(u: Block):
                ops_event(u, "Anom", cat("ANOMALY|", itn("LedgerKey")), "STOCK_ANOMALY", "Critical",
                          cat("Stock changed outside the posting process: ", itn("StockKey")),
                          cat("Intent ", itn("LedgerKey"), " expected stock version ", s_(Ex(f"sub({seq}, 1)")), " (before) or ", s_(seq),
                              " (after), found version ", s_(sv), " on hand ", s_(oh), ". The intent was voided; this request changed nothing."))
                u.sp_update("Void_intent", L_LEDGER, X(itn("Id")),
                            {"LedgerKey": cat("VOID|", f("guid")), "RequestID": cat("VOID|", f("guid")), "PostingState": "Voided",
                             "Reason": cat("Voided: stock changed outside protocol. Original request ", itn("RequestID"))}, always=True)
                result(u, "Result_anomaly", "Failed", "STOCK_CHANGED_OUTSIDE_PROTOCOL", effect="NotApplied", always=True)
            l.cond("If_state_anomaly", and_(CONT, eq(o("Compose_ApplyState"), "anomaly")), anomaly)
        a.until("Until_apply", or_(eq(v("vApplied"), "yes"), eq(vres("outcome"), "done"), f("greaterOrEquals", v("vApplyTries"), 3)), loop, count=5)

        def finalize_ledger(u: Block):
            u.attempt("Finalize_ledger", lambda s, n: s.sp_update(n, L_LEDGER, X(itn("Id")), {"PostingState": "Posted"}))
            u.compose("Compose_SuccessMessage", X(success_message("Compose_Intent")), always=True)
            u.cond("If_ledger_posted", ok("Finalize_ledger"),
                   lambda w: result(w, "Result_success", "Succeeded", "OK", X(o("Compose_SuccessMessage")), effect="Applied",
                                    ledger=X(itn("LedgerKey")), newonhand=X(s_(itn("QtyAfter"))), auth_by=X(coalesce(itn("AuthorizedByUPN"), ""))),
                   lambda w: result(w, "Result_finalizing", "Processing", "FINALIZING",
                                    "The quantity WAS updated. Confirming the record. Do not repeat this; it will complete automatically.",
                                    effect="Applied", ledger=X(itn("LedgerKey")), newonhand=X(s_(itn("QtyAfter"))), finalize=False),
                   always=True)
        a.cond("If_applied_finalize", and_(CONT, eq(v("vApplied"), "yes")), finalize_ledger)
        a.cond("If_apply_pending", and_(CONT, eq(v("vApplied"), "no")),
               lambda u: result(u, "Result_apply_pending", "Processing", "APPLY_PENDING",
                                "Not confirmed yet. Do not repeat; it will be completed automatically.", finalize=False))
    t.cond("If_intent_row_present", and_(CONT, Ex("not(equals(outputs('Compose_Intent'), null))")), apply_body)


# ---------------------------------------------------------------------------------------------------------------------
def stage_master(t: Block):
    """ITEM_CREATE / LOCATION_ADD - idempotent: rows carry CreatedViaRequestID so a retry adopts its own earlier writes."""
    P = lambda k: Ex(f"outputs('Compose_Payload')?['{k}']")
    RID = o("Compose_RequestIdIn")
    t.compose("Compose_Payload", X("json(coalesce(" + str(req("PayloadJson")) + ", '{}'))"))
    t.compose("Compose_MItem", X("toUpper(trim(replace(string(coalesce(" + str(P("ItemID")) + ", '')), '*', '')))"))
    t.compose("Compose_MLocIn", X("trim(string(coalesce(" + str(P("LocationCode")) + ", '')))"))
    t.sp_get("Get_m_location", L_LOCATIONS, ["LocationCode eq '", qv(coalesce(o("Compose_MLocIn"), "NONE")), "'"], select="Id,LocationCode,Active", top=2)
    t.compose("Compose_MLoc", X("first(body('Get_m_location')?['d']?['results'])"))
    t.compose("Compose_MStockKey", X("concat(outputs('Compose_MItem'), '|', toUpper(coalesce(outputs('Compose_MLoc')?['LocationCode'], '')))"))
    t.sp_get("Get_m_item", L_ITEMS, ["ItemID eq '", qv(coalesce(o("Compose_MItem"), "NONE")), "'"], select="Id,ItemID,ItemName,CreatedViaRequestID", top=2)
    t.compose("Compose_MItemRow", X("first(body('Get_m_item')?['d']?['results'])"))
    t.sp_get("Get_m_stock", L_STOCK, ["StockKey eq '", qv(o("Compose_MStockKey")), "'"], select=STOCK_SELECT, top=2)
    t.compose("Compose_MStockRow", X("first(body('Get_m_stock')?['d']?['results'])"))
    mn, mx = P("MinQty"), P("MaxQty")
    me = lambda row, k: Ex(f"outputs('{row}')?['{k}']")
    ours = lambda row: eq(me(row, "CreatedViaRequestID"), RID)
    checks(t, "Master", [
        ("item_id_valid", code_if(or_(f("empty", o("Compose_MItem")), f("contains", o("Compose_MItem"), "|"), f("contains", o("Compose_MItem"), " ")), "PAYLOAD_INVALID")),
        ("name_given", code_if(and_(eq(T, "ITEM_CREATE"), f("empty", f("trim", Ex(f"string(coalesce({P('ItemName')}, ''))")))), "PAYLOAD_INVALID")),
        ("min_max_valid", code_if(or_(not_(is_int(mn)), not_(is_int(mx)), f("less", num(mn), 0), f("greater", num(mn), num(mx))), "PAYLOAD_INVALID")),
        ("location_known", code_if(or_(is_null(o("Compose_MLoc")), not_(eq(me("Compose_MLoc", "Active"), True))), "LOCATION_UNKNOWN")),
        ("item_new", code_if(and_(eq(T, "ITEM_CREATE"), not_(is_null(o("Compose_MItemRow"))), not_(ours("Compose_MItemRow"))), "ITEM_EXISTS")),
        ("item_for_location", code_if(and_(eq(T, "LOCATION_ADD"), is_null(o("Compose_MItemRow"))), "ITEM_NOT_FOUND")),
        ("stock_new", code_if(and_(not_(is_null(o("Compose_MStockRow"))), not_(ours("Compose_MStockRow"))), "STOCK_EXISTS")),
    ])
    mr = o("Master_Result")
    t.cond("If_m_reject", nz(mr), lambda u: reject(u, "Result_m_reject", Ex(str(mr)), X(msg_of(Ex(str(mr))))))

    def create(u: Block):
        u.cond("If_create_item", Ex("and(equals(" + str(T) + ", 'ITEM_CREATE'), equals(outputs('Compose_MItemRow'), null))"),
               lambda w: w.attempt("Create_item", lambda s, n: s.sp_create(n, L_ITEMS, {
                   "Title": X(o("Compose_MItem")), "ItemID": X(o("Compose_MItem")),
                   "ItemName": X(Ex(f"trim(string({P('ItemName')}))")), "Description": X(Ex(f"string(coalesce({P('Description')}, ''))")),
                   "Manufacturer": X(Ex(f"string(coalesce({P('Manufacturer')}, ''))")), "Active": True,
                   "CreatedViaRequestID": X(RID), "ApprovedByUPN": X(o("Compose_AuthBy"))})))
        u.cond("If_create_stock", Ex("equals(outputs('Compose_MStockRow'), null)"),
               lambda w: w.attempt("Create_stock", lambda s, n: s.sp_create(n, L_STOCK, {
                   "Title": cat(o("Compose_MItem"), " @ ", Ex("outputs('Compose_MLoc')?['LocationCode']")),
                   "StockKey": X(o("Compose_MStockKey")), "ItemID": X(o("Compose_MItem")),
                   "LocationCode": X(Ex("outputs('Compose_MLoc')?['LocationCode']")),
                   "ItemName": X(Ex(f"if(equals({T}, 'ITEM_CREATE'), trim(string({P('ItemName')})), coalesce(outputs('Compose_MItemRow')?['ItemName'], ''))")),
                   "Area": X(Ex(f"string(coalesce({P('Area')}, ''))")), "MinQty": X(mn), "MaxQty": X(mx), "StockVersion": 0,
                   "BalanceStatus": "NoBalance", "LowStockFlag": False, "Active": True, "CreatedViaRequestID": X(RID)})), always=True)
        # verify by re-reading (covers lost responses): success only if the rows exist and are ours
        u.sp_get("Verify_m_item", L_ITEMS, ["ItemID eq '", qv(o("Compose_MItem")), "'"], select="Id,CreatedViaRequestID", top=2, always=True)
        u.sp_get("Verify_m_stock", L_STOCK, ["StockKey eq '", qv(o("Compose_MStockKey")), "'"], select="Id,CreatedViaRequestID", top=2, always=True)
        u.compose("Compose_MVerified", X(
            "and(not(empty(body('Verify_m_stock')?['d']?['results'])), equals(first(body('Verify_m_stock')?['d']?['results'])?['CreatedViaRequestID'], "
            + str(RID) + "), or(equals(" + str(T) + ", 'LOCATION_ADD'), and(not(empty(body('Verify_m_item')?['d']?['results'])), "
            "equals(first(body('Verify_m_item')?['d']?['results'])?['CreatedViaRequestID'], " + str(RID) + "))))"), always=True)
        u.cond("If_m_verified", eq(o("Compose_MVerified"), True),
               lambda w: result(w, "Result_m_ok", "Succeeded", "OK",
                                X(cat("Created ", o("Compose_MStockKey"), ". It has NO quantity yet: a supervisor must count it (Audit) before it can be issued.")),
                                effect="NotApplied", auth_by=X(o("Compose_AuthBy"))),
               lambda w: result(w, "Result_m_pending", "Processing", "CREATE_PENDING",
                                "Not confirmed yet. Do not repeat; it will be completed or retried automatically.", finalize=False),
               always=True)
    t.cond("If_m_create", and_(CONT, eq(mr, "")), create)


# ---------------------------------------------------------------------------------------------------------------------
def stage_param(t: Block):
    """PARAM_UPDATE: change MinQty / MaxQty / Area / Active on a stock record (never quantities)."""
    P = lambda k: Ex(f"outputs('Compose_PPayload')?['{k}']")
    t.compose("Compose_PPayload", X("json(coalesce(" + str(req("PayloadJson")) + ", '{}'))"))
    t.set_many("Param_init", {"vApplyTries": 0, "vApplied": "no"})

    def loop(l: Block):
        l.inc_var("vApplyTries", 1, name="Param_inc_tries")
        l.sp_get("Get_p_stock", L_STOCK, ["StockKey eq '", qv(coalesce(req("StockKey"), "NONE")), "'"], select=STOCK_SELECT, top=2)
        l.compose("Compose_PStock", X("first(body('Get_p_stock')?['d']?['results'])"))
        cur = lambda k: _pick("Compose_PStock", k)
        new_min, new_max = Ex(f"coalesce({P('MinQty')}, {cur('MinQty')})"), Ex(f"coalesce({P('MaxQty')}, {cur('MaxQty')})")
        new_act = Ex(f"coalesce({P('Active')}, {cur('Active')})")
        checks(l, "Param", [
            ("stock_found", code_if(is_null(o("Compose_PStock")), "STOCK_NOT_FOUND")),
            ("min_max_valid", code_if(or_(not_(is_int(new_min)), not_(is_int(new_max)), f("less", num(new_min), 0), f("greater", num(new_min), num(new_max))), "PAYLOAD_INVALID")),
            ("no_deactivate_with_stock", code_if(and_(eq(new_act, False), not_(is_null(cur("OnHandQty"))), f("greater", num(cur("OnHandQty")), 0)), "NONZERO_STOCK")),
        ])
        pr = o("Param_Result")
        l.cond("If_p_reject", and_(CONT, nz(pr)), lambda u: reject(u, "Result_p_reject", Ex(str(pr)), X(msg_of(Ex(str(pr))))))
        low = and_(not_(is_null(cur("OnHandQty"))), if_(eq(cfg("LowStockRule"), "LT"), f("less", cur("OnHandQty"), new_min), f("lessOrEquals", cur("OnHandQty"), new_min)))

        def apply(u: Block):
            u.attempt("Apply_param", lambda s, n: s.sp_update(
                n, L_STOCK, X(cur("Id")),
                {"MinQty": X(new_min), "MaxQty": X(new_max), "Active": X(new_act), "LowStockFlag": X(low),
                 "Area": X(Ex(f"coalesce({P('Area')}, {cur('Area')})"))},
                etag=X(Ex("outputs('Compose_PStock')?['__metadata']?['etag']"))))
            u.cond("If_param_ok", ok("Apply_param"), lambda w: w.set_var("vApplied", "yes", name="Set_vApplied_param"), always=True)
        l.cond("If_p_apply", and_(CONT, eq(pr, "")), apply)
    t.until("Until_param", or_(eq(v("vApplied"), "yes"), eq(vres("outcome"), "done"), f("greaterOrEquals", v("vApplyTries"), 3)), loop, count=5)
    t.cond("If_param_done", and_(CONT, eq(v("vApplied"), "yes")),
           lambda u: result(u, "Result_param_ok", "Succeeded", "OK", "Settings for this item/location were updated.", effect="NotApplied", auth_by=X(o("Compose_AuthBy"))))
    t.cond("If_param_pending", and_(CONT, eq(v("vApplied"), "no")),
           lambda u: result(u, "Result_param_pending", "Pending", "CONTENTION", "Busy - retrying automatically."))


# ---------------------------------------------------------------------------------------------------------------------
def stage_approve(t: Block):
    """APPROVE: authority already verified (Author is an active Supervisor/Admin). Record it and re-queue the target."""
    t.sp_get("Get_target", L_REQUESTS, ["RequestID eq '", qv(coalesce(req("TargetRequestID"), "NONE")), "'"], select=REQ_SELECT, expand="Author", top=2)
    t.compose("Compose_Target", X("first(body('Get_target')?['d']?['results'])"))
    t.cond("If_target_missing", is_null(o("Compose_Target")), lambda u: reject(u, "Result_target_missing", "TARGET_NOT_FOUND"))
    t.cond("If_target_not_waiting", and_(CONT, Ex("not(equals(outputs('Compose_Target')?['RequestStatus'], 'AwaitingSupervisor'))")),
           lambda u: result(u, "Result_target_not_waiting", "Succeeded", "OK_NOTHING_TO_DO",
                            "That request is not waiting for approval (already finished or being processed). Nothing was changed.", effect="NotApplied"))

    def requeue(u: Block):
        u.attempt("Requeue_target", lambda s, n: s.sp_update(
            n, L_REQUESTS, X(Ex("outputs('Compose_Target')?['Id']")), {"RequestStatus": "Pending", "IsOpen": True},
            etag=X(Ex("outputs('Compose_Target')?['__metadata']?['etag']"))))
        u.cond("If_requeued", ok("Requeue_target"),
               lambda w: result(w, "Result_approve_ok", "Succeeded", "OK",
                                "Your decision was recorded and the request was released for processing.", effect="NotApplied", auth_by=X(o("Compose_AuthBy"))),
               lambda w: result(w, "Result_approve_pending", "Processing", "REQUEUE_PENDING",
                                "Decision recorded; releasing the request. It will complete automatically.", finalize=False),
               always=True)
    t.cond("If_requeue_target", CONT, requeue)


# ---------------------------------------------------------------------------------------------------------------------
def stage_finalize(c: Block):
    TERM = in_(vres("status"), TERMINAL)

    def fin(t: Block):
        t.attempt("Finalize_request", lambda s, n: s.sp_update(
            n, L_REQUESTS, X(req("Id")),
            {"RequestStatus": X(vres("status")), "ResultCode": X(vres("code")), "ResultMessage": X(vres("message")),
             "LedgerKey": X(vres("ledger")), "InventoryEffect": X(if_(f("empty", vres("effect")), None, vres("effect"))),
             "AuthorizedByUPN": X(vres("authBy")), "ProcessedUtc": X(if_(TERM, Ex(f"utcNow('{ISO}')"), None)),
             "ClaimedUtc": None, "IsOpen": X(not_(TERM))}))
        # keep the badge session alive on the server side too (best effort)
        t.cond("If_touch_session", and_(nz(v("vSessionItem")), in_(vres("status"), ["Succeeded", "Rejected"])),
               lambda u: u.attempt("Touch_session", lambda s, n: s.sp_update(
                   n, L_SESSIONS, X(v("vSessionItem")), {"LastActivityUtc": X(coalesce(req("Created"), Ex(f"utcNow('{ISO}')")))})),
               always=True)
    c.cond("Stage_finalize", Ex("and(equals(variables('vRes')?['finalize'], 'yes'), not(equals(outputs('Compose_Req'), null)))"), fin, always=True)
