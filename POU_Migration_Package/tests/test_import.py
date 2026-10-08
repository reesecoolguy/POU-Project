import csv
import shutil
from pathlib import Path

import pytest

from pou_tools.extract import extract
from pou_tools.import_data import ImportRefused, run_all, run_stage, STAGES
from pou_tools.transform import transform, write_outputs
from pou_tools.verify_import import verify
from pou_tools.schema import load_schema
from conftest import client_for, SITE_OWNER

REAL = Path(__file__).resolve().parent.parent.parent / "POU_Inventory_Pilot Test _With_Badge.xlsm"
pytestmark = pytest.mark.skipif(not REAL.exists(), reason="real workbook not present")


@pytest.fixture(scope="module")
def import_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("mig")
    write_outputs(transform(extract(REAL)), d)
    return d / "import"


def test_dry_run_writes_nothing_then_apply_then_rerun_is_noop(provisioned, import_dir):
    f, url = provisioned
    owner = client_for(f, SITE_OWNER, url)
    schema = load_schema()
    before = {k: f.count(k) for k in ("POUItems", "POUStockLocations", "POULedger", "POURequests", "POULocations", "POUEmployees")}
    res = run_all(owner, schema, import_dir, [s[0] for s in STAGES], apply=False, log=lambda *a: None)
    assert {k: f.count(k) for k in before} == before
    assert sum(r.would_create for r in res) == 22 + 7 + 251 + 254 + 26 + 252

    res = run_all(owner, schema, import_dir, [s[0] for s in STAGES], apply=True, log=lambda *a: None)
    assert all(not r.errors for r in res), [r.errors[:2] for r in res if r.errors]
    assert f.count("POUItems") == 251 and f.count("POUStockLocations") == 254 and f.count("POULedger") == 26
    assert f.count("POURequests") == 252 and f.count("POULocations") == 22 and f.count("POUEmployees") == 7

    # the three repeated IDs are two stock records each under one item
    for k in ("K102516", "K102517", "K13471"):
        assert len(owner.get_by_key("POUItems", "ItemID", k) and list(owner.query("POUStockLocations", f"ItemID eq '{k}'"))) == 2

    # NOTHING wrote a balance: every stock record is NoBalance, OnHand blank, version 0
    for r in f.items_of("POUStockLocations"):
        assert r["OnHandQty"] is None and r["BalanceStatus"] == "NoBalance" and r["StockVersion"] == 0
    # legacy rows are history only
    for r in f.items_of("POULedger"):
        assert r["Origin"] == "Legacy" and r["AffectsBalance"] is False and r["SeqNo"] is None
    # text IDs, numeric-looking IDs stay text
    assert owner.get_by_key("POUItems", "ItemID", "100416")["ItemID"] == "100416"

    n = len(f.request_log)
    res2 = run_all(owner, schema, import_dir, [s[0] for s in STAGES], apply=True, log=lambda *a: None)
    assert sum(r.created for r in res2) == 0 and all(r.exists_same == r.total for r in res2)
    assert [r for r in f.request_log[n:] if r["method"] != "GET"] == []


def test_resumes_after_partial_import(provisioned, import_dir):
    f, url = provisioned
    owner = client_for(f, SITE_OWNER, url)
    schema = load_schema()
    run_stage(owner, schema, "items", import_dir / "03_items.csv", "POUItems", "ItemID", apply=True)
    # simulate interruption: delete half the items
    for r in list(f.lists["POUItems"].items.values())[:100]:
        del f.lists["POUItems"].items[r["id"]]
    r = run_stage(owner, schema, "items", import_dir / "03_items.csv", "POUItems", "ItemID", apply=True)
    assert r.created == 100 and r.exists_same == 151 and f.count("POUItems") == 251


def test_existing_different_row_is_reported_not_overwritten(provisioned, import_dir):
    f, url = provisioned
    owner = client_for(f, SITE_OWNER, url)
    schema = load_schema()
    run_stage(owner, schema, "items", import_dir / "03_items.csv", "POUItems", "ItemID", apply=True)
    it = owner.get_by_key("POUItems", "ItemID", "K100593")
    owner.update_item("POUItems", it["Id"], {"ItemName": "EDITED BY A PERSON"})
    r = run_stage(owner, schema, "items", import_dir / "03_items.csv", "POUItems", "ItemID", apply=True)
    assert r.exists_different == [{"key": "K100593", "fields": ["ItemName"]}]
    assert owner.get_by_key("POUItems", "ItemID", "K100593")["ItemName"] == "EDITED BY A PERSON"


def test_importer_refuses_balance_columns_and_non_legacy_ledger(provisioned, import_dir, tmp_path):
    f, url = provisioned
    owner = client_for(f, SITE_OWNER, url)
    schema = load_schema()
    bad = tmp_path / "stock.csv"
    rows = list(csv.DictReader(open(import_dir / "04_stock_locations.csv")))
    with open(bad, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) + ["OnHandQty"])
        w.writeheader()
        for r in rows[:3]:
            w.writerow({**r, "OnHandQty": "5"})
    with pytest.raises(ImportRefused):
        run_stage(owner, schema, "stock", bad, "POUStockLocations", "StockKey", apply=True)
    led = list(csv.DictReader(open(import_dir / "05_ledger_legacy.csv")))
    bad2 = tmp_path / "ledger.csv"
    with open(bad2, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(led[0].keys()))
        w.writeheader()
        r = dict(led[0]); r["AffectsBalance"] = "TRUE"
        w.writerow(r)
    with pytest.raises(ImportRefused):
        run_stage(owner, schema, "ledger", bad2, "POULedger", "LedgerKey", apply=True)


def test_operator_cannot_run_the_import(provisioned, import_dir):
    f, url = provisioned
    schema = load_schema()
    op = client_for(f, "station1@test", url)
    r = run_stage(op, schema, "locations", import_dir / "01_locations.csv", "POULocations", "LocationCode", apply=True)
    assert len(r.errors) == 22 and "403" in r.errors[0]["error"]


def test_post_import_verification_states(provisioned, import_dir):
    f, url = provisioned
    owner = client_for(f, SITE_OWNER, url)
    schema = load_schema()
    run_all(owner, schema, import_dir, [s[0] for s in STAGES], apply=True, log=lambda *a: None)
    counts, rows, st, bad = verify(owner, import_dir)
    # before the flow posts the openings: pending, not failed; blanks are OK_NO_BALANCE
    assert st["PENDING_OPENING"] == 252 and st["OK_NO_BALANCE"] == 2 and not bad
    # simulate what the flow does for ONE opening, correctly
    sk = "K100593|1-A"
    stock = owner.get_by_key("POUStockLocations", "StockKey", sk)
    q = int([r for r in csv.DictReader(open(import_dir / "06_opening_balance_requests.csv")) if r["StockKey"] == sk][0]["Quantity"])
    svc = client_for(f, "svc@test", url)
    svc.create_item("POULedger", {"LedgerKey": sk + "#1", "RequestID": "OPEN-" + sk, "LedgerType": "OPENING", "StockKey": sk, "SeqNo": 1, "QtyAfter": q, "PostingState": "Posted"})
    svc.update_item("POUStockLocations", stock["Id"], {"OnHandQty": q, "StockVersion": 1, "BalanceStatus": "Unverified"})
    counts, rows, st, bad = verify(owner, import_dir)
    assert st["OK"] == 1 and st["PENDING_OPENING"] == 251 and not bad
    # now corrupt it: balance differs from the workbook figure -> MISMATCH is detected
    stock = owner.get_by_key("POUStockLocations", "StockKey", sk)
    svc.update_item("POUStockLocations", stock["Id"], {"OnHandQty": q + 1})
    counts, rows, st, bad = verify(owner, import_dir)
    assert st["MISMATCH"] == 1 and bad
    # a blank-source record that gained a balance outside the protocol is flagged too
    blank = owner.get_by_key("POUStockLocations", "StockKey", "K102516|2-A")
    svc.update_item("POUStockLocations", blank["Id"], {"OnHandQty": 0})
    counts, rows, st, bad = verify(owner, import_dir)
    assert st["MISMATCH_UNEXPECTED_BALANCE"] == 1
