"""Step 3: load the import-ready CSVs into SharePoint.

* DRY-RUN BY DEFAULT (reads only). Use --apply to write.
* IDEMPOTENT / RESUMABLE: every row is looked up by its unique key first. Existing identical rows are left alone,
  existing DIFFERENT rows are reported (never overwritten), missing rows are created. Re-run after any interruption.
* BALANCES ARE NOT WRITTEN HERE. The importer refuses any stock file containing OnHandQty/StockVersion, and refuses a
  ledger file that is not Origin=Legacy / AffectsBalance=No / PostingState=Posted. Opening balances are created as
  OPENING *requests* (stage 'openings'); the Power Automate processor posts them, so the ledger explains every balance.
* WHO RUNS THIS: one-time migration under a Site Owner (Full Control) identity because StockLocations and Ledger are
  deliberately not writable by operators, supervisors or admins. The 'openings' stage additionally requires that
  identity to be an Active Admin in POUEmployees with MicrosoftUPN set (the processor checks the request author).

Usage:
  python -m pou_tools.import_data --site-url https://T.sharepoint.com/sites/POU --tenant ... --client-id ... [--apply]
        [--stages locations,employees,items,stock,ledger,openings] [--skip-legacy-ledger] [--import-dir migration/import]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from .schema import ListDef, Schema, load_schema
from .spclient import SpClient, SpError, odata_str

STAGES = [
    ("locations", "01_locations.csv", "POULocations", "LocationCode"),
    ("employees", "02_employees.csv", "POUEmployees", "BadgeID"),
    ("items", "03_items.csv", "POUItems", "ItemID"),
    ("stock", "04_stock_locations.csv", "POUStockLocations", "StockKey"),
    ("ledger", "05_ledger_legacy.csv", "POULedger", "LedgerKey"),
    ("openings", "06_opening_balance_requests.csv", "POURequests", "RequestID"),
]
FORBIDDEN_STOCK_COLUMNS = {"OnHandQty", "StockVersion", "LastLedgerKey", "LastPostedUtc", "LastCountedUtc"}


class ImportRefused(Exception):
    pass


def coerce(ld: ListDef, name: str, raw: str):
    """CSV text -> JSON value for the column type. Returns None for blank (column is then omitted, never written as '')."""
    if raw is None or raw == "":
        return None
    f = ld.field(name) if name != "Title" else None
    if f is None:
        return raw
    t = f.type
    if t == "Boolean":
        r = raw.strip().upper()
        if r in ("TRUE", "1", "YES"):
            return True
        if r in ("FALSE", "0", "NO"):
            return False
        raise ValueError(f"{name}: not a boolean: {raw!r}")
    if t in ("Number", "Currency"):
        x = float(raw)
        return int(x) if x == int(x) and t == "Number" else x
    return raw


def read_rows(path: Path, ld: ListDef) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        allowed = set(ld.field_names) | {"Title"}
        extra = [c for c in (rd.fieldnames or []) if c not in allowed]
        if extra:
            raise ImportRefused(f"{path.name}: columns not in list {ld.name}: {extra}")
        rows = []
        for raw in rd:
            row = {}
            for k, v in raw.items():
                cv = coerce(ld, k, v)
                if cv is not None:
                    row[k] = cv
            rows.append(row)
    return rows


def guard(stage: str, cols: set[str], rows: list[dict]):
    if stage == "stock":
        bad = cols & FORBIDDEN_STOCK_COLUMNS
        if bad:
            raise ImportRefused(f"stock file contains {sorted(bad)}: quantities may only arrive via OPENING requests posted by the flow")
        if any(r.get("BalanceStatus", "NoBalance") != "NoBalance" for r in rows):
            raise ImportRefused("stock rows must have BalanceStatus=NoBalance at import")
    if stage == "ledger":
        for r in rows:
            if not (r.get("Origin") == "Legacy" and r.get("AffectsBalance") is False and r.get("PostingState") == "Posted"):
                raise ImportRefused(f"ledger row {r.get('LedgerKey')} is not Origin=Legacy/AffectsBalance=No/PostingState=Posted")
            if not str(r.get("LedgerKey", "")).startswith("LEGACY|"):
                raise ImportRefused(f"ledger row key {r.get('LedgerKey')} does not start with LEGACY|")
    if stage == "openings":
        for r in rows:
            if r.get("RequestType") != "OPENING":
                raise ImportRefused("openings file must contain only RequestType=OPENING")


@dataclass
class StageResult:
    stage: str
    list: str
    total: int = 0
    created: int = 0
    would_create: int = 0
    exists_same: int = 0
    exists_different: list = field(default_factory=list)
    errors: list = field(default_factory=list)


def _same(existing: dict, row: dict) -> list[str]:
    diffs = []
    for k, v in row.items():
        ev = existing.get(k)
        if isinstance(v, bool) or isinstance(ev, bool):
            ok = bool(ev) == bool(v) if ev is not None else False
        elif isinstance(v, (int, float)) and ev is not None:
            ok = float(ev) == float(v)
        else:
            ok = (ev or "") == v if isinstance(v, str) else ev == v
        if not ok:
            diffs.append(k)
    return diffs


def run_stage(client: SpClient, schema: Schema, stage: str, path: Path, list_name: str, key: str, apply: bool,
              log=print, batch_pause: float = 0.0) -> StageResult:
    ld = schema[list_name]
    rows = read_rows(path, ld)
    cols = set().union(*[set(r) for r in rows]) if rows else set()
    guard(stage, cols, rows)
    res = StageResult(stage, list_name, total=len(rows))
    if client.get_list(list_name) is None:
        raise ImportRefused(f"List {list_name} does not exist. Run provisioning first.")
    select = ",".join(sorted(cols | {key, "Id"}))
    existing = {}
    for it in client.query(list_name, select=select, top=500):
        existing[str(it[key]).lower()] = it
    for i, row in enumerate(rows, 1):
        k = str(row[key])
        ex = existing.get(k.lower())
        if ex is not None:
            diffs = _same(ex, row)
            if diffs:
                res.exists_different.append({"key": k, "fields": diffs})
            else:
                res.exists_same += 1
            continue
        if not apply:
            res.would_create += 1
            continue
        try:
            client.create_item(list_name, row)
            res.created += 1
        except SpError as e:
            if e.is_duplicate:       # lost the race / previous run created it just before an error
                res.exists_same += 1
            else:
                res.errors.append({"key": k, "error": str(e)[:300]})
        if batch_pause:
            time.sleep(batch_pause)
        if i % 100 == 0:
            log(f"  {stage}: {i}/{len(rows)}")
    return res


def check_opening_authority(client: SpClient, log=print):
    me = client.current_user()
    upn = me.get("Email") or ""
    try:
        emp = list(client.query("POUEmployees", f"MicrosoftUPN eq '{odata_str(upn)}'", select="BadgeID,Role,Active", top=5))
    except SpError as e:
        log(f"  WARNING: cannot read POUEmployees ({e.status}); cannot confirm {upn} is an Active Admin there.")
        return False
    ok = any(e.get("Role") == "Admin" and e.get("Active") for e in emp)
    if not ok:
        log(f"  WARNING: {upn} is not an Active Admin with MicrosoftUPN set in POUEmployees. OPENING requests created by this identity "
            f"will be REJECTED by the processor (NOT_AUTHORIZED). Add yourself to POUEmployees (Role=Admin, MicrosoftUPN={upn}) first.")
    return ok


def run_all(client, schema, import_dir: Path, stages: list[str], apply: bool, skip_legacy_ledger=False, log=print):
    results = []
    me = client.current_user()
    log(f"Importing as {me.get('Email') or me.get('Title')} ({'APPLY' if apply else 'DRY-RUN'})")
    for st, fname, ln, key in STAGES:
        if st not in stages:
            continue
        if st == "ledger" and skip_legacy_ledger:
            log("  skipping legacy ledger (--skip-legacy-ledger)")
            continue
        if st == "openings":
            check_opening_authority(client, log)
        log(f"Stage {st}: {fname} -> {ln}")
        r = run_stage(client, schema, st, import_dir / fname, ln, key, apply, log)
        results.append(r)
        log(f"  total={r.total} created={r.created} would_create={r.would_create} already_same={r.exists_same} "
            f"different={len(r.exists_different)} errors={len(r.errors)}")
    return results


def main(argv=None):
    from .auth import make_provider
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site-url", required=True)
    ap.add_argument("--tenant"); ap.add_argument("--client-id")
    ap.add_argument("--auth", choices=["device", "env", "fake"], default="device")
    ap.add_argument("--fake-user", default="owner@test")
    ap.add_argument("--token-cache")
    ap.add_argument("--import-dir", default="migration/import")
    ap.add_argument("--stages", default="locations,employees,items,stock,ledger,openings")
    ap.add_argument("--skip-legacy-ledger", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--report")
    a = ap.parse_args(argv)
    client = SpClient(a.site_url, make_provider(a))
    res = run_all(client, load_schema(), Path(a.import_dir), a.stages.split(","), a.apply, a.skip_legacy_ledger)
    if a.report:
        Path(a.report).write_text(json.dumps([r.__dict__ for r in res], indent=2), encoding="utf-8")
    bad = sum(len(r.errors) for r in res) + sum(len(r.exists_different) for r in res)
    if not a.apply:
        print("DRY-RUN: nothing was written.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
