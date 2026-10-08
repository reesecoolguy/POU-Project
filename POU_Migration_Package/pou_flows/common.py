"""Shared building blocks: site-url guard, settings loader, message catalogue, ops-event upsert."""
from __future__ import annotations

from .dsl import (ALL, Block, Ex, Flow, X, and_, b, cat, coalesce, eq, f, if_, is_null, lit, nz, o, not_, or_, qv, v)

DEFAULT_SITE_URL = "https://CHANGE-ME.sharepoint.com/sites/POU"

L_SETTINGS, L_STATIONS, L_LOCATIONS, L_EMPLOYEES, L_SESSIONS = "POUSettings", "POUStations", "POULocations", "POUEmployees", "POUSessions"
L_ITEMS, L_STOCK, L_REQUESTS, L_LEDGER, L_OPS = "POUItems", "POUStockLocations", "POURequests", "POULedger", "POUOpsEvents"

REQ_SELECT = ("Id,Created,RequestID,RequestType,RequestStatus,IsOpen,SessionID,StationID,StockKey,ItemID,LocationCode,Quantity,"
              "ExpectedVersion,PayloadJson,Reason,ReversesLedgerKey,TargetRequestID,Decision,ResultCode,ResultMessage,LedgerKey,"
              "InventoryEffect,ClaimedUtc,AttemptCount,ProcessingRunId,Author/EMail")
STOCK_SELECT = ("Id,StockKey,ItemID,LocationCode,ItemName,Area,MinQty,MaxQty,OnHandQty,StockVersion,BalanceStatus,LowStockFlag,Active,"
                "LastLedgerKey,LastCountedUtc,CreatedViaRequestID")
LEDGER_SELECT = ("Id,LedgerKey,RequestID,LedgerType,PostingState,StockKey,ItemID,LocationCode,SeqNo,QtyDelta,QtyBefore,QtyAfter,"
                 "AffectsBalance,ReversesLedgerKey,OccurredUtc,BadgeID,EmployeeName,Origin")

TERMINAL = ["Succeeded", "Rejected", "Failed"]

MESSAGES = {
    "UNKNOWN_TYPE": "Unknown request type.",
    "NO_SESSION": "You are not signed in. Scan your badge again.",
    "SESSION_ENDED": "Your session has ended. Scan your badge again.",
    "SESSION_EXPIRED": "Your session timed out. Scan your badge again.",
    "SESSION_ACCOUNT_MISMATCH": "This badge session belongs to a different Microsoft sign-in. Scan your badge again.",
    "EMPLOYEE_INACTIVE": "This badge is not active. See a supervisor.",
    "STATION_INVALID": "This station is not set up or is inactive. See a supervisor.",
    "STATION_MISMATCH": "This request came from a different station than the session. Scan your badge again.",
    "STATION_ACCOUNT_MISMATCH": "This station only accepts requests from its assigned Microsoft account.",
    "NOT_AUTHORIZED": "This action needs a supervisor who is signed in to Microsoft with their own account.",
    "SUPERVISOR_REJECTED": "A supervisor rejected this request. Nothing was changed.",
    "STOCK_NOT_FOUND": "That item/location does not exist. Nothing was changed.",
    "STOCK_INACTIVE": "That item/location is inactive. Nothing was changed.",
    "INVALID_QUANTITY": "Quantity must be a whole number of 1 or more. Nothing was changed.",
    "INVALID_COUNT": "Counted quantity must be a whole number of 0 or more. Nothing was changed.",
    "NO_BALANCE": "This item/location has no verified quantity yet. A supervisor must count it first (Audit). Nothing was changed.",
    "BALANCE_UNVERIFIED": "This quantity has not been verified by a count yet. Nothing was changed.",
    "MISSING_EXPECTED_VERSION": "The count did not record the stock version it started from. Recount. Nothing was changed.",
    "OPENING_NOT_ALLOWED": "An opening balance can only be set once, on a record with no balance. Nothing was changed.",
    "REASON_REQUIRED": "A reason is required. Nothing was changed.",
    "REVERSAL_TARGET_MISSING": "The movement to reverse was not found. Nothing was changed.",
    "REVERSAL_NOT_POSTED": "Only posted ISSUE or RECEIPT movements can be reversed. Nothing was changed.",
    "REVERSAL_WRONG_STOCK": "That movement belongs to a different item/location. Nothing was changed.",
    "REVERSAL_ALREADY": "That movement has already been reversed. Nothing was changed.",
    "REVERSAL_NEGATIVE": "Reversing would make the quantity negative. Use an ADJUSTMENT instead. Nothing was changed.",
    "DRIFT_DETECTED": "The stored quantity does not match its history. A supervisor has been alerted. Nothing was changed.",
    "STOCK_CHANGED_OUTSIDE_PROTOCOL": "The stored quantity was changed outside the normal process while this was being posted. A supervisor has been alerted. Nothing was changed by this request.",
    "PAYLOAD_INVALID": "The details supplied are incomplete or invalid. Nothing was changed.",
    "ITEM_EXISTS": "That Item ID already exists. Use 'Add stocking location' to stock it somewhere else. Nothing was changed.",
    "ITEM_NOT_FOUND": "That Item ID does not exist. Nothing was changed.",
    "STOCK_EXISTS": "That item is already stocked at that location. Nothing was changed.",
    "LOCATION_UNKNOWN": "That location is not in the location list (an admin adds locations). Nothing was changed.",
    "TARGET_NOT_FOUND": "The request being approved was not found.",
    "TARGET_NOT_WAITING": "That request is not waiting for approval.",
    "NONZERO_STOCK": "An item/location with stock cannot be deactivated. Count it to zero first. Nothing was changed.",
    "GAVE_UP": "This could not be processed after several automatic attempts. Nothing was changed. Please repeat it.",
    "EXPIRED": "No supervisor approved this in time. Nothing was changed. Please repeat it.",
}

SCHEMA_RESPONSE = {
    "type": "object",
    "properties": {k: {"type": "string"} for k in ("status", "code", "message", "ledgerKey", "effect", "newOnHand", "requestId")},
}


def preamble(flow: Flow, site_url: str = DEFAULT_SITE_URL):
    """Cfg_SiteUrl + hard stop if still the placeholder."""
    blk = flow.root
    blk.compose("Cfg_SiteUrl", site_url)
    blk.cond("Guard_site_url_configured", f("contains", o("Cfg_SiteUrl"), "CHANGE-ME"),
             lambda t: t.terminate("Stop_site_url_not_set", "Failed", "Edit the Cfg_SiteUrl action: it still contains CHANGE-ME."))
    return blk


def load_settings(blk: Block, prefix=""):
    blk.sp_get(f"{prefix}Get_settings", L_SETTINGS, select="Id,SettingKey,SettingValue", top=500, filter_parts=None)
    blk.select(f"{prefix}Select_settings", X(Ex(f"body('{prefix}Get_settings')?['d']?['results']")),
               "@concat('\"', item()?['SettingKey'], '\":\"', replace(replace(coalesce(item()?['SettingValue'], ''), '\"', ''), '\\', '/'), '\"')")
    blk.compose(f"{prefix}Compose_Settings", X(f"json(concat('{{', join(body('{prefix}Select_settings'), ','), '}}'))"))


def cfg(key, prefix="") -> Ex:
    return Ex(f"outputs('{prefix}Compose_Settings')?['{key}']")


def cfgi(key, default, prefix="") -> Ex:
    return Ex(f"int(coalesce({cfg(key, prefix)}, '{default}'))")


def cfgb(key, default, prefix="") -> Ex:
    return Ex(f"equals(toLower(coalesce({cfg(key, prefix)}, '{default}')), 'true')")


def ops_event(blk: Block, pfx: str, key, etype: str, severity: str, subject, details):
    """Upsert a POUOpsEvents row (de-duplicated by EventKey). Never fails the caller: wrapped in a scope run with always=True next."""
    def build(s: Block):
        s.sp_get(f"{pfx}_Get_event", L_OPS, [("EventKey eq '"), qv(key), "'"], select="Id,OccurrenceCount", top=2)
        s.compose(f"{pfx}_Event_row", X(f"first(body('{pfx}_Get_event')?['d']?['results'])"))
        s.cond(f"{pfx}_Event_exists", Ex(f"not(equals(outputs('{pfx}_Event_row'), null))"),
               lambda t: t.sp_update(f"{pfx}_Update_event", L_OPS, X(Ex(f"outputs('{pfx}_Event_row')?['Id']")),
                                     {"LastSeenUtc": X("utcNow('yyyy-MM-ddTHH:mm:ssZ')"),
                                      "OccurrenceCount": X(f"add(int(coalesce(outputs('{pfx}_Event_row')?['OccurrenceCount'], 1)), 1)"),
                                      "Details": details, "Resolved": False}),
               lambda e: e.sp_create(f"{pfx}_Create_event", L_OPS,
                                     {"Title": subject, "EventKey": key, "EventType": etype, "Severity": severity, "Subject": subject,
                                      "Details": details, "FirstSeenUtc": X("utcNow('yyyy-MM-ddTHH:mm:ssZ')"),
                                      "LastSeenUtc": X("utcNow('yyyy-MM-ddTHH:mm:ssZ')"), "OccurrenceCount": 1, "Resolved": False}))
    return blk.scope(f"{pfx}_Ops_event", build)
