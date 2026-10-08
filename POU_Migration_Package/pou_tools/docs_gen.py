"""Generates the reference tables in docs/ from the single sources of truth (schema/*.json), so documents cannot drift from the code."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

# Source workbook column -> target field. Every row is implemented in pou_tools/transform.py and covered by tests/test_transform.py.
MAPPING = [
    ("Inventory", "Item ID", "POUItems.ItemID  +  POUStockLocations.ItemID", "Text, exactly as stored. A numeric cell becomes its digits ('100416'); leading zeros cannot be recovered from a number and are reported (NUMERIC_ITEM_ID). Never zero-padded."),
    ("Inventory", "Item ID + Location", "POUStockLocations.StockKey", "UPPER(TRIM(ItemID)) | UPPER(TRIM(Location)). One stock record per item per location. K102516, K102517 and K13471 therefore produce several stock records under ONE item."),
    ("Inventory", "Item Name", "POUItems.ItemName  +  POUStockLocations.ItemName (copy)", "Master value taken from the first row of the item; differences between rows are reported (SAME_NAME_DIFFERENT_ID / MASTER_VALUE_FROM_SIBLING_ROW)."),
    ("Inventory", "Location", "POULocations.LocationCode  +  POUStockLocations.LocationCode", "Distinct spellings (22) become the location list. Non-standard codes are reported, never changed."),
    ("Inventory", "Min Qty", "POUStockLocations.MinQty", "As is. Min = 0 reported (MIN_ZERO)."),
    ("Inventory", "Max Qty", "POUStockLocations.MaxQty", "As is. Max = 0 reported (MAX_ZERO). Never used to cap a quantity."),
    ("Inventory", "On Hand Qty", "POURequests (OPENING) -> POULedger -> POUStockLocations.OnHandQty", "NOT written to the stock record by the import. Each numeric value becomes one OPENING request that the flow posts, so the ledger explains the balance. A BLANK value creates a stock record with BalanceStatus=NoBalance and NO opening request (BLANK_ONHAND). Blank is never zero. Values above Max are kept (ONHAND_ABOVE_MAX)."),
    ("Inventory", "Barcode", "(not migrated)", "Formula `=\"*\"&A2&\"*\"`. Derived data. Existing printed tags keep working: the app removes * characters."),
    ("Inventory", "Area:", "POUStockLocations.Area", "As is (single value in this workbook: AREA_SINGLE_VALUE)."),
    ("Inventory", "Description", "POUItems.Description", "Multi-line text kept."),
    ("Inventory", "Manufacturer", "POUItems.Manufacturer", "As is; spelling variants reported, not merged (MANUFACTURER_SPELLING_VARIANTS)."),
    ("Inventory", "Notes / Priority / Lead Time / Cost per Unit", "POUItems.Notes / Priority / LeadTimeDays / UnitCost", "Carried when present; empty source columns reported (SOURCE_COLUMN_EMPTY). Nothing invented."),
    ("Inventory", "(row number)", "POUStockLocations.LegacySourceRow, POUItems.LegacySourceRows", "Provenance back to the workbook row."),
    ("Users", "Badge ID", "POUEmployees.BadgeID", "Text. Numeric badges keep their digits (NUMERIC_BADGE)."),
    ("Users", "Employee Name", "POUEmployees.EmployeeName", "As is."),
    ("Users", "(none)", "POUEmployees.Active / Role / MicrosoftUPN", "The workbook has no such columns: everyone is imported Active, Role=Operator, MicrosoftUPN empty (EMPLOYEE_ROLES_UNKNOWN). Supervisors/Admins must be set up by hand (docs/07_Deployment.md)."),
    ("Transactions", "Timestamp", "POULedger.OccurredUtc (+ OccurredLocalText, LegacyTimestampText)", "Original timestamp kept. The workbook stores no time zone: America/Chicago is ASSUMED and converted to UTC; ambiguous/non-existent DST times are flagged (LEGACY_TIMEZONE_ASSUMED)."),
    ("Transactions", "Item ID", "POULedger.ItemID (+ LocationCode only if provable)", "Location was never recorded. LocationResolution = UniqueAtCutover only when the item is stocked in exactly ONE location; Unresolved otherwise. No location is guessed."),
    ("Transactions", "Transaction Type / Quantity", "POULedger.LedgerType (ADD->RECEIPT, REMOVE->ISSUE), QtyDelta (signed)", "QtyBefore/QtyAfter stay BLANK: the workbook did not record them."),
    ("Transactions", "User", "POULedger.LegacyUser / EmployeeName", "The NAME as typed in the workbook. No badge is attached and no employee identity is inferred."),
    ("InventoryAudit", "Date/Time, Item ID, Previous Qty, Counted Qty, Variance, User", "POULedger (LedgerType=AUDIT)", "QtyBefore=Previous, QtyAfter=Counted, QtyDelta=Counted-Previous. If the recorded Variance disagrees both are preserved and flagged. Chain gaps between consecutive counts are reported (LEGACY_AUDIT_CHAIN_GAP)."),
    ("(all legacy ledger rows)", "-", "POULedger.Origin=Legacy, AffectsBalance=No, PostingState=Posted", "History only. These rows are NOT re-applied to any balance; the balance comes only from the verified OPENING at cutover."),
    ("ReorderQueue / ReorderReport / Usage Summary / Dashboard / Scanner / Launcher", "-", "(not migrated)", "Derived or scratch sheets (SHEET_NOT_MIGRATED). Replaced by LowStockFlag, the daily low-stock report and the weekly 30/90-day usage report."),
]


def md_lists(schema) -> str:
    out = ["# Data model (generated from schema/lists.json)", "",
           "Do not edit by hand: edit `schema/lists.json` and run `python -m pou_tools.docs_gen`. Provisioning (`pou_tools.provision`) reads the same file.", ""]
    out += ["## Conventions", ""] + [f"* **{k}**: {v}" for k, v in schema["conventions"].items()] + [""]
    for l in schema["lists"]:
        out += [f"## {l['name']}", "", l["description"], "", f"Expected size: {l.get('growth', '')}", "",
                "| Column | Type | Required | Index | Unique | Notes |", "|---|---|---|---|---|---|"]
        for f in l["fields"]:
            typ = f["type"] + (f" ({', '.join(f['choices'])})" if f.get("choices") else "") + (f" max {f['maxLength']}" if f.get("maxLength") else "")
            note = f.get("description", "")
            if f.get("default") is not None:
                note = (note + f" Default: {f['default']}.").strip()
            out.append(f"| `{f['name']}` | {typ} | {'yes' if f.get('required') else ''} | {'yes' if f.get('indexed') else ''} | {'**yes**' if f.get('unique') else ''} | {note} |")
        out.append("")
    return "\n".join(out) + "\n"


def md_mapping() -> str:
    out = ["# Source-to-target field mapping", "",
           "Source: `POU_Inventory_Pilot Test _With_Badge.xlsm`. Every row below is implemented in `pou_tools/transform.py` and covered by `tests/test_transform.py`; "
           "the numbers for the real workbook are in `migration/RUN_SUMMARY.md`; every anomaly is in `migration/exceptions/exceptions.csv`.", "",
           "| Source sheet | Source column | Target | Rule |", "|---|---|---|---|"]
    out += [f"| {a} | {b} | `{c}` | {d} |" for a, b, c, d in MAPPING]
    return "\n".join(out) + "\n"


def md_permissions(perms) -> str:
    groups = {g["key"]: g for g in perms["groups"]}
    roles = {r["key"]: r for r in perms["roleDefinitions"]}
    label = {None: "none (list invisible)", "read": "Read", "addonly": "Read + **Add** only", "flowwriter": "Read + Add + Edit (no delete)", "contribute": "Contribute (read/add/edit/delete)"}
    out = ["# Permissions matrix (generated from schema/permissions.json)", "", *[f"* {n}" for n in perms["notes"]], "",
           "## Groups", ""]
    out += [f"* **{g['title']}**: {g['description']}" for g in perms["groups"]]
    out += ["", "## Custom permission levels", ""]
    out += [f"* **{r['name']}** ({'built in' if r.get('builtin') else 'created by provisioning'}): {r.get('description', '')}" for r in perms["roleDefinitions"]]
    out += ["", "## Matrix", "", "| List | " + " | ".join(groups[k]["title"] for k in groups) + " |", "|---|" + "---|" * len(groups)]
    for ln, row in perms["matrix"].items():
        out.append(f"| `{ln}` | " + " | ".join(label[row[k]] for k in groups) + " |")
    out += ["", "The site **Owners** group keeps Full Control as break-glass. Any use of it bypasses the posting protocol; the nightly reconciliation (POU-Reconcile) detects the consequences."]
    return "\n".join(out) + "\n"


def main():
    schema = json.loads((ROOT / "schema" / "lists.json").read_text())
    perms = json.loads((ROOT / "schema" / "permissions.json").read_text())
    DOCS.mkdir(exist_ok=True)
    (DOCS / "03a_Data_Model.md").write_text(md_lists(schema))
    (DOCS / "03b_Field_Mapping.md").write_text(md_mapping())
    (DOCS / "04a_Permissions_Matrix.md").write_text(md_permissions(perms))
    print("wrote docs/03a_Data_Model.md, 03b_Field_Mapping.md, 04a_Permissions_Matrix.md")


if __name__ == "__main__":
    main()
