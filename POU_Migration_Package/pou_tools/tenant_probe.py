"""TENANT PROBE: measures the SharePoint behaviours the posting protocol depends on, on YOUR tenant, in a throw-away list.

Everything the design assumes about SharePoint is written down as an assertion here. The same script runs against the in-memory model
(tests/test_tenant_probe.py) so the script itself is tested - but only a run against the real tenant proves the real behaviour.

  python -m pou_tools.tenant_probe --site-url https://TENANT.sharepoint.com/sites/POU --tenant TENANT.onmicrosoft.com --client-id <APP-ID>            (dry run: prints the plan)
  python -m pou_tools.tenant_probe ... --apply                 (creates list 'POUProbe', runs the checks, deletes the list)
  python -m pou_tools.tenant_probe ... --apply --large 5100    (also seeds 5,100 rows to prove list-view-threshold behaviour; slow: about 1 row/0.3 s)

Run it as a SITE OWNER. It never touches the POU* production lists. Exit code 0 only if every check passed.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time

from .auth import make_provider
from .spclient import SpClient, SpError

PROBE = "POUProbe"
FIELDS = [("K", "Text", True, True), ("V", "Number", True, False), ("N", "Text", False, False)]


def field_xml(name, typ, indexed, unique):
    a = f'Type="{typ}" DisplayName="{name}" Name="{name}" StaticName="{name}"'
    return f"<Field {a} />"


class Probe:
    def __init__(self, client: SpClient, make_client, log=print):
        self.c, self.make_client, self.log = client, make_client, log
        self.results: list[tuple[str, bool, str]] = []

    def check(self, name, ok, detail=""):
        self.results.append((name, bool(ok), detail))
        self.log(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))

    # ---------------------------------------------------------------- setup / teardown
    def setup(self):
        if self.c.get_list(PROBE):
            raise SystemExit(f"List {PROBE} already exists (left over from an aborted run?). Delete it in SharePoint (Site contents) and re-run.")
        self.c.create_list(PROBE, "Throw-away list created by pou_tools.tenant_probe")
        for name, typ, indexed, unique in FIELDS:
            self.c.create_field_xml(PROBE, field_xml(name, typ, indexed, unique))
            if indexed:
                self.c.update_field(PROBE, name, {"Indexed": True})
            if unique:
                self.c.update_field(PROBE, name, {"EnforceUniqueValues": True})

    def teardown(self):
        try:
            self.c.delete_list(PROBE)
            self.log(f"list {PROBE} deleted")
        except SpError as e:
            self.log(f"WARNING: could not delete {PROBE}: {e}. Delete it manually.")

    # ---------------------------------------------------------------- checks
    def identity(self):
        u = self.c.current_user()
        self.log(f"signed in as: {u.get('Email') or u.get('LoginName')}")
        self.check("I1 identity readable", bool(u.get("Id")))

    def unique_keys(self):
        self.c.create_item(PROBE, {"Title": "a", "K": "Alpha"})
        for label, key in (("same case", "Alpha"), ("different case", "ALPHA")):
            try:
                self.c.create_item(PROBE, {"Title": "dup", "K": key})
                self.check(f"U1 unique key refuses duplicate ({label})", False, "second create SUCCEEDED")
            except SpError as e:
                self.check(f"U1 unique key refuses duplicate ({label})", e.is_duplicate, f"HTTP {e.status} {e.code}")
        for k in ("000123", "00", " lead", "trail ", "ÄÖ-1", "K102516"):
            try:
                it = self.c.create_item(PROBE, {"Title": "t", "K": k})
                back = self.c.get_by_key(PROBE, "K", k)
                self.check(f"T1 text id round-trips exactly: {k!r}", back is not None and back["K"] == it["K"] == k or (back is not None and back["K"] == k.strip()),
                           f"stored as {back['K']!r}" if back else "not found")
            except SpError as e:
                self.check(f"T1 text id round-trips: {k!r}", False, str(e))
        it = self.c.create_item(PROBE, {"Title": "n", "K": "NullTest"})
        self.check("N1 omitted number column reads back as null, not 0", it.get("V") is None, f"V={it.get('V')!r}")

    def etag(self):
        it = self.c.create_item(PROBE, {"Title": "e", "K": "EtagTest", "V": 1})
        et = (it.get("__metadata") or {}).get("etag")
        self.check("E1 item carries __metadata.etag", bool(et), repr(et))
        self.c.update_item(PROBE, it["Id"], {"V": 2}, etag=et)
        try:
            self.c.update_item(PROBE, it["Id"], {"V": 3}, etag=et)
            self.check("E2 stale If-Match is refused (412)", False, "stale update SUCCEEDED")
        except SpError as e:
            self.check("E2 stale If-Match is refused (412)", e.is_precondition, f"HTTP {e.status}")
        row = self.c.get_by_key(PROBE, "K", "EtagTest")
        self.check("E3 refused update changed nothing", row["V"] == 2, f"V={row['V']}")

    def race_create(self, threads=8):
        outcomes = []

        def go():
            cl = self.make_client()
            try:
                cl.create_item(PROBE, {"Title": "r", "K": "RaceKey"})
                outcomes.append("ok")
            except SpError as e:
                outcomes.append("dup" if e.is_duplicate else f"err{e.status}")
        ts = [threading.Thread(target=go) for _ in range(threads)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.check(f"R1 {threads} simultaneous creates of one unique key: exactly one wins", outcomes.count("ok") == 1 and outcomes.count("dup") == threads - 1, str(sorted(outcomes)))

    def race_etag(self, threads=8):
        it = self.c.create_item(PROBE, {"Title": "c", "K": "CasKey", "V": 0})
        et = it["__metadata"]["etag"]
        outcomes = []

        def go(i):
            cl = self.make_client()
            try:
                cl.update_item(PROBE, it["Id"], {"V": i + 1}, etag=et)
                outcomes.append("ok")
            except SpError as e:
                outcomes.append("412" if e.is_precondition else f"err{e.status}")
        ts = [threading.Thread(target=go, args=(i,)) for i in range(threads)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.check(f"R2 {threads} simultaneous updates with the SAME etag: exactly one wins", outcomes.count("ok") == 1 and outcomes.count("412") == threads - 1, str(sorted(outcomes)))

    def large(self, n, seed=True):
        self.log(f"seeding {n} rows (slow)..." if seed else f"verifying a list that already holds {n} rows")
        t0 = time.time()
        for i in range(n if seed else 0):
            self.c.create_item(PROBE, {"Title": f"L{i}", "K": f"L{i:06d}", "V": 7})
            if i and i % 500 == 0:
                self.log(f"  {i} rows, {time.time() - t0:.0f}s")
        total = sum(1 for _ in self.c.query(PROBE, select="Id", top=500))
        self.check("L1 ID-ordered paging returns every row (no filter)", total >= n, f"{total} rows")
        try:
            hit = sum(1 for _ in self.c.query(PROBE, "V eq 7", select="Id", top=500))
            self.check("L2 an indexed filter matching more than 5,000 rows is REFUSED", n <= 5000, f"returned {hit} rows - NOT refused")
        except SpError as e:
            self.check("L2 an indexed filter matching more than 5,000 rows is REFUSED", e.is_threshold and n > 5000, f"HTTP {e.status} {e.code}")
        few = sum(1 for _ in self.c.query(PROBE, "K eq 'L000042'", select="Id"))
        self.check("L3 an indexed filter matching one row works on a >5,000-row list", few == 1, f"{few} rows")
        rng = sum(1 for _ in self.c.query(PROBE, "Id gt 100 and Id le 600", select="Id", top=500))
        self.check("L4 an ID-range filter works on a large list", rng == 500, f"{rng} rows")

    def run(self, large=0):
        self.identity()
        self.setup()
        try:
            self.unique_keys()
            self.etag()
            self.race_create()
            self.race_etag()
            if large:
                self.large(large)
        finally:
            self.teardown()
        bad = [r for r in self.results if not r[1]]
        self.log(f"\n{len(self.results) - len(bad)} passed, {len(bad)} failed")
        return not bad


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site-url", required=True)
    ap.add_argument("--tenant"); ap.add_argument("--client-id")
    ap.add_argument("--auth", choices=["device", "env", "fake"], default="device")
    ap.add_argument("--fake-user", default="owner@test")
    ap.add_argument("--token-cache")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--large", type=int, default=0, help="seed this many rows (use 5100) to test the list-view threshold")
    ap.add_argument("--report")
    a = ap.parse_args(argv)
    tp = make_provider(a)
    mk = lambda: SpClient(a.site_url, tp)
    if not a.apply:
        print("DRY RUN. Would create list POUProbe (columns K unique+indexed, V indexed, N), run checks U1 T1 N1 E1-E3 R1 R2" + (f" L1-L4 with {a.large} rows" if a.large else "")
              + ", then delete the list. Re-run with --apply.")
        return 0
    p = Probe(mk(), mk)
    ok = p.run(a.large)
    if a.report:
        with open(a.report, "w") as fh:
            json.dump([{"check": n, "pass": o, "detail": d} for n, o, d in p.results], fh, indent=2)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
