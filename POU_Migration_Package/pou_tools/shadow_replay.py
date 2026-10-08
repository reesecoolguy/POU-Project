"""SHADOW / REPLAY comparison period - a rehearsal of the new system on REAL workbook activity, WITHOUT dual live posting.

The workbook stays the only live system. This tool takes the movements the workbook recorded since the baseline snapshot and replays them
into a separate TEST copy of the SharePoint site (a second site provisioned and imported exactly like production, with the baseline
OPENING balances posted). The test site's own flows process them like real requests; then `compare` lists, item/location by item/location,
where the test site and the workbook disagree and why. Staff type each movement ONCE, into the workbook. Nothing here touches production.

  1. python -m pou_tools.extract "<workbook>" --out migration/shadow/baseline.json          (the day the test site was imported; keep it)
  2. python -m pou_tools.extract "<workbook>" --out migration/shadow/current.json           (any later day, from a COPY of the live workbook)
  3. python -m pou_tools.shadow_replay plan    --baseline migration/shadow/baseline.json --current migration/shadow/current.json
  4. python -m pou_tools.shadow_replay replay  ... --site-url <TEST site> [--apply]          (dry run unless --apply)
  5. wait for the TEST site's sweeper to post them (5-minute cadence)
  6. python -m pou_tools.shadow_replay compare ... --site-url <TEST site>

What it cannot do, by design (and says so in its output):
  * The workbook never recorded a LOCATION. A movement for an item stocked in more than one location cannot be attributed: it is listed
    as AMBIGUOUS_LOCATION, never guessed. Reconcile those items by a physical count.
  * Workbook COUNTS (InventoryAudit) overwrite On Hand. They are not replayed; their variance is used to EXPLAIN a difference.
  * Test-site settings: set ServerSessionMaxIdleMinutes high (e.g. 720) in the TEST site, because replayed requests are created in bursts.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .auth import make_provider
from .keys import normalize_id
from .spclient import SpClient
from .transform import transform

REPLAY_BADGE, REPLAY_NAME, REPLAY_STATION = "REPLAYBOT", "Replay (shadow test)", "SHADOW"


@dataclass
class Move:
    request_id: str
    sheet: str
    row: int
    ts: str
    item: str
    kind: str                # RECEIPT | ISSUE
    qty: object
    user: str
    stock_key: str = ""
    location: str = ""
    status: str = "REPLAYABLE"   # REPLAYABLE | AMBIGUOUS_LOCATION | UNKNOWN_ITEM | BAD_QUANTITY | BAD_TYPE


@dataclass
class Plan:
    moves: list[Move] = field(default_factory=list)
    audits: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _cell(c, h):
    x = c.get(h)
    return None if x is None else x["v"]


def _max_row(ex, sheet):
    return max((r["_row"] for r in ex[sheet]["rows"]), default=1)


def build_plan(baseline: dict, current: dict) -> Plan:
    base = transform(baseline)
    by_item: dict[str, list[dict]] = {}
    for s in base.stock:
        by_item.setdefault(s["ItemID"], []).append(s)
    P = Plan()
    last_tx, last_au = _max_row(baseline, "transactions"), _max_row(baseline, "audits")
    # the baseline rows must be unchanged, otherwise "new rows" is not trustworthy
    base_sig = {r["_row"]: json.dumps(r["cells"], sort_keys=True) for r in baseline["transactions"]["rows"]}
    for r in current["transactions"]["rows"]:
        if r["_row"] in base_sig and base_sig[r["_row"]] != json.dumps(r["cells"], sort_keys=True):
            P.notes.append(f"Transactions row {r['_row']} differs from the baseline: history was edited after the snapshot.")
    for r in current["transactions"]["rows"]:
        if r["_row"] <= last_tx:
            continue
        c = r["cells"]
        item = normalize_id(_cell(c, "Item ID"))
        t = str(_cell(c, "Transaction Type") or "").strip().upper()
        q = _cell(c, "Quantity")
        m = Move(f"SHADOW-T-r{r['_row']}", "Transactions", r["_row"], str(_cell(c, "Timestamp") or ""), item,
                 {"ADD": "RECEIPT", "REMOVE": "ISSUE"}.get(t, t), q, str(_cell(c, "User") or ""))
        if t not in ("ADD", "REMOVE"):
            m.status = "BAD_TYPE"
        elif not isinstance(q, int) or isinstance(q, bool) or q < 1:
            m.status = "BAD_QUANTITY"
        elif item not in by_item:
            m.status = "UNKNOWN_ITEM"
        elif len(by_item[item]) > 1:
            m.status = "AMBIGUOUS_LOCATION"
        else:
            s = by_item[item][0]
            m.stock_key, m.location = s["StockKey"], s["LocationCode"]
        P.moves.append(m)
    for r in current["audits"]["rows"]:
        if r["_row"] <= last_au:
            continue
        c = r["cells"]
        P.audits.append({"row": r["_row"], "item": normalize_id(_cell(c, "Item ID")), "variance": _cell(c, "Variance"),
                         "previous": _cell(c, "Previous Qty"), "counted": _cell(c, "Counted Qty")})
    P.notes.append("Audit rows are NOT replayed (a workbook count overwrites On Hand); their variances are used to explain differences.")
    return P


def write_plan(P: Plan, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "replay_plan.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["RequestID", "SourceSheet", "SourceRow", "SourceTimestamp", "ItemID", "RequestType", "Quantity", "StockKey", "User", "Status"])
        for m in P.moves:
            w.writerow([m.request_id, m.sheet, m.row, m.ts, m.item, m.kind, m.qty, m.stock_key, m.user, m.status])


def replay(client: SpClient, P: Plan, apply: bool, log=print) -> dict:
    """Create the replay employee/station/session (once) and one request per REPLAYABLE movement, oldest first. Idempotent by RequestID."""
    me = client.current_user()
    upn = (me.get("Email") or me.get("LoginName", "").split("|")[-1]).lower()
    res = {"created": 0, "existing": 0, "skipped": 0}
    todo = [m for m in P.moves if m.status == "REPLAYABLE"]
    res["skipped"] = len(P.moves) - len(todo)
    log(f"{'APPLY' if apply else 'DRY-RUN'}: {len(todo)} replayable movements, {res['skipped']} not replayable (see replay_plan.csv)")
    if not apply:
        return res
    if not client.get_by_key("POUEmployees", "BadgeID", REPLAY_BADGE):
        client.create_item("POUEmployees", {"Title": REPLAY_NAME, "BadgeID": REPLAY_BADGE, "EmployeeName": REPLAY_NAME, "Active": True, "Role": "Operator"})
    if not client.get_by_key("POUStations", "StationID", REPLAY_STATION):
        client.create_item("POUStations", {"Title": REPLAY_STATION, "StationID": REPLAY_STATION, "Active": True})
    sid = "SHADOWSESSION"
    sess = client.get_by_key("POUSessions", "SessionID", sid)
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = {"Title": "Shadow replay session", "SessionID": sid, "BadgeID": REPLAY_BADGE, "EmployeeName": REPLAY_NAME, "StationID": REPLAY_STATION,
            "AppAccountUPN": upn, "StartedUtc": now, "LastActivityUtc": now, "SessionState": "Active"}
    if sess:
        client.update_item("POUSessions", sess["Id"], {"AppAccountUPN": upn, "LastActivityUtc": now, "SessionState": "Active"})
    else:
        client.create_item("POUSessions", body)
    for m in sorted(todo, key=lambda x: (x.ts, x.row)):
        if client.get_by_key("POURequests", "RequestID", m.request_id):
            res["existing"] += 1
            continue
        client.create_item("POURequests", {
            "Title": f"{m.kind} {m.qty} x {m.item} (replay of workbook row {m.row})", "RequestID": m.request_id, "RequestType": m.kind,
            "RequestStatus": "Pending", "IsOpen": True, "SessionID": sid, "StationID": REPLAY_STATION, "StockKey": m.stock_key, "ItemID": m.item,
            "LocationCode": m.location, "Quantity": m.qty, "Reason": f"shadow replay {m.sheet}!r{m.row} {m.ts} {m.user}", "ClientLocalTime": m.ts})
        res["created"] += 1
    log(f"created {res['created']} requests ({res['existing']} already existed). The test site's sweeper will post them.")
    return res


def compare(client: SpClient, current: dict, P: Plan) -> list[dict]:
    cur = transform(current)
    wb_qty = {o["StockKey"]: o["Quantity"] for o in cur.opening_requests}
    site = {r["StockKey"]: r for r in client.query("POUStockLocations", select="StockKey,OnHandQty,BalanceStatus", top=500)}
    pending = {r["StockKey"] for r in client.query("POURequests", "IsOpen eq 1", select="StockKey", top=500) if r.get("StockKey")}
    amb_items = {m.item for m in P.moves if m.status == "AMBIGUOUS_LOCATION"}
    bad_items = {m.item for m in P.moves if m.status in ("UNKNOWN_ITEM", "BAD_QUANTITY", "BAD_TYPE")}
    variance = {}
    for a in P.audits:
        if isinstance(a["variance"], (int, float)):
            variance[a["item"]] = variance.get(a["item"], 0) + a["variance"]
    rows = []
    for s in cur.stock:
        k, item = s["StockKey"], s["ItemID"]
        w, t = wb_qty.get(k), (site.get(k) or {}).get("OnHandQty")
        if k not in site:
            st, d = "MISSING_IN_SITE", None
        elif w is None and t is None:
            st, d = "NOBALANCE_BOTH", None
        elif w is None or t is None:
            st, d = "NOBALANCE_ONE_SIDE", None
        else:
            d = t - w
            if k in pending:
                st = "NOT_YET_PROCESSED"
            elif d == 0 and item not in amb_items:
                st = "MATCH"
            elif item in amb_items:
                st = "AMBIGUOUS_ITEM"
            elif item in bad_items and d != 0:
                st = "DIFF_UNREPLAYABLE_ROWS"
            elif item in variance and d == -variance[item]:
                st = "EXPLAINED_BY_AUDIT"
            else:
                st = "DIFF" if d else "MATCH"
        rows.append({"StockKey": k, "WorkbookOnHand": w, "TestSiteOnHand": t, "Difference": d, "Status": st,
                     "AuditVarianceSinceBaseline": variance.get(item, "")})
    return rows


def write_compare(rows, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "shadow_compare.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["plan", "replay", "compare"])
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--current", required=True)
    ap.add_argument("--out", default="migration/shadow")
    ap.add_argument("--site-url"); ap.add_argument("--tenant"); ap.add_argument("--client-id")
    ap.add_argument("--auth", choices=["device", "env", "fake"], default="device")
    ap.add_argument("--fake-user", default="owner@test")
    ap.add_argument("--token-cache")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    base, cur = json.load(open(a.baseline, encoding="utf-8")), json.load(open(a.current, encoding="utf-8"))
    P = build_plan(base, cur)
    write_plan(P, Path(a.out))
    counts = {}
    for m in P.moves:
        counts[m.status] = counts.get(m.status, 0) + 1
    print("plan:", counts or "no new movements", "| audits since baseline:", len(P.audits))
    for n in P.notes:
        print("NOTE:", n)
    if a.action == "plan":
        return 0
    if not a.site_url:
        raise SystemExit("--site-url (the TEST site) is required")
    if "CHANGE-ME" in a.site_url:
        raise SystemExit("site url still contains CHANGE-ME")
    c = SpClient(a.site_url, make_provider(a))
    if a.action == "replay":
        replay(c, P, a.apply)
        return 0
    rows = compare(c, cur, P)
    write_compare(rows, Path(a.out))
    tally = {}
    for r in rows:
        tally[r["Status"]] = tally.get(r["Status"], 0) + 1
    print("compare:", tally, "->", Path(a.out) / "shadow_compare.csv")
    return 0 if not tally.get("DIFF") and not tally.get("MISSING_IN_SITE") else 1


if __name__ == "__main__":
    sys.exit(main())
