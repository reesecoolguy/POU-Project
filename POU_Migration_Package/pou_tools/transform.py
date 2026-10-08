"""Step 2: validate + transform the extracted workbook into import-ready files, an exception report and reconciliation.

RULES THIS MODULE ENFORCES (each has a test in tests/test_transform.py):
  * ItemID / BadgeID are TEXT. Numeric cells are rendered as digits; leading zeros are never invented, and the
    loss of any that may have existed is reported.
  * The same ItemID at different locations is NORMAL: one POUItems row, several POUStockLocations rows.
    Nothing is deleted, merged, renumbered or rejected because an ItemID repeats.
  * Blank quantities stay blank (NoBalance). Quantities above Max are NOT capped. Nothing is zero-filled.
  * OnHandQty is never written to the stock-location import file. Balances travel as OPENING requests that the
    flow posts, so the ledger always explains the balance.
  * Legacy transactions/audits keep their timestamps (converted to UTC from an ASSUMED America/Chicago local time),
    original user NAME text, and are marked Origin=Legacy, AffectsBalance=No. Missing before/after quantities,
    locations and employee identities stay blank.
  * Ambiguity goes to the exception report, never silently resolved.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .keys import KEY_SEP, KeyError_, clean_display, ledger_key, normalize_id, stock_key, to_text

SEV_ORDER = {"BLOCKER": 0, "WARN": 1, "INFO": 2}
STANDARD_LOCATION = re.compile(r"^\d+-[A-Za-z]$")


@dataclass
class Exc:
    severity: str
    category: str
    sheet: str
    row: object
    item_id: str
    location: str
    field: str
    value: str
    message: str
    action: str
    disposition: str
    id: str = ""

    def as_row(self):
        return [self.id, self.severity, self.category, self.sheet, self.row, self.item_id, self.location, self.field,
                self.value, self.message, self.action, self.disposition]


EXC_COLUMNS = ["ExceptionID", "Severity", "Category", "SourceSheet", "SourceRow", "ItemID", "Location", "Field",
               "Value", "Message", "RecommendedAction", "Disposition"]


@dataclass
class Config:
    source_timezone: str = "America/Chicago"
    assume_all_employees_active: bool = True
    default_employee_role: str = "Operator"
    migration_station_id: str = "MIGRATION"


@dataclass
class Result:
    items: list[dict] = field(default_factory=list)
    locations: list[dict] = field(default_factory=list)
    stock: list[dict] = field(default_factory=list)
    employees: list[dict] = field(default_factory=list)
    legacy_ledger: list[dict] = field(default_factory=list)
    opening_requests: list[dict] = field(default_factory=list)
    held_inventory: list[dict] = field(default_factory=list)
    held_legacy: list[dict] = field(default_factory=list)
    exceptions: list[Exc] = field(default_factory=list)
    row_counts: list[dict] = field(default_factory=list)
    qty_recon: list[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)


# column orders = schema internal names (importer validates against schema)
ITEM_COLS = ["Title", "ItemID", "ItemName", "Description", "Manufacturer", "Priority", "LeadTimeDays", "UnitCost",
             "Notes", "Active", "LegacySourceRows"]
STOCK_COLS = ["Title", "StockKey", "ItemID", "LocationCode", "ItemName", "Area", "MinQty", "MaxQty", "BalanceStatus",
              "LowStockFlag", "Active", "LegacySourceRow"]
LOCATION_COLS = ["Title", "LocationCode", "Description", "Active"]
EMPLOYEE_COLS = ["Title", "BadgeID", "EmployeeName", "Active", "Role", "MicrosoftUPN", "Notes"]
LEDGER_COLS = ["Title", "LedgerKey", "RequestID", "LedgerType", "Origin", "AffectsBalance", "PostingState", "StockKey",
               "ItemID", "LocationCode", "SeqNo", "QtyDelta", "QtyBefore", "QtyAfter", "EmployeeName", "StationID",
               "OccurredUtc", "OccurredLocalText", "Reason", "LegacyUser", "LegacyTimestampText", "LegacySource",
               "LocationResolution"]
REQUEST_COLS = ["Title", "RequestID", "RequestType", "StationID", "StockKey", "ItemID", "LocationCode", "Quantity", "Reason"]


def _v(cells, h):
    c = cells.get(h)
    return (None, "none") if c is None else (c["v"], c["t"])


def to_int(v, t):
    """Whole non-negative-or-not integer from a cell, else None. Text digits are accepted (reported by caller)."""
    if t == "int":
        return v
    if t == "float" and v == int(v):
        return int(v)
    if t == "str" and re.fullmatch(r"\s*-?\d+\s*", v):
        return int(v)
    return None


def to_number(v, t):
    if t in ("int", "float"):
        return v
    if t == "str":
        s = v.strip().replace("$", "").replace(",", "")
        if re.fullmatch(r"-?\d+(\.\d+)?", s):
            return float(s) if "." in s else int(s)
    return None


def _utc(local_naive: datetime, tz: ZoneInfo):
    """Return (utc_dt, flag) where flag in {None,'AMBIGUOUS','NONEXISTENT'}."""
    a = local_naive.replace(tzinfo=tz, fold=0)
    b = local_naive.replace(tzinfo=tz, fold=1)
    flag = None
    if a.utcoffset() != b.utcoffset():
        flag = "AMBIGUOUS"
    ua = a.astimezone(timezone.utc)
    if ua.astimezone(tz).replace(tzinfo=None) != local_naive:
        flag = "NONEXISTENT"
    return ua, flag


def transform(ex: dict, cfg: Config | None = None) -> Result:
    cfg = cfg or Config()
    tz = ZoneInfo(cfg.source_timezone)
    R = Result()
    E = R.exceptions
    src_sha = ex["meta"]["source_sha256"]

    def exc(sev, cat, sheet, row, item, loc, fld, val, msg, act, disp):
        E.append(Exc(sev, cat, sheet, row, item, loc, fld, "" if val is None else str(val), msg, act, disp))

    # ---------------------------------------------------------------- inventory rows
    inv_rows = ex["inventory"]["rows"]
    parsed = []
    for r in inv_rows:
        c, n = r["cells"], r["_row"]
        idv, idt = _v(c, "Item ID")
        locv, loct = _v(c, "Location")
        item_raw = to_text(idv)
        item_id = normalize_id(idv)
        loc_clean = clean_display(locv)
        p = {"row": n, "item_id": item_id, "item_raw": item_raw, "loc": loc_clean, "hold": False, "cells": c}
        parsed.append(p)

        if not item_id:
            exc("BLOCKER", "BLANK_ITEM_ID", "Inventory", n, "", loc_clean, "Item ID", "", "Row has no Item ID.",
                "Supply an Item ID in the workbook and re-extract.", "HELD")
            p["hold"] = True
        if not loc_clean:
            exc("BLOCKER", "BLANK_LOCATION", "Inventory", n, item_id, "", "Location", "", "Row has no Location.",
                "Supply a location and re-extract.", "HELD")
            p["hold"] = True
        if p["hold"]:
            continue
        if KEY_SEP in item_id or KEY_SEP in loc_clean:
            exc("BLOCKER", "RESERVED_CHARACTER", "Inventory", n, item_id, loc_clean, "Item ID/Location",
                f"{item_id} / {loc_clean}", f"'{KEY_SEP}' is reserved as the StockKey separator.",
                "Rename the item or location without that character.", "HELD")
            p["hold"] = True
            continue
        if item_raw != item_id:
            exc("INFO", "ID_NORMALIZED", "Inventory", n, item_id, loc_clean, "Item ID", item_raw,
                "Item ID was trimmed / upper-cased / had scanner asterisks removed.", "None unless you want the tag reprinted.", "MIGRATED")
        if idt in ("int", "float"):
            exc("INFO", "NUMERIC_ITEM_ID", "Inventory", n, item_id, loc_clean, "Item ID", item_raw,
                "Item ID was stored as a NUMBER in the workbook. Migrated as text exactly as the digits appear; "
                "any leading zeros that may have existed were already lost in Excel.",
                "Confirm against the printed tag.", "MIGRATED")
        p["skey"] = stock_key(item_id, loc_clean)

    # duplicate (item, location) -> ambiguous, hold ALL involved rows
    groups = defaultdict(list)
    for p in parsed:
        if not p["hold"]:
            groups[p["skey"]].append(p)
    for sk, ps in groups.items():
        if len(ps) > 1:
            for p in ps:
                exc("BLOCKER", "DUPLICATE_ITEM_LOCATION", "Inventory", p["row"], p["item_id"], p["loc"], "Item ID+Location",
                    sk, f"Item/location {sk} appears {len(ps)} times (rows {[q['row'] for q in ps]}). Cannot tell which is correct.",
                    "Decide which row is right, or merge quantities in the workbook, then re-extract.", "HELD")
                p["hold"] = True

    # canonical location spelling = first seen
    canon_loc: "OrderedDict[str, str]" = OrderedDict()
    for p in parsed:
        if p["hold"]:
            continue
        k = normalize_id(p["loc"])
        if k not in canon_loc:
            canon_loc[k] = p["loc"]
        elif canon_loc[k] != p["loc"]:
            exc("INFO", "LOCATION_CASE_VARIANT", "Inventory", p["row"], p["item_id"], p["loc"], "Location", p["loc"],
                f"Location spelled differently from first use '{canon_loc[k]}'; migrated using the first spelling.", "None.", "MIGRATED")
        p["loc_canon"] = canon_loc[k]
        p["skey"] = stock_key(p["item_id"], p["loc_canon"])

    # per-row quantities
    for p in parsed:
        if p["hold"]:
            continue
        c, n, item_id, loc = p["cells"], p["row"], p["item_id"], p["loc_canon"]
        mv, mt = _v(c, "Min Qty")
        xv, xt = _v(c, "Max Qty")
        ov, ot = _v(c, "On Hand Qty")
        mn, mx = to_int(mv, mt), to_int(xv, xt)
        for lab, val, t_, parsed_ in (("Min Qty", mv, mt, mn), ("Max Qty", xv, xt, mx)):
            if parsed_ is None or parsed_ < 0:
                exc("BLOCKER", "INVALID_MIN_MAX", "Inventory", n, item_id, loc, lab, to_text(val),
                    f"{lab} is blank, not a whole number, or negative.", "Correct in the workbook and re-extract.", "HELD")
                p["hold"] = True
            elif t_ == "str":
                exc("INFO", "TEXT_NUMBER", "Inventory", n, item_id, loc, lab, to_text(val), f"{lab} stored as text; converted to a number.", "None.", "MIGRATED")
        if p["hold"]:
            continue
        p["min"], p["max"] = mn, mx
        if mn > mx:
            exc("WARN", "MIN_GT_MAX", "Inventory", n, item_id, loc, "Min/Max", f"{mn}/{mx}", "Min Qty exceeds Max Qty.", "Fix the parameters after cutover.", "MIGRATED_WITH_FLAG")
        if mx == 0:
            exc("WARN", "MAX_ZERO", "Inventory", n, item_id, loc, "Max Qty", 0, "Max Qty is 0, so suggested order quantity will always be 0.", "Set a real Max.", "MIGRATED_WITH_FLAG")
        if mn == 0:
            p["min_zero"] = True
        oh = to_int(ov, ot)
        if ot == "none":
            exc("WARN", "BLANK_ONHAND", "Inventory", n, item_id, loc, "On Hand Qty", "", "On Hand is BLANK. Not treated as zero. Stock record is created as NoBalance with no opening request; ISSUE/RECEIPT are refused until it is counted.",
                "Physically count it; a supervisor posts the count as an AUDIT (opening) after cutover.", "MIGRATED_WITH_FLAG")
            p["onhand"] = None
        elif oh is None or oh < 0:
            exc("WARN", "INVALID_ONHAND", "Inventory", n, item_id, loc, "On Hand Qty", to_text(ov), "On Hand is not a whole number >= 0. Not guessed. Created as NoBalance, no opening request.",
                "Count and post as AUDIT after cutover.", "MIGRATED_WITH_FLAG")
            p["onhand"] = None
        else:
            if ot == "str":
                exc("INFO", "TEXT_NUMBER", "Inventory", n, item_id, loc, "On Hand Qty", to_text(ov), "On Hand stored as text; converted.", "None.", "MIGRATED")
            p["onhand"] = oh
            if oh > mx:
                exc("WARN", "ONHAND_ABOVE_MAX", "Inventory", n, item_id, loc, "On Hand Qty", f"{oh} (Max {mx})",
                    "On Hand exceeds Max. NOT capped; the opening balance is the workbook figure.",
                    "Confirm at the opening count; correct Max or quantity.", "MIGRATED_WITH_FLAG")

    ok_rows = [p for p in parsed if not p["hold"]]

    # ---------------------------------------------------------------- items (master) from ok rows
    by_item: "OrderedDict[str, list]" = OrderedDict()
    for p in ok_rows:
        by_item.setdefault(p["item_id"], []).append(p)

    def merged(item_id, label, rows):
        vals = []
        for p in rows:
            v, t = _v(p["cells"], label)
            s = clean_display(v)
            if s != "":
                vals.append((p["row"], s, t))
        return vals

    for item_id, rows in by_item.items():
        out = {c: "" for c in ITEM_COLS}
        out["ItemID"] = item_id
        out["Title"] = item_id
        out["Active"] = "TRUE"
        out["LegacySourceRows"] = ";".join(f"Inventory!r{p['row']}" for p in rows)
        notes_extra = []
        # name
        names = merged(item_id, "Item Name", rows)
        distinct = list(OrderedDict.fromkeys(s for _, s, _ in names))
        if not names:
            out["ItemName"] = item_id
            exc("WARN", "BLANK_ITEM_NAME", "Inventory", rows[0]["row"], item_id, "", "Item Name", "", "Item has no name; Item ID used as the name so the record can exist.", "Enter a real name.", "MIGRATED_WITH_FLAG")
        else:
            out["ItemName"] = distinct[0]
            if len(distinct) > 1:
                exc("WARN", "ITEM_NAME_CONFLICT", "Inventory", ";".join(str(r) for r, _, _ in names), item_id, "", "Item Name",
                    " || ".join(distinct), "Same Item ID has different names at different locations; the first was used on the item master.", "Choose the correct name.", "MIGRATED_WITH_FLAG")
        # free-text master fields
        for label, col in (("Description", "Description"), ("Manufacturer", "Manufacturer"), ("Notes", "Notes")):
            vs = merged(item_id, label, rows)
            dis = list(OrderedDict.fromkeys(s for _, s, _ in vs))
            if not dis:
                continue
            if len(dis) == 1:
                out[col] = dis[0]
                if len(vs) < len(rows) and len(rows) > 1:
                    exc("INFO", "MASTER_VALUE_FROM_SIBLING_ROW", "Inventory", ";".join(str(p["row"]) for p in rows), item_id, "",
                        label, dis[0], f"{label} was filled on only some rows of this multi-location item; the single recorded value is used on the item master.",
                        "Confirm it applies to all locations.", "MIGRATED_WITH_FLAG")
                if any(t in ("int", "float") for _, _, t in vs):
                    exc("INFO", "NUMERIC_TEXT_FIELD", "Inventory", vs[0][0], item_id, "", label, dis[0], f"{label} was numeric in the workbook; migrated as text digits.", "None.", "MIGRATED")
            else:
                exc("WARN", "MASTER_VALUE_CONFLICT", "Inventory", ";".join(str(r) for r, _, _ in vs), item_id, "", label, " || ".join(dis),
                    f"{label} differs between locations of the same Item ID. Left BLANK on the item master (no guess); values are listed here.",
                    "Pick the right value and enter it on POUItems.", "MIGRATED_WITH_FLAG")
        # numeric master fields
        for label, col, kind in (("Priority", "Priority", "int"), ("Lead Time", "LeadTimeDays", "int"), ("Cost per Unit", "UnitCost", "num")):
            vs = []
            for p in rows:
                v, t = _v(p["cells"], label)
                if t != "none" and clean_display(v) != "":
                    vs.append((p["row"], v, t))
            if not vs:
                continue
            nums = OrderedDict()
            bad = []
            for rw, v, t in vs:
                nv = to_int(v, t) if kind == "int" else to_number(v, t)
                if nv is None:
                    bad.append((rw, to_text(v)))
                else:
                    nums[nv] = rw
            if len(nums) == 1 and not bad:
                out[col] = str(next(iter(nums)))
            elif len(nums) > 1:
                exc("WARN", "MASTER_VALUE_CONFLICT", "Inventory", ";".join(str(r) for r in nums.values()), item_id, "", label, " || ".join(map(str, nums)),
                    f"{label} differs between locations; left blank.", "Choose the correct value.", "MIGRATED_WITH_FLAG")
            if bad:
                txt = "; ".join(f"{label} (source text, row {rw}): {v}" for rw, v in bad)
                out["Notes"] = (out["Notes"] + "\n" if out["Notes"] else "") + txt
                exc("WARN", "NON_NUMERIC_VALUE", "Inventory", bad[0][0], item_id, "", label, bad[0][1],
                    f"{label} is not a number; kept as text in Notes rather than lost or guessed.", "Enter a numeric value on POUItems.", "MIGRATED_WITH_FLAG")
        R.items.append(out)

    # ---------------------------------------------------------------- locations
    for k, spelling in canon_loc.items():
        used = [p for p in ok_rows if normalize_id(p["loc"]) == k]
        if not used:
            continue
        R.locations.append({"Title": spelling, "LocationCode": spelling, "Description": "", "Active": "TRUE"})
        if not STANDARD_LOCATION.match(spelling):
            exc("INFO", "NONSTANDARD_LOCATION", "Inventory", ";".join(str(p["row"]) for p in used), "", spelling, "Location", spelling,
                f"Location '{spelling}' does not follow the usual 'row-letter' pattern ({len(used)} stock record(s)). Migrated as-is.",
                "Confirm it is a real bin/zone.", "MIGRATED")

    # ---------------------------------------------------------------- stock
    item_name = {i["ItemID"]: i["ItemName"] for i in R.items}
    area_values = Counter()
    for p in ok_rows:
        c = p["cells"]
        areav, _ = _v(c, "Area:")
        area = clean_display(areav)
        area_values[area] += 1
        if p.get("min_zero"):
            pass
        R.stock.append({
            "Title": f"{p['item_id']} @ {p['loc_canon']}", "StockKey": p["skey"], "ItemID": p["item_id"],
            "LocationCode": p["loc_canon"], "ItemName": item_name[p["item_id"]], "Area": area,
            "MinQty": p["min"], "MaxQty": p["max"], "BalanceStatus": "NoBalance", "LowStockFlag": "FALSE",
            "Active": "TRUE", "LegacySourceRow": f"Inventory!r{p['row']}",
        })
        if p["onhand"] is not None:
            R.opening_requests.append({
                "Title": f"OPENING {p['skey']}", "RequestID": f"OPEN-{p['skey']}", "RequestType": "OPENING",
                "StationID": cfg.migration_station_id, "StockKey": p["skey"], "ItemID": p["item_id"],
                "LocationCode": p["loc_canon"], "Quantity": p["onhand"],
                "Reason": f"Cutover opening balance from workbook (sha256 {src_sha[:12]}) row {p['row']}",
            })
        R.qty_recon.append({
            "StockKey": p["skey"], "ItemID": p["item_id"], "LocationCode": p["loc_canon"], "SourceRow": p["row"],
            "SourceOnHand": "" if p["onhand"] is None else p["onhand"], "SourceMin": p["min"], "SourceMax": p["max"],
            "OpeningRequestQty": "" if p["onhand"] is None else p["onhand"],
            "ExpectedBalanceStatusAfterOpening": "Unverified" if p["onhand"] is not None else "NoBalance",
            "Status": "MATCH" if p["onhand"] is not None else "NO_BALANCE_BLANK_IN_SOURCE",
        })
    if len(area_values) == 1 and len(ok_rows) > 1:
        a, n = next(iter(area_values.items()))
        exc("INFO", "AREA_SINGLE_VALUE", "Inventory", "all", "", "", "Area:", a,
            f"Every stock record ({n}) has Area = '{a}'. Migrated as given; it may be a placeholder.", "Confirm or correct per location.", "MIGRATED")

    # multi-location items
    for item_id, rows in by_item.items():
        if len(rows) > 1:
            locs = ", ".join(f"{p['loc_canon']} (row {p['row']}, on hand {p['onhand'] if p['onhand'] is not None else 'blank'})" for p in rows)
            exc("INFO", "ITEM_AT_MULTIPLE_LOCATIONS", "Inventory", ";".join(str(p['row']) for p in rows), item_id, "", "Item ID", item_id,
                f"Same Item ID stocked at {len(rows)} locations: {locs}. Migrated as ONE item with {len(rows)} stock records (nothing merged, renumbered or deleted).",
                "Confirm each stock record is real (e.g. a blank-quantity row may be an obsolete bin).", "MIGRATED")

    # placeholder IDs
    temp = [i for i in R.items if re.match(r"^TEMP\d+$", i["ItemID"])]
    if temp:
        exc("INFO", "TEMPORARY_ITEM_IDS", "Inventory", "multiple", "", "", "Item ID", f"{len(temp)} items",
            f"{len(temp)} item IDs look like placeholders (TEMP####). Migrated unchanged. A permanent ID later requires a controlled rename (see docs/10_Maintenance.md).",
            "Decide the renumbering plan before printing final tags.", "MIGRATED")
    # same name different id
    nm = defaultdict(list)
    for i in R.items:
        nm[i["ItemName"].strip().lower()].append(i["ItemID"])
    for name, ids in nm.items():
        if len(ids) > 1:
            exc("INFO", "SAME_NAME_DIFFERENT_ID", "Inventory", "", ", ".join(ids), "", "Item Name", name,
                "Different Item IDs share the same name. Not merged.", "Check whether they are the same part.", "MIGRATED")
    # manufacturer spelling variants
    mv = defaultdict(set)
    for i in R.items:
        if i["Manufacturer"]:
            mv[i["Manufacturer"].lower()].add(i["Manufacturer"])
    for low, spell in mv.items():
        if len(spell) > 1:
            exc("INFO", "MANUFACTURER_SPELLING_VARIANTS", "Inventory", "", "", "", "Manufacturer", " | ".join(sorted(spell)),
                "Manufacturer spelled with different capitalisation. Kept exactly as in the workbook.", "Standardise on POUItems if desired.", "MIGRATED")
    # empty source columns
    for label in ("Priority", "Lead Time", "Cost per Unit"):
        if all(_v(p["cells"], label)[1] == "none" for p in ok_rows) and ok_rows:
            exc("INFO", "SOURCE_COLUMN_EMPTY", "Inventory", "all", "", "", label, "",
                f"'{label}' is empty on every row of the workbook. The SharePoint column exists but is blank.", "Populate when known.", "MIGRATED")
    for s in ex["inventory"].get("stray", []):
        exc("INFO", "STRAY_CELL", "Inventory", s["cell"], "", "", "(outside table)", s["v"],
            "Text outside the inventory table. Not migrated as data. It records a reporting requirement.",
            "Priority-1 on-hand report: implemented in the low-stock/usage emails only once Priority is populated.", "NOT_MIGRATED")

    # ---------------------------------------------------------------- employees
    badge_seen = defaultdict(list)
    erows = []
    for r in ex["users"]["rows"]:
        bv, bt = _v(r["cells"], "Badge ID")
        nv, _ = _v(r["cells"], "Employee Name")
        badge, name = to_text(bv).strip(), clean_display(nv)
        erows.append((r["_row"], badge, name, bt))
        if badge:
            badge_seen[badge.upper()].append(r["_row"])
    for rw, badge, name, bt in erows:
        if not badge or not name:
            exc("BLOCKER", "INCOMPLETE_EMPLOYEE", "Users", rw, "", "", "Badge/Name", f"{badge!r}/{name!r}", "Badge ID or name is blank.", "Complete the row.", "HELD")
            continue
        if len(badge_seen[badge.upper()]) > 1:
            exc("BLOCKER", "DUPLICATE_BADGE", "Users", rw, "", "", "Badge ID", badge, "Badge ID appears more than once; cannot tell who owns it.", "Resolve in the workbook.", "HELD")
            continue
        if bt in ("int", "float"):
            exc("INFO", "NUMERIC_BADGE", "Users", rw, "", "", "Badge ID", badge,
                "Badge stored as a NUMBER in the workbook; migrated as text digits. Leading zeros printed on a badge, if any, were already lost.",
                "Compare with a physical badge/scan.", "MIGRATED")
        R.employees.append({"Title": name, "BadgeID": badge, "EmployeeName": name,
                            "Active": "TRUE" if cfg.assume_all_employees_active else "FALSE",
                            "Role": cfg.default_employee_role, "MicrosoftUPN": "", "Notes": "Migrated from workbook Users sheet"})
    if R.employees:
        exc("WARN", "EMPLOYEE_ROLES_UNKNOWN", "Users", "all", "", "", "Role/Active/MicrosoftUPN", "",
            "The workbook has no Active, Role or Microsoft account column. All employees were imported Active with Role=Operator. Nobody can approve audits or new items until a Supervisor/Admin row has a MicrosoftUPN.",
            "Edit POUEmployees: set Role and MicrosoftUPN for supervisors and admins; set Active=No for leavers.", "MIGRATED_WITH_FLAG")

    # ---------------------------------------------------------------- legacy ledger
    stock_by_item = defaultdict(list)
    for s in R.stock:
        stock_by_item[s["ItemID"]].append(s)
    stock_keys = {s["StockKey"] for s in R.stock}

    def resolve(item_id):
        rows = stock_by_item.get(item_id, [])
        if len(rows) == 1:
            return rows[0], "UniqueAtCutover"
        return None, "Unresolved"

    def parse_ts(v, t, sheet, row, item):
        if t == "datetime":
            return datetime.fromisoformat(v)
        exc("BLOCKER", "INVALID_TIMESTAMP", sheet, row, item, "", "Timestamp", to_text(v), "Timestamp missing or not a date/time.", "Fix in workbook.", "HELD")
        return None

    def ledger_row(kind, sheet, row, item_id, ts, user, qty_fields, ltype):
        u, flag = _utc(ts, tz)
        if flag:
            exc("WARN", "AMBIGUOUS_LOCAL_TIME" if flag == "AMBIGUOUS" else "NONEXISTENT_LOCAL_TIME", sheet, row, item_id, "", "Timestamp", ts.isoformat(),
                f"Local time falls in a daylight-saving {'repeat' if flag == 'AMBIGUOUS' else 'gap'}; UTC conversion uses the first occurrence.", "Check if this matters.", "MIGRATED_WITH_FLAG")
        s, res = resolve(item_id)
        if s is None:
            why = "Item ID is not in the Inventory sheet" if item_id not in stock_by_item else f"Item ID has {len(stock_by_item[item_id])} stock locations and the legacy record has no location"
            exc("WARN", "LEGACY_LOCATION_UNRESOLVED", sheet, row, item_id, "", "Item ID", item_id, f"{why}. History row kept with ItemID only; no StockKey assigned.", "None required; usage-by-location excludes it.", "MIGRATED_WITH_FLAG")
        base = {
            "Title": f"LEGACY {sheet} r{row} {item_id}", "LedgerKey": f"LEGACY{KEY_SEP}{sheet}{KEY_SEP}r{row}",
            "RequestID": f"LEGACY-{sheet}-r{row}", "LedgerType": ltype, "Origin": "Legacy", "AffectsBalance": "FALSE",
            "PostingState": "Posted", "StockKey": s["StockKey"] if s else "", "ItemID": item_id,
            "LocationCode": s["LocationCode"] if s else "", "SeqNo": "", "QtyDelta": "", "QtyBefore": "", "QtyAfter": "",
            "EmployeeName": "", "StationID": "LEGACY",
            "OccurredUtc": u.strftime("%Y-%m-%dT%H:%M:%SZ"), "OccurredLocalText": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "Reason": "", "LegacyUser": user, "LegacyTimestampText": ts.isoformat(), "LegacySource": f"{sheet}!r{row}",
            "LocationResolution": res,
        }
        base.update(qty_fields)
        return base

    legacy_keys = set()
    for r in ex["transactions"]["rows"]:
        c, n = r["cells"], r["_row"]
        iv, it = _v(c, "Item ID")
        item_id = normalize_id(iv)
        tv, tt = _v(c, "Timestamp")
        ts = parse_ts(tv, tt, "Transactions", n, item_id) if tt != "none" else None
        ttype = clean_display(_v(c, "Transaction Type")[0]).upper()
        qv, qt = _v(c, "Quantity")
        q = to_int(qv, qt)
        user = clean_display(_v(c, "User")[0])
        bad = None
        if ts is None:
            bad = "timestamp"
        elif not item_id:
            bad = "item id"
            exc("BLOCKER", "LEGACY_BLANK_ITEM", "Transactions", n, "", "", "Item ID", "", "Transaction has no Item ID.", "Fix or discard.", "HELD")
        elif ttype not in ("ADD", "REMOVE"):
            bad = "type"
            exc("BLOCKER", "LEGACY_UNKNOWN_TYPE", "Transactions", n, item_id, "", "Transaction Type", ttype, "Type is not ADD or REMOVE; sign of quantity unknown.", "Fix or discard.", "HELD")
        elif q is None or q <= 0:
            bad = "qty"
            exc("BLOCKER", "LEGACY_INVALID_QTY", "Transactions", n, item_id, "", "Quantity", to_text(qv), "Quantity is not a positive whole number.", "Fix or discard.", "HELD")
        if bad:
            R.held_legacy.append({"Sheet": "Transactions", "Row": n, "Reason": bad, **{k: to_text(v["v"]) for k, v in c.items()}})
            continue
        if it in ("int", "float"):
            exc("INFO", "NUMERIC_ITEM_ID", "Transactions", n, item_id, "", "Item ID", item_id, "Legacy Item ID was numeric; migrated as digits text.", "None.", "MIGRATED")
        signed = q if ttype == "ADD" else -q
        row = ledger_row("tx", "Transactions", n, item_id, ts, user,
                         {"QtyDelta": signed}, "RECEIPT" if ttype == "ADD" else "ISSUE")
        legacy_keys.add(row["LedgerKey"])
        R.legacy_ledger.append(row)

    for r in ex["audits"]["rows"]:
        c, n = r["cells"], r["_row"]
        iv, it = _v(c, "Item ID")
        item_id = normalize_id(iv)
        tv, tt = _v(c, "Date/Time")
        ts = parse_ts(tv, tt, "InventoryAudit", n, item_id) if tt != "none" else None
        pv, pt = _v(c, "Previous Qty")
        cv, ct = _v(c, "Counted Qty")
        vv, vt = _v(c, "Variance")
        prev, cnt, var = to_int(pv, pt), to_int(cv, ct), to_int(vv, vt)
        user = clean_display(_v(c, "User")[0])
        if ts is None or not item_id or cnt is None or cnt < 0:
            R.held_legacy.append({"Sheet": "InventoryAudit", "Row": n, "Reason": "incomplete", **{k: to_text(v["v"]) for k, v in c.items()}})
            exc("BLOCKER", "LEGACY_INVALID_AUDIT", "InventoryAudit", n, item_id, "", "row", "", "Audit row is incomplete or invalid (timestamp, item, counted qty).", "Fix or discard.", "HELD")
            continue
        qf = {"QtyAfter": cnt}
        if prev is not None and prev >= 0:
            qf["QtyBefore"] = prev
            qf["QtyDelta"] = cnt - prev
            if var is not None and var != cnt - prev:
                exc("WARN", "LEGACY_AUDIT_VARIANCE_MISMATCH", "InventoryAudit", n, item_id, "", "Variance", var,
                    f"Recorded variance {var} differs from counted-previous = {cnt - prev}. Both preserved: QtyDelta uses counted-previous.", "None.", "MIGRATED_WITH_FLAG")
        row = ledger_row("audit", "InventoryAudit", n, item_id, ts, user, qf, "AUDIT")
        R.legacy_ledger.append(row)

    # legacy continuity check (informational)
    by_stock_audit = defaultdict(list)
    for lr in R.legacy_ledger:
        if lr["StockKey"]:
            by_stock_audit[lr["StockKey"]].append(lr)
    src_onhand = {q["StockKey"]: q["SourceOnHand"] for q in R.qty_recon}
    for sk, rows in by_stock_audit.items():
        rows.sort(key=lambda x: x["OccurredUtc"])
        last_audit = None
        for i, lr in enumerate(rows):
            if lr["LedgerType"] == "AUDIT":
                last_audit = i
        if last_audit is None:
            continue
        exp = rows[last_audit]["QtyAfter"] + sum(int(x["QtyDelta"]) for x in rows[last_audit + 1:] if x["QtyDelta"] != "")
        cur = src_onhand.get(sk, "")
        if cur != "" and exp != cur:
            exc("INFO", "LEGACY_HISTORY_DOES_NOT_EXPLAIN_BALANCE", "Transactions/InventoryAudit", "", rows[0]["ItemID"], rows[0]["LocationCode"], "On Hand",
                f"history implies {exp}, workbook shows {cur}",
                "Last legacy count plus later legacy movements does not equal the workbook's On Hand (the workbook allowed direct edits). Legacy rows are history only and never change the opening balance.",
                "Resolved by the physical opening count.", "MIGRATED")
        elif cur != "" and exp == cur:
            pass
    # audit chain gaps
    for sk, rows in by_stock_audit.items():
        aud = [x for x in rows if x["LedgerType"] == "AUDIT"]
        for a, b in zip(aud, aud[1:]):
            if b["QtyBefore"] != "" and a["QtyAfter"] != "" and b["QtyBefore"] != a["QtyAfter"]:
                between = [x for x in rows if a["OccurredUtc"] < x["OccurredUtc"] < b["OccurredUtc"] and x["LedgerType"] in ("ISSUE", "RECEIPT")]
                net = sum(int(x["QtyDelta"]) for x in between)
                if a["QtyAfter"] + net != b["QtyBefore"]:
                    exc("INFO", "LEGACY_AUDIT_CHAIN_GAP", "InventoryAudit", f"{a['LegacySource']} -> {b['LegacySource']}", a["ItemID"], a["LocationCode"], "Previous Qty",
                        f"{a['QtyAfter']} then {b['QtyBefore']}", "Counted quantity of one audit plus logged movements does not equal the next audit's Previous Qty (edited outside the logged workflow or test activity).",
                        "None; history preserved as recorded.", "MIGRATED")

    if R.legacy_ledger:
        who = Counter(lr["LegacyUser"] for lr in R.legacy_ledger)
        exc("INFO", "LEGACY_PILOT_ACTIVITY", "Transactions/InventoryAudit", "all", "", "", "User", ", ".join(f"{k} x{v}" for k, v in who.items()),
            f"Legacy history ({len(R.legacy_ledger)} rows, {min(l['OccurredUtc'] for l in R.legacy_ledger)[:10]} to {max(l['OccurredUtc'] for l in R.legacy_ledger)[:10]}) looks like pilot/test activity by few users. "
            "Imported as history (Origin=Legacy, AffectsBalance=No) with user NAMES only; no badge or location was invented. No quantity before/after was invented for movements.",
            "Decide whether to keep or skip pilot history (skip with --skip-legacy-ledger).", "MIGRATED")
        exc("INFO", "LEGACY_TIMEZONE_ASSUMED", "Transactions/InventoryAudit", "all", "", "", "Timestamp", "",
            f"Workbook timestamps carry no time zone. Assumed {cfg.source_timezone} (the PC that ran the macros) and converted to UTC. Original text kept in LegacyTimestampText.",
            "Confirm the cabinet PC was on Central time.", "MIGRATED")

    # not migrated by design
    notmig = [
        ("Launcher", "Instruction text for the VBA launcher button. Replaced by START_HERE / app instructions."),
        ("Scanner", "Hidden helper sheet used only by the old modScan macro. Not data."),
        ("Dashboard", "Hidden formulas over the Inventory sheet. Replaced by SharePoint views and the low-stock flag."),
        ("Usage Summary", "Hidden, empty report output. Replaced by the weekly usage flow."),
        ("ReorderReport", "Generated report output (stale snapshot). Replaced by the daily low-stock flow."),
        ("ReorderQueue", "Generated queue with stale rows (incl. negative suggested orders). Replaced by LowStockFlag + daily report; purchasing workflow is out of scope."),
    ]
    for sh, why in notmig:
        info = ex["other_sheets"].get(sh)
        if info:
            exc("INFO", "SHEET_NOT_MIGRATED", sh, "", "", "", "sheet", f"{info['nonblank_rows']} non-blank rows", why, "None.", "NOT_MIGRATED")
    exc("INFO", "BARCODE_COLUMN_DROPPED", "Inventory", "all", "", "", "Barcode", '="*"&A2&"*"',
        "Barcode is a formula that wraps the Item ID in Code-39 asterisks. It is derived data and is not migrated; existing printed tags keep working (the app strips * characters).", "None.", "NOT_MIGRATED")

    # low stock rule effect
    le = sum(1 for p in ok_rows if p["onhand"] is not None and p["onhand"] <= p["min"])
    lt = sum(1 for p in ok_rows if p["onhand"] is not None and p["onhand"] < p["min"])
    exc("INFO", "LOW_STOCK_RULE_DIFFERENCE", "Inventory", "all", "", "", "On Hand vs Min", f"<= Min: {le}; < Min: {lt}",
        "The original scanner warned at On Hand <= Min but the original Low Stock list used < Min. With this data <= flags %d stock records and < flags %d. Default is <= (setting LowStockRule)." % (le, lt),
        "Confirm the rule with purchasing; change setting LowStockRule (LE/LT).", "MIGRATED")
    mz = sum(1 for p in ok_rows if p.get("min_zero"))
    if mz:
        zero_oh = sum(1 for p in ok_rows if p.get("min_zero") and p["onhand"] == 0)
        exc("INFO", "MIN_ZERO", "Inventory", "multiple", "", "", "Min Qty", f"{mz} records",
            f"{mz} stock records have Min = 0 ({zero_oh} of them also have On Hand = 0). Under 'On Hand <= Min' they count as low stock at zero.", "Set meaningful minimums or deactivate unused records.", "MIGRATED")

    # ---------------------------------------------------------------- held inventory rows
    for p in parsed:
        if p["hold"]:
            R.held_inventory.append({"SourceRow": p["row"], **{k: to_text(v["v"]) for k, v in p["cells"].items()}})

    # ---------------------------------------------------------------- IDs, sorting
    E.sort(key=lambda e: (SEV_ORDER[e.severity], e.category, str(e.sheet), str(e.row), e.item_id))
    for i, e in enumerate(E, 1):
        e.id = f"EX-{i:04d}"

    # ---------------------------------------------------------------- reconciliation
    n_src_inv = len(inv_rows)
    n_ok = len(ok_rows)
    n_held = n_src_inv - n_ok
    src_total = sum(p["onhand"] for p in ok_rows if p["onhand"] is not None)
    all_src_total = 0
    for r in inv_rows:
        ov, ot = _v(r["cells"], "On Hand Qty")
        iv = to_int(ov, ot)
        if iv is not None and iv >= 0:
            all_src_total += iv
    open_total = sum(int(o["Quantity"]) for o in R.opening_requests)
    distinct_src_ids = len({normalize_id(_v(r["cells"], "Item ID")[0]) for r in inv_rows if normalize_id(_v(r["cells"], "Item ID")[0])})
    rc = R.row_counts
    def add(check, src, tgt, note=""):
        rc.append({"Check": check, "Source": src, "Target": tgt, "Difference": (tgt - src) if isinstance(src, int) and isinstance(tgt, int) else "",
                   "Status": "OK" if src == tgt else "REVIEW", "Note": note})
    add("Inventory rows -> stock-location records (+ held)", n_src_inv, len(R.stock) + n_held, f"{len(R.stock)} imported + {n_held} held in exceptions")
    add("Distinct Item IDs -> item master rows (+ ids wholly held)", distinct_src_ids, len(R.items) + len({p['item_id'] for p in parsed if p['hold'] and p['item_id']} - {i['ItemID'] for i in R.items}))
    add("Stock records with a numeric On Hand -> OPENING requests", sum(1 for p in ok_rows if p["onhand"] is not None), len(R.opening_requests))
    add("Stock records with blank/invalid On Hand -> NoBalance (no opening request)", sum(1 for p in ok_rows if p["onhand"] is None), len(R.stock) - len(R.opening_requests))
    add("Sum of source On Hand (imported rows) -> sum of OPENING quantities", src_total, open_total)
    add("Sum of source On Hand (all rows) -> imported rows + held rows", all_src_total, open_total + (all_src_total - src_total))
    add("Users rows -> employees (+ held)", len(ex["users"]["rows"]), len(R.employees) + sum(1 for e in E if e.sheet == "Users" and e.disposition == "HELD"))
    add("Transactions rows -> legacy ledger rows (+ held)", len(ex["transactions"]["rows"]),
        sum(1 for l in R.legacy_ledger if l["LegacySource"].startswith("Transactions!")) + sum(1 for h in R.held_legacy if h["Sheet"] == "Transactions"))
    add("InventoryAudit rows -> legacy ledger rows (+ held)", len(ex["audits"]["rows"]),
        sum(1 for l in R.legacy_ledger if l["LegacySource"].startswith("InventoryAudit!")) + sum(1 for h in R.held_legacy if h["Sheet"] == "InventoryAudit"))
    add("Locations: distinct normalised locations -> locations", len({normalize_id(p['loc']) for p in ok_rows}), len(R.locations))
    add("Duplicate StockKeys in import file", 0, len(R.stock) - len({s["StockKey"] for s in R.stock}))
    add("Duplicate LedgerKeys in legacy ledger", 0, len(R.legacy_ledger) - len({l["LedgerKey"] for l in R.legacy_ledger}))

    sev = Counter(e.severity for e in E)
    R.summary = {
        "source_file": ex["meta"]["source_file"], "source_sha256": src_sha,
        "inventory_rows": n_src_inv, "stock_records_imported": len(R.stock), "stock_records_held": n_held,
        "items": len(R.items), "locations": len(R.locations),
        "items_with_multiple_locations": sum(1 for rows in by_item.values() if len(rows) > 1),
        "opening_requests": len(R.opening_requests), "blank_or_invalid_onhand": len(R.stock) - len(R.opening_requests),
        "sum_opening_quantity": open_total, "employees": len(R.employees),
        "legacy_ledger_rows": len(R.legacy_ledger), "legacy_rows_held": len(R.held_legacy),
        "exceptions": dict(sev), "low_stock_le_min": le, "low_stock_lt_min": lt,
        "source_timezone_assumed": cfg.source_timezone,
    }
    return R


# ------------------------------------------------------------------------------------------------
def _write_csv(path: Path, cols, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow([r.get(c, "") if isinstance(r, dict) else r for c in cols] if isinstance(r, dict) else r)


def write_outputs(R: Result, out_root: Path):
    out_root = Path(out_root)
    imp, exd, rec = out_root / "import", out_root / "exceptions", out_root / "reconciliation"
    _write_csv(imp / "01_locations.csv", LOCATION_COLS, R.locations)
    _write_csv(imp / "02_employees.csv", EMPLOYEE_COLS, R.employees)
    _write_csv(imp / "03_items.csv", ITEM_COLS, R.items)
    _write_csv(imp / "04_stock_locations.csv", STOCK_COLS, R.stock)
    _write_csv(imp / "05_ledger_legacy.csv", LEDGER_COLS, R.legacy_ledger)
    _write_csv(imp / "06_opening_balance_requests.csv", REQUEST_COLS, R.opening_requests)
    # held rows (not importable)
    if R.held_inventory:
        cols = list(R.held_inventory[0].keys())
        _write_csv(exd / "held_inventory_rows.csv", cols, R.held_inventory)
    else:
        _write_csv(exd / "held_inventory_rows.csv", ["SourceRow"], [])
    if R.held_legacy:
        cols = sorted({k for h in R.held_legacy for k in h})
        _write_csv(exd / "held_legacy_rows.csv", cols, R.held_legacy)
    else:
        _write_csv(exd / "held_legacy_rows.csv", ["Sheet", "Row"], [])
    _write_csv(exd / "exceptions.csv", EXC_COLUMNS, [e.as_row() for e in R.exceptions])
    _write_csv(rec / "row_counts.csv", ["Check", "Source", "Target", "Difference", "Status", "Note"], R.row_counts)
    qcols = ["StockKey", "ItemID", "LocationCode", "SourceRow", "SourceOnHand", "SourceMin", "SourceMax", "OpeningRequestQty",
             "ExpectedBalanceStatusAfterOpening", "Status"]
    _write_csv(rec / "quantity_by_item_location.csv", qcols, R.qty_recon)
    (out_root / "summary.json").write_text(json.dumps(R.summary, indent=2) + "\n", encoding="utf-8")
    # human summary
    lines = ["# Migration run summary", "",
             f"Source: `{R.summary['source_file']}`  sha256 `{R.summary['source_sha256']}`", ""]
    for k, v in R.summary.items():
        if k not in ("source_file", "source_sha256"):
            lines.append(f"- **{k}**: {v}")
    lines += ["", "## Row-count reconciliation", "", "| Check | Source | Target | Status | Note |", "|---|---:|---:|---|---|"]
    for r in R.row_counts:
        lines.append(f"| {r['Check']} | {r['Source']} | {r['Target']} | {r['Status']} | {r['Note']} |")
    (out_root / "RUN_SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--extract", default="migration/source_extract/extract.json")
    ap.add_argument("--out", default="migration")
    ap.add_argument("--source-timezone", default="America/Chicago")
    a = ap.parse_args(argv)
    ex = json.loads(Path(a.extract).read_text(encoding="utf-8"))
    R = transform(ex, Config(source_timezone=a.source_timezone))
    write_outputs(R, Path(a.out))
    s = R.summary
    print(f"items={s['items']} stock={s['stock_records_imported']} (held {s['stock_records_held']}) opening={s['opening_requests']} "
          f"blank/invalid onhand={s['blank_or_invalid_onhand']} legacy ledger={s['legacy_ledger_rows']} employees={s['employees']} exceptions={s['exceptions']}")
    bad = [r for r in R.row_counts if r["Status"] != "OK"]
    if bad:
        print("RECONCILIATION REVIEW ITEMS:")
        for r in bad:
            print("  ", r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
