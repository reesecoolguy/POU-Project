"""Reusable Power Fx fragments, generated once and pasted into each control that needs them.

Naming: varX = global (Set), locX = screen context variable (UpdateContext), colX = collection.
Every fragment is plain text; the linter checks the assembled result.
"""
from __future__ import annotations

SESSION_FLOW = "'POU-Session'"
PROCESS_FLOW = "'POU-ProcessRequest'"

# Settings the app reads (key, global variable, default, kind). Defaults mirror schema/settings_defaults.json.
APP_SETTINGS = [
    ("IdleTimeoutMinutes", "varIdleMin", 3, "num"),
    ("MaxAddQty", "varMaxAdd", 500, "num"),
    ("AuditConfirmVariance", "varAuditVar", 5, "num"),
    ("ScanCommitIdleMs", "varScanIdle", 350, "num"),
    ("ScanMinLength", "varScanMin", 3, "num"),
    ("StatusPollSeconds", "varPollSec", 2, "num"),
    ("StatusPollTimeoutSeconds", "varPollMax", 45, "num"),
    ("LogoutAfterSubmit", "varLogoutAfter", "false", "bool"),
    ("RequireSupervisorForAudit", "varSupAudit", "true", "bool"),
    ("RequireSupervisorForNewItem", "varSupNewItem", "true", "bool"),
    ("LowStockRule", "varLowRule", "LE", "text"),
    ("DisplayTimeZoneIana", "varTzName", "America/Chicago", "text"),
]


def setting_set(key: str, var: str, default, kind: str) -> str:
    look = f'LookUp(colSettings, SettingKey = "{key}").SettingValue'
    if kind == "num":
        return f"Set({var}, If(IsNumeric({look}), Value({look}), {default}))"
    if kind == "bool":
        return f'Set({var}, Lower(Coalesce({look}, "{default}")) = "true")'
    return f'Set({var}, Coalesce({look}, "{default}"))'


def settings_block() -> str:
    return ";\n".join(setting_set(*s) for s in APP_SETTINGS)


ACT = "Set(varLastActivity, Now())"


def normalise(text_expr: str) -> str:
    """Same rule as pou_tools.keys.normalize_id and the flows: UPPER(TRIM(x)) with scanner '*' removed."""
    return f'Upper(Trim(Substitute({text_expr}, "*", "")))'


QTY_PATTERN = '"^[1-9][0-9]{0,3}$"'          # 1..9999, no leading zero, no sign, no decimals, no spaces
COUNT_PATTERN = '"^(0|[1-9][0-9]{0,5})$"'    # 0..999999


def qty_ok(text_expr: str, maxq: str | None = None) -> str:
    base = f"IsMatch({text_expr}, {QTY_PATTERN})"
    return f"If({base}, Value({text_expr}) <= {maxq}, false)" if maxq else base


def qty_hint(text_expr: str, label: str = "Quantity", maxq: str | None = None) -> str:
    bad = f'"{label} must be a whole number from 1 to 9999. Was a barcode scanned into this box?"'
    if maxq:
        over = f'"That is over the limit of " & {maxq} & " for one ADD. Was a part number scanned here?"'
        return f'If(IsBlank({text_expr}), "", {qty_ok(text_expr)}, If(Value({text_expr}) > {maxq}, {over}, ""), {bad})'
    return f'If(IsBlank({text_expr}), "", {qty_ok(text_expr)}, "", {bad})'


# ---------------------------------------------------------------------------------------------------------------------
# The posting procedure. ONE implementation, used by every screen that creates a request.
# ---------------------------------------------------------------------------------------------------------------------

def req_record(rtype: str, stockkey: str, item: str, loc: str, qty: str, expver: str, reason: str, payload: str, target: str,
               decision: str, reverses: str, summary: str) -> str:
    """The retained request: every field is TEXT so the record is identical for every request type."""
    return ("{RequestID: Lower(GUID()), SessionID: varSession, Station: varStation, RequestType: " + rtype + ", StockKey: " + stockkey + ", ItemID: " + item + ", LocationCode: " + loc +
            ", Quantity: " + qty + ", ExpectedVersion: " + expver + ", Reason: " + reason + ", PayloadJson: " + payload +
            ", TargetRequestID: " + target + ", Decision: " + decision + ", ReversesLedgerKey: " + reverses + ", Summary: " + summary + "}")


def begin_request(record: str) -> str:
    """Create the retained request ONCE (GUID generated here) and persist it locally before anything is sent."""
    return (f"Set(varReq, {record});\n"
            "Collect(colOutbox, varReq);\n"
            'IfError(SaveData(colOutbox, "POUOutbox"), true)')


def outcome_block(after_final: str) -> str:
    """Read the SYSTEM OF RECORD (the request row) and decide what to show. Success is shown only for RequestStatus = Succeeded."""
    return f"""Set(varRow, IfError(LookUp(POURequests, RequestID = varReq.RequestID), Blank()));
Set(varFinal, If(IsBlank(varRow), Coalesce(varResp.status, ""), varRow.RequestStatus.Value));
Set(varText, If(IsBlank(varRow), Coalesce(varResp.message, ""), Coalesce(varRow.ResultMessage, varResp.message, "")));
Set(varEffect, If(IsBlank(varRow), Coalesce(varResp.effect, ""), Coalesce(varRow.InventoryEffect.Value, "")));
Set(varShort, Left(varReq.RequestID, 8));
If(
    varFinal = "Succeeded",
        Set(varPolling, false); Set(varOutKind, "ok"); Set(varOutText, varText);
        {after_final},
    varFinal = "Rejected",
        Set(varPolling, false); Set(varOutKind, "bad"); Set(varOutText, varText);
        {after_final},
    varFinal = "AwaitingSupervisor",
        Set(varPolling, false); Set(varOutKind, "wait");
        Set(varOutText, "Waiting for a supervisor to approve (request " & varShort & "). Nothing has been changed yet. It appears under History.");
        {after_final},
    varFinal = "Failed",
        Set(varPolling, false); Set(varOutKind, "bad");
        Set(varOutText, varText & If(varEffect = "NotApplied", "", " The quantity MAY have changed. Do not repeat this. Tell a supervisor (request " & varShort & ")."));
        {after_final},
    Set(varOutKind, "unconfirmed");
    Set(varOutText, "NOT CONFIRMED (request " & varShort & "). Do not enter it again. Press 'Retry same request' or wait: it cannot post twice and it finishes automatically.");
    Set(varPolling, true)
)"""


def finish_common(extra: str = "") -> str:
    """Runs once the request reached a terminal answer: drop it from the local outbox and release the screen."""
    parts = ['RemoveIf(colOutbox, RequestID = varReq.RequestID)',
             'IfError(SaveData(colOutbox, "POUOutbox"), true)',
             'Set(varReq, Blank())']
    if extra:
        parts.append(extra)
    return ";\n".join(parts)


def run_post(after_final: str) -> str:
    """Create-if-missing, ask the flow to process, then read back the truth. Safe to run any number of times for the same varReq."""
    create_fields = """{
        Title: varReq.Summary,
        RequestID: varReq.RequestID,
        RequestType: {Value: varReq.RequestType},
        RequestStatus: {Value: "Pending"},
        IsOpen: true,
        SessionID: varReq.SessionID,
        StationID: varReq.Station,
        StockKey: varReq.StockKey,
        ItemID: varReq.ItemID,
        LocationCode: varReq.LocationCode,
        Quantity: If(IsBlank(varReq.Quantity), Blank(), Value(varReq.Quantity)),
        ExpectedVersion: If(IsBlank(varReq.ExpectedVersion), Blank(), Value(varReq.ExpectedVersion)),
        PayloadJson: varReq.PayloadJson,
        Reason: varReq.Reason,
        ReversesLedgerKey: varReq.ReversesLedgerKey,
        TargetRequestID: varReq.TargetRequestID,
        Decision: If(IsBlank(varReq.Decision), Blank(), {Value: varReq.Decision}),
        ClientLocalTime: Text(Now(), "yyyy-mm-dd hh:mm:ss")
    }"""
    return f"""If(
    IsBlank(varReq) Or varBusy,
    false,
    Set(varBusy, true);
Set(varOutKind, "");
Set(varOutText, "");
Set(varLookupFailed, false);
Set(varFound, IfError(LookUp(POURequests, RequestID = varReq.RequestID), Set(varLookupFailed, true); Blank()));
Set(varSent, Not(IsBlank(varFound)));
If(
    Not(varSent) And Not(varLookupFailed),
    Set(varCreateFailed, false);
    IfError(Patch(POURequests, Defaults(POURequests), {create_fields}), Set(varCreateFailed, true));
    Set(varSent, Not(varCreateFailed));
    If(
        varCreateFailed,
        Set(varFound, IfError(LookUp(POURequests, RequestID = varReq.RequestID), Blank()));
        Set(varSent, Not(IsBlank(varFound)))
    )
);
If(
    varSent,
    Set(varResp, IfError({PROCESS_FLOW}.Run(varReq.RequestID),
        {{status: "", code: "NO_RESPONSE", message: "", ledgerKey: "", effect: "", newOnHand: "", requestId: varReq.RequestID}}));
    {outcome_block(after_final)},
    Set(varOutKind, "unconfirmed");
    Set(varOutText, "NOT CONFIRMED (request " & Left(varReq.RequestID, 8) & "). The app could not confirm that the server received it. Do not enter it again: press 'Retry same request' - the same request number is reused, so it cannot post twice.");
    Set(varPolling, false)
);
Set(varBusy, false)
)"""


def poll_tick(after_final: str) -> str:
    """Timer body: only READS the request row; never re-sends. Stops by itself after StatusPollTimeoutSeconds."""
    return f"""If(
    IsBlank(varReq) Or Not(varPolling),
    Set(varPolling, false),
    Set(varPollTries, varPollTries + 1);
    Set(varResp, {{status: "", code: "POLL", message: "", ledgerKey: "", effect: "", newOnHand: "", requestId: varReq.RequestID}});
    {outcome_block(after_final)};
    If(
        varPolling And varPollTries * varPollSec >= varPollMax,
        Set(varPolling, false);
        Set(varOutText, "STILL NOT CONFIRMED (request " & Left(varReq.RequestID, 8) & "). The background job completes pending requests every few minutes. Do not enter it again; check History, or press 'Retry same request'.")
    )
)"""


def logout_block() -> str:
    return f"""If(
    Not(IsBlank(varSession)),
    IfError({SESSION_FLOW}.Run("LOGOUT", "", varStation, varSession, Lower(User().Email)), true)
);
Set(varSession, "");
Set(varEmpName, "");
Set(varRole, "");
Set(varSupMode, false);
Clear(colStock);
Navigate(scrLogin, ScreenTransition.None)"""
