import json
import pytest
from pou_tools import masks, keys
from pou_tools.schema import load_schema, SchemaError, validate_schema, Schema, ListDef, Field
from pou_tools.spclient import SpError
from pou_tools.provision import provision
from conftest import client_for, SITE_OWNER


def test_builtin_read_mask_matches_documented_values():
    s = masks.split(masks.READ_MASK)
    assert (s["Low"], s["High"]) == (138612833, 176)


def test_schema_loads_and_is_consistent(schema):
    assert len(schema.lists) == 10
    for ld in schema.lists.values():
        assert len(ld.indexed_names) <= 20
        for f in ld.fields:
            assert f.name.isalnum() and len(f.name) <= 32
    # keys that the protocol relies on are unique+indexed
    assert schema["POULedger"].field("LedgerKey").unique
    assert schema["POULedger"].field("RequestID").unique
    assert schema["POURequests"].field("RequestID").unique
    assert schema["POUStockLocations"].field("StockKey").unique
    assert schema["POUItems"].field("ItemID").unique


def test_schema_validator_rejects_bad_names():
    bad = Schema("x", {"Bad_List": ListDef("Bad_List", "", "L", [Field("ID", "ID", "Text")])}, {})
    with pytest.raises(SchemaError):
        validate_schema(bad)


def test_schema_xml_contains_unique_and_index(schema):
    x = schema["POULedger"].field("LedgerKey").schema_xml()
    assert 'EnforceUniqueValues="TRUE"' in x and 'Indexed="TRUE"' in x and 'Name="LedgerKey"' in x
    c = schema["POURequests"].field("RequestStatus").schema_xml()
    assert "<CHOICE>Pending</CHOICE>" in c and "<Default>Pending</Default>" in c


def test_keys():
    assert keys.stock_key(" k102516 ", "2-a") == "K102516|2-A"
    assert keys.normalize_id("*K100593*") == "K100593"
    assert keys.to_text(100416) == "100416"
    assert keys.to_text(100416.0) == "100416"
    with pytest.raises(keys.KeyError_):
        keys.stock_key("A|B", "1")


def test_dry_run_changes_nothing(fake_http, schema, perms):
    f, url = fake_http
    admin = client_for(f, SITE_OWNER, url)
    before = f.request_count
    rep = provision(admin, schema, perms, apply=False, log=lambda *a: None)
    assert not f.lists
    assert rep.count("PLANNED") > 100
    assert all(r["method"] == "GET" for r in f.request_log)


def test_apply_creates_everything_and_rerun_is_noop(fake_http, schema, perms):
    f, url = fake_http
    admin = client_for(f, SITE_OWNER, url)
    rep = provision(admin, schema, perms, apply=True, log=lambda *a: None)
    assert rep.count("ERROR") == 0, [a.line() for a in rep.actions if a.status == "ERROR"]
    assert set(f.lists) == set(schema.lists)
    # columns / indexes / uniqueness
    led = f.lists["POULedger"]
    assert led.fields["LedgerKey"].unique and led.fields["LedgerKey"].indexed
    assert led.fields["OccurredUtc"].indexed
    assert not led.fields["Title"].required
    assert led.props["EnableVersioning"] is True
    # settings seeded
    assert f.count("POUSettings") == 35
    n_before = len(f.request_log)
    rep2 = provision(admin, schema, perms, apply=True, log=lambda *a: None)
    assert rep2.count("PLANNED") == 0 and rep2.count("DONE") == 0, [a.line() for a in rep2.actions if a.status in ("PLANNED", "DONE")]
    assert rep2.count("ERROR") == 0
    assert f.count("POUSettings") == 35
    posts = [r for r in f.request_log[n_before:] if r["method"] != "GET"]
    assert posts == []


def test_rerun_does_not_overwrite_changed_setting(fake_http, schema, perms):
    f, url = fake_http
    admin = client_for(f, SITE_OWNER, url)
    provision(admin, schema, perms, apply=True, log=lambda *a: None)
    row = admin.get_by_key("POUSettings", "SettingKey", "MaxAddQty")
    admin.update_item("POUSettings", row["Id"], {"SettingValue": "250"})
    provision(admin, schema, perms, apply=True, log=lambda *a: None)
    assert admin.get_by_key("POUSettings", "SettingKey", "MaxAddQty")["SettingValue"] == "250"


def test_rerun_repairs_safe_drift(fake_http, schema, perms):
    f, url = fake_http
    admin = client_for(f, SITE_OWNER, url)
    provision(admin, schema, perms, apply=True, log=lambda *a: None)
    f.lists["POUItems"].fields["Manufacturer"].indexed = True  # extra index is fine
    f.lists["POULedger"].fields["OccurredUtc"].indexed = False
    rep = provision(admin, schema, perms, apply=True, log=lambda *a: None)
    assert f.lists["POULedger"].fields["OccurredUtc"].indexed
    assert any(a.kind == "UPDATE_FIELD" and a.status == "DONE" for a in rep.actions)


def test_type_drift_is_reported_not_changed(fake_http, schema, perms):
    f, url = fake_http
    admin = client_for(f, SITE_OWNER, url)
    provision(admin, schema, perms, apply=True, log=lambda *a: None)
    f.lists["POUItems"].fields["Priority"].type = "Text"
    rep = provision(admin, schema, perms, apply=True, log=lambda *a: None)
    assert any(a.status == "DRIFT" and a.target == "POUItems.Priority" for a in rep.actions)
    assert f.lists["POUItems"].fields["Priority"].type == "Text"


# ------------------------------------------------------------------ permissions are real, not cosmetic
def _c(f, url, upn):
    return client_for(f, upn, url)


def test_operator_cannot_write_stock_or_ledger_or_read_employees(provisioned):
    f, url = provisioned
    svc = _c(f, url, "svc@test")
    svc.create_item("POUStockLocations", {"StockKey": "A|1", "ItemID": "A", "LocationCode": "1", "OnHandQty": 5})
    op = _c(f, url, "station1@test")
    row = op.get_by_key("POUStockLocations", "StockKey", "A|1")      # read allowed
    assert row["OnHandQty"] == 5
    with pytest.raises(SpError) as e:
        op.update_item("POUStockLocations", row["Id"], {"OnHandQty": 999})
    assert e.value.status == 403
    with pytest.raises(SpError) as e:
        op.create_item("POULedger", {"LedgerKey": "x", "RequestID": "y", "LedgerType": "ISSUE"})
    assert e.value.status == 403
    with pytest.raises(SpError) as e:
        list(op.query("POUEmployees"))
    assert e.value.status == 403
    with pytest.raises(SpError) as e:
        list(op.query("POUSessions"))
    assert e.value.status == 403
    with pytest.raises(SpError) as e:
        op.delete_item("POUStockLocations", row["Id"])
    assert e.value.status == 403


def test_operator_can_add_request_but_not_edit_or_delete_it(provisioned):
    f, url = provisioned
    op = _c(f, url, "station1@test")
    r = op.create_item("POURequests", {"RequestID": "R1", "RequestType": "ISSUE", "StockKey": "A|1", "Quantity": 1})
    # server stamps the author - client cannot choose it
    row = op.get_by_key("POURequests", "RequestID", "R1", select="Id,RequestStatus,Author/EMail")
    got = list(op.query("POURequests", "RequestID eq 'R1'", select="Id,Author/EMail", expand="Author"))[0]
    assert got["Author"]["EMail"] == "station1@test"
    with pytest.raises(SpError) as e:
        op.update_item("POURequests", row["Id"], {"RequestStatus": "Succeeded"})
    assert e.value.status == 403
    with pytest.raises(SpError) as e:
        op.delete_item("POURequests", row["Id"])
    assert e.value.status == 403


def test_duplicate_request_id_rejected_by_unique_constraint(provisioned):
    f, url = provisioned
    op = _c(f, url, "station1@test")
    op.create_item("POURequests", {"RequestID": "R1", "RequestType": "ISSUE"})
    with pytest.raises(SpError) as e:
        op.create_item("POURequests", {"RequestID": "r1", "RequestType": "ISSUE"})   # case-insensitive
    assert e.value.is_duplicate


def test_flow_service_can_edit_stock_but_not_delete_ledger(provisioned):
    f, url = provisioned
    svc = _c(f, url, "svc@test")
    r = svc.create_item("POULedger", {"LedgerKey": "A|1#1", "RequestID": "R1", "LedgerType": "ISSUE"})
    svc.update_item("POULedger", r["Id"], {"PostingState": "Posted"})
    with pytest.raises(SpError) as e:
        svc.delete_item("POULedger", r["Id"])
    assert e.value.status == 403


def test_admin_cannot_edit_stock_or_ledger_but_can_edit_settings(provisioned):
    f, url = provisioned
    svc = _c(f, url, "svc@test")
    svc.create_item("POUStockLocations", {"StockKey": "A|1", "ItemID": "A", "LocationCode": "1", "OnHandQty": 5})
    ad = _c(f, url, "admin@test")
    row = ad.get_by_key("POUStockLocations", "StockKey", "A|1")
    with pytest.raises(SpError) as e:
        ad.update_item("POUStockLocations", row["Id"], {"OnHandQty": 50})
    assert e.value.status == 403
    s = ad.get_by_key("POUSettings", "SettingKey", "MaxAddQty")
    ad.update_item("POUSettings", s["Id"], {"SettingValue": "400"})


def test_operator_cannot_change_settings_and_supervisor_can_read_employees(provisioned):
    f, url = provisioned
    op = _c(f, url, "station1@test")
    s = op.get_by_key("POUSettings", "SettingKey", "MaxAddQty")
    with pytest.raises(SpError) as e:
        op.update_item("POUSettings", s["Id"], {"SettingValue": "99999"})
    assert e.value.status == 403
    sup = _c(f, url, "sup@test")
    list(sup.query("POUEmployees"))          # allowed
    with pytest.raises(SpError):
        sup.create_item("POUEmployees", {"BadgeID": "1", "EmployeeName": "x"})


def test_unknown_user_has_no_access(provisioned):
    f, url = provisioned
    rnd = _c(f, url, "random@test")
    with pytest.raises(SpError) as e:
        list(rnd.query("POUItems"))
    assert e.value.status == 403
