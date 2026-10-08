"""Step 1 of the migration: extract the legacy workbook into a lossless, deterministic JSON file.

Nothing is cleaned, converted or dropped here. Every cell keeps its Excel value AND its storage type
(str / int / float / datetime / None) so later steps can see, for example, that Item ID 100416 was a NUMBER
in the workbook (leading zeros would already be gone) and that a description such as 30014234 was numeric.

Usage:
  python -m pou_tools.extract "POU_Inventory_Pilot Test _With_Badge.xlsm" --out migration/source_extract/extract.json

Re-running on the same workbook produces byte-identical output (no run timestamp inside the file).
The workbook is opened read-only; macros are never executed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime
from pathlib import Path

import openpyxl

EXTRACTOR_VERSION = "1.0"

INVENTORY_HEADERS = ["Item ID", "Item Name", "Location", "Min Qty", "Max Qty", "On Hand Qty", "Barcode", "Area:",
                     "Description", "Manufacturer", "Notes", "Priority", "Lead Time", "Cost per Unit"]
REQUIRED_INVENTORY = ["Item ID", "Item Name", "Location", "Min Qty", "Max Qty", "On Hand Qty"]
TX_HEADERS = ["Timestamp", "Item ID", "Transaction Type", "Quantity", "User"]
AUDIT_HEADERS = ["Date/Time", "Item ID", "Previous Qty", "Counted Qty", "Variance", "User"]
USER_HEADERS = ["Badge ID", "Employee Name"]
OTHER_SHEETS = ["Launcher", "ReorderReport", "ReorderQueue", "Usage Summary", "Dashboard", "Scanner"]


class ExtractError(Exception):
    pass


def _cell(v):
    """Lossless JSON form of a cell value."""
    if v is None:
        return {"v": None, "t": "none"}
    if isinstance(v, bool):
        return {"v": v, "t": "bool"}
    if isinstance(v, int):
        return {"v": v, "t": "int"}
    if isinstance(v, float):
        return {"v": v, "t": "float"}
    if isinstance(v, datetime):
        return {"v": v.replace(microsecond=0).isoformat(), "t": "datetime", "us": v.microsecond}
    if isinstance(v, date):
        return {"v": v.isoformat(), "t": "date"}
    return {"v": str(v), "t": "str"}


def _headers(ws, expected, required=None, row=1):
    found = {}
    for c in ws[row]:
        if c.value is not None and str(c.value).strip() != "":
            found[str(c.value).strip()] = c.column
    missing = [h for h in (required or expected) if h not in found]
    if missing:
        raise ExtractError(f"Sheet '{ws.title}' is missing expected header(s): {missing}. Found: {list(found)}")
    return found


def _block(ws, expected, required=None, last_col_hint=None):
    hdr = _headers(ws, expected, required)
    rows = []
    max_row = ws.max_row
    for r in range(2, max_row + 1):
        cells = {h: _cell(ws.cell(r, col).value) for h, col in hdr.items()}
        if all(c["t"] == "none" for c in cells.values()):
            continue
        rows.append({"_row": r, "cells": cells})
    return {"headers": list(hdr.keys()), "rows": rows}


def extract(path: str | Path) -> dict:
    path = Path(path)
    data = path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    wb = openpyxl.load_workbook(path, data_only=False, keep_vba=False)   # formulas as text; Barcode is a formula
    names = wb.sheetnames
    for need in ("Inventory", "Transactions", "InventoryAudit", "Users"):
        if need not in names:
            raise ExtractError(f"Workbook has no '{need}' sheet. Sheets: {names}")

    meta = {
        "extractor_version": EXTRACTOR_VERSION,
        "source_file": path.name,
        "source_sha256": sha,
        "source_bytes": len(data),
        "sheets": [{"name": ws.title, "state": ws.sheet_state, "dimensions": ws.dimensions} for ws in wb.worksheets],
    }

    inv = wb["Inventory"]
    table_ref = None
    for tname, t in inv.tables.items():
        table_ref = t if isinstance(t, str) else t.ref
        meta["inventory_table_name"] = tname
    inv_block = _block(inv, INVENTORY_HEADERS, REQUIRED_INVENTORY)
    # cells outside the table's columns, or below it
    stray = []
    if table_ref:
        from openpyxl.utils import range_boundaries
        c1, r1, c2, r2 = range_boundaries(table_ref)
        for row in inv.iter_rows():
            for c in row:
                if c.value is not None and (c.column > c2 or c.row > r2):
                    stray.append({"cell": c.coordinate, **_cell(c.value)})
        inv_rows_in_table = [r for r in inv_block["rows"] if r["_row"] <= r2]
        outside = [r for r in inv_block["rows"] if r["_row"] > r2]
        inv_block["rows"] = inv_rows_in_table
        for r in outside:
            for h, c in r["cells"].items():
                if c["t"] != "none":
                    stray.append({"cell": f"{h}@row{r['_row']}", **c})
    meta["inventory_table_ref"] = table_ref

    # number format of Item ID cells: 'General' for text and numbers alike; record the storage type only.
    out = {
        "meta": meta,
        "inventory": {**inv_block, "stray": stray},
        "transactions": _block(wb["Transactions"], TX_HEADERS),
        "audits": _block(wb["InventoryAudit"], AUDIT_HEADERS),
        "users": _block(wb["Users"], USER_HEADERS),
        "other_sheets": {},
    }
    for n in OTHER_SHEETS:
        if n in wb.sheetnames:
            ws = wb[n]
            nonblank = sum(1 for row in ws.iter_rows(values_only=True) if any(v is not None for v in row))
            out["other_sheets"][n] = {"state": ws.sheet_state, "dimensions": ws.dimensions, "nonblank_rows": nonblank}
    # VBA presence (informational; never executed)
    meta["contains_vba_project"] = any(n.lower().endswith("vbaproject.bin") for n in _zip_names(path))
    return out


def _zip_names(path):
    import zipfile
    try:
        with zipfile.ZipFile(path) as z:
            return z.namelist()
    except zipfile.BadZipFile:
        return []


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workbook")
    ap.add_argument("--out", default="migration/source_extract/extract.json")
    a = ap.parse_args(argv)
    ex = extract(a.workbook)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(ex, indent=1, sort_keys=False, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Extracted {a.workbook}: sha256={ex['meta']['source_sha256'][:12]}… "
          f"inventory={len(ex['inventory']['rows'])} transactions={len(ex['transactions']['rows'])} "
          f"audits={len(ex['audits']['rows'])} users={len(ex['users']['rows'])} stray={len(ex['inventory']['stray'])}")
    print(f"Wrote {a.out}")


if __name__ == "__main__":
    sys.exit(main())
