"""Step 4: post-import reconciliation. Compares what is in SharePoint with the import files and the opening-balance plan.

Checks (all read-only):
  * row counts per list vs. import files
  * every stock record: BalanceStatus / OnHandQty / StockVersion vs. the OPENING request quantity
      - OPENING request not yet processed -> PENDING_OPENING (not a failure)
      - blank-in-source -> must still be NoBalance with OnHandQty blank (never 0)
  * every OPENING must have exactly one Posted ledger row (SeqNo 1) whose QtyAfter equals the workbook quantity
  * sum of OnHandQty == sum of OPENING quantities (once all are processed)
  * legacy ledger rows: Origin=Legacy, AffectsBalance=No, no SeqNo, count equals import file
Exit code 0 only when nothing is MISMATCH / MISSING.

Usage: python -m pou_tools.verify_import --site-url ... --out migration/reconciliation/post_import_quantity_reconciliation.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

from .spclient import SpClient, SpError


def _csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def verify(client: SpClient, import_dir: Path, log=print):
    stock_f = _csv(import_dir / "04_stock_locations.csv")
    open_f = {r["StockKey"]: r for r in _csv(import_dir / "06_opening_balance_requests.csv")}
    ledger_f = _csv(import_dir / "05_ledger_legacy.csv")
    counts = []

    def cnt(title, n_file, n_sp, note=""):
        counts.append({"Check": title, "ImportFile": n_file, "SharePoint": n_sp, "Status": "OK" if n_file == n_sp else "MISMATCH", "Note": note})

    sp_stock = {r["StockKey"]: r for r in client.query("POUStockLocations", select="Id,StockKey,OnHandQty,StockVersion,BalanceStatus,LowStockFlag", top=500)}
    sp_items = sum(1 for _ in client.query("POUItems", select="Id", top=500))
    sp_loc = sum(1 for _ in client.query("POULocations", select="Id", top=500))
    sp_emp = sum(1 for _ in client.query("POUEmployees", select="Id", top=500))
    sp_legacy = list(client.query("POULedger", "Origin eq 'Legacy'", select="Id,LedgerKey,AffectsBalance,SeqNo,PostingState", top=500))
    opening_led = {r["StockKey"]: r for r in client.query("POULedger", "LedgerType eq 'OPENING'", select="Id,StockKey,SeqNo,QtyAfter,PostingState,RequestID", top=500)}
    opening_req = {r["StockKey"]: r for r in client.query("POURequests", "RequestType eq 'OPENING'", select="Id,StockKey,RequestStatus,ResultCode,ResultMessage", top=500)}

    cnt("Stock-location records", len(stock_f), len(sp_stock))
    cnt("Item master rows", len(_csv(import_dir / "03_items.csv")), sp_items)
    cnt("Locations", len(_csv(import_dir / "01_locations.csv")), sp_loc)
    cnt("Employees", len(_csv(import_dir / "02_employees.csv")), sp_emp)
    cnt("Legacy ledger rows", len(ledger_f), len(sp_legacy))
    bad_legacy = [r for r in sp_legacy if r.get("AffectsBalance") or r.get("SeqNo") is not None]
    counts.append({"Check": "Legacy rows that affect balance or carry a sequence number", "ImportFile": 0, "SharePoint": len(bad_legacy),
                   "Status": "OK" if not bad_legacy else "MISMATCH", "Note": "must be 0: legacy history never applies to stock"})

    rows = []
    tot_expected = tot_actual = 0
    for s in stock_f:
        sk = s["StockKey"]
        sp = sp_stock.get(sk)
        exp = open_f.get(sk)
        row = {"StockKey": sk, "ExpectedOpeningQty": exp["Quantity"] if exp else "", "SharePointOnHand": "", "SharePointBalanceStatus": "",
               "StockVersion": "", "OpeningRequestStatus": "", "OpeningLedgerQtyAfter": "", "Status": ""}
        if sp is None:
            row["Status"] = "MISSING_IN_SHAREPOINT"
            rows.append(row)
            continue
        oh = sp.get("OnHandQty")
        row["SharePointOnHand"] = "" if oh is None else int(oh)
        row["SharePointBalanceStatus"] = sp.get("BalanceStatus")
        row["StockVersion"] = int(sp.get("StockVersion") or 0)
        rq = opening_req.get(sk)
        row["OpeningRequestStatus"] = rq["RequestStatus"] if rq else ""
        lg = opening_led.get(sk)
        row["OpeningLedgerQtyAfter"] = "" if not lg else int(lg["QtyAfter"])
        if exp is None:
            # blank in source: must remain NoBalance and blank
            ok = oh is None and sp.get("BalanceStatus") == "NoBalance" and row["StockVersion"] == 0
            row["Status"] = "OK_NO_BALANCE" if ok else "MISMATCH_UNEXPECTED_BALANCE"
        else:
            q = int(exp["Quantity"])
            tot_expected += q
            if oh is None:
                if rq and rq["RequestStatus"] in ("Rejected", "Failed"):
                    row["Status"] = f"OPENING_{rq['RequestStatus'].upper()}"
                else:
                    row["Status"] = "PENDING_OPENING"
            else:
                tot_actual += int(oh)
                ledger_ok = lg is not None and lg.get("PostingState") == "Posted" and int(lg["QtyAfter"]) == q and int(lg["SeqNo"]) == 1
                ok = int(oh) == q and sp.get("BalanceStatus") == "Unverified" and row["StockVersion"] == 1 and ledger_ok
                row["Status"] = "OK" if ok else "MISMATCH"
        rows.append(row)
    cnt_status = Counter(r["Status"] for r in rows)
    pending = cnt_status.get("PENDING_OPENING", 0)
    counts.append({"Check": "Sum of on-hand (processed) vs sum of expected opening quantities", "ImportFile": tot_expected, "SharePoint": tot_actual,
                   "Status": "OK" if tot_expected == tot_actual else ("PENDING" if pending else "MISMATCH"), "Note": f"{pending} openings not yet processed"})
    extra = set(sp_stock) - {s["StockKey"] for s in stock_f}
    counts.append({"Check": "Stock records in SharePoint that are not in the import file", "ImportFile": 0, "SharePoint": len(extra),
                   "Status": "OK" if not extra else "REVIEW", "Note": ", ".join(sorted(extra))[:200]})
    bad = any(r["Status"].startswith("MISMATCH") or r["Status"].startswith("MISSING") or r["Status"].startswith("OPENING_") for r in rows) or \
        any(c["Status"] == "MISMATCH" for c in counts)
    return counts, rows, cnt_status, bad


def write(counts, rows, out: Path):
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["StockKey"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    with open(out.with_name(out.stem + "_counts.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Check", "ImportFile", "SharePoint", "Status", "Note"], lineterminator="\n")
        w.writeheader()
        w.writerows(counts)


def main(argv=None):
    from .auth import make_provider
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site-url", required=True)
    ap.add_argument("--tenant"); ap.add_argument("--client-id")
    ap.add_argument("--auth", choices=["device", "env", "fake"], default="device")
    ap.add_argument("--fake-user", default="owner@test")
    ap.add_argument("--token-cache")
    ap.add_argument("--import-dir", default="migration/import")
    ap.add_argument("--out", default="migration/reconciliation/post_import_quantity_reconciliation.csv")
    a = ap.parse_args(argv)
    client = SpClient(a.site_url, make_provider(a))
    counts, rows, st, bad = verify(client, Path(a.import_dir))
    write(counts, rows, Path(a.out))
    for c in counts:
        print(f"[{c['Status']:8}] {c['Check']}: file={c['ImportFile']} sharepoint={c['SharePoint']} {c['Note']}")
    print("by status:", dict(st))
    print("RESULT:", "FAIL" if bad else "PASS (or pending openings only)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
