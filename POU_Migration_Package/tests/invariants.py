"""Ledger/stock invariants that must hold after ANY interleaving or crash."""
from __future__ import annotations

from collections import defaultdict


def check(env, expect_complete=False):
    owner = env.c("owner@test")
    stock = {s["StockKey"]: s for s in owner.query("POUStockLocations", top=500)}
    ledger = list(owner.query("POULedger", top=500))
    reqs = {r["RequestID"]: r for r in owner.query("POURequests", top=500)}
    by_stock = defaultdict(list)
    for l in ledger:
        if l["PostingState"] in ("Posted", "Intent") and l["AffectsBalance"]:
            by_stock[l["StockKey"]].append(l)
    problems = []
    for sk, rows in by_stock.items():
        rows.sort(key=lambda r: r["SeqNo"])
        seqs = [r["SeqNo"] for r in rows]
        if seqs != list(range(1, len(rows) + 1)):
            problems.append(f"{sk}: sequence gap/dup {seqs}")
            continue
        for a, b in zip(rows, rows[1:]):
            if b["QtyBefore"] != a["QtyAfter"]:
                problems.append(f"{sk}: chain break seq {b['SeqNo']} before={b['QtyBefore']} prev after={a['QtyAfter']}")
        s = stock[sk]
        k = len(rows)
        v = s["StockVersion"]
        if v == k:
            if s["OnHandQty"] != rows[-1]["QtyAfter"]:
                problems.append(f"{sk}: OnHand {s['OnHandQty']} != last ledger after {rows[-1]['QtyAfter']}")
        elif v == k - 1:
            if rows[-1]["PostingState"] != "Intent":
                problems.append(f"{sk}: version {v} lags a row that is not an Intent")
            prev_after = rows[-2]["QtyAfter"] if k > 1 else None
            if s["OnHandQty"] != prev_after:
                problems.append(f"{sk}: OnHand {s['OnHandQty']} != after of seq {k-1} ({prev_after})")
        else:
            problems.append(f"{sk}: StockVersion {v} inconsistent with {k} ledger rows")
        if s["OnHandQty"] is not None and s["OnHandQty"] < 0:
            problems.append(f"{sk}: negative stock")
        for r in rows:
            if r["PostingState"] == "Posted" and r["SeqNo"] > v:
                problems.append(f"{sk}: Posted row seq {r['SeqNo']} beyond stock version {v}")
    for sk, s in stock.items():
        if sk not in by_stock and (s["StockVersion"] or 0) != 0:
            problems.append(f"{sk}: version {s['StockVersion']} with no ledger rows")
        if sk not in by_stock and s["OnHandQty"] is not None:
            problems.append(f"{sk}: has a balance but no ledger rows")
    led_by_req = {l["RequestID"]: l for l in ledger if l["PostingState"] != "Voided"}
    for rid, r in reqs.items():
        st, eff = r["RequestStatus"], r["InventoryEffect"]
        if st == "Succeeded" and r["RequestType"] in ("ISSUE", "RECEIPT", "AUDIT", "OPENING", "ADJUSTMENT", "REVERSAL"):
            l = led_by_req.get(rid)
            if not l or l["PostingState"] != "Posted":
                problems.append(f"request {rid[:8]} Succeeded without a Posted ledger row")
        if eff == "NotApplied" and r["RequestType"] in ("ISSUE", "RECEIPT", "AUDIT", "OPENING", "ADJUSTMENT", "REVERSAL") and rid in led_by_req:
            problems.append(f"request {rid[:8]} says NotApplied but a ledger row exists")
        if eff == "Applied" and rid not in led_by_req:
            problems.append(f"request {rid[:8]} says Applied but no ledger row")
        if expect_complete and st in ("Pending", "Processing"):
            problems.append(f"request {rid[:8]} still {st}")
    if expect_complete:
        for l in ledger:
            if l["PostingState"] == "Intent":
                problems.append(f"ledger {l['LedgerKey']} still Intent")
    return problems
