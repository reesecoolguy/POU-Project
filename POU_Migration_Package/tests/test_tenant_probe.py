"""The tenant probe and permission audit are themselves tested against the in-memory SharePoint model."""
from conftest import SITE_OWNER, client_for
from pou_tools.permission_audit import audit, expected_for
from pou_tools.tenant_probe import Probe


def test_probe_passes_against_the_model(fake_http):
    f, url = fake_http
    mk = lambda: client_for(f, SITE_OWNER, url)
    p = Probe(mk(), mk, log=lambda *a: None)
    assert p.run(large=0), [r for r in p.results if not r[1]]
    assert f.lists.get("POUProbe") is None            # cleaned up
    assert len(p.results) >= 14


def test_probe_large_list_threshold_checks(fake_http):
    f, url = fake_http
    mk = lambda: client_for(f, SITE_OWNER, url)
    p = Probe(mk(), mk, log=lambda *a: None)
    p.setup()
    f.bulk_load("POUProbe", [{"Title": f"L{i}", "K": f"L{i:06d}", "V": 7} for i in range(5100)])
    p.large(5100, seed=False)          # the seeding loop is skipped (bulk_load above)
    assert all(ok for _, ok, _ in p.results), p.results
    p.teardown()


def test_permission_audit_matches_the_matrix_for_every_group(provisioned, perms):
    f, url = provisioned
    for group, upn in (("operators", "station1@test"), ("supervisors", "sup@test"), ("admins", "admin@test"), ("flowservice", "svc@test")):
        res = audit(client_for(f, upn, url), perms, group)
        bad = [r for r in res if not r["ok"]]
        assert not bad, (group, bad)


def test_permission_audit_detects_a_wrong_group(provisioned, perms):
    f, url = provisioned
    res = audit(client_for(f, "station1@test", url), perms, "supervisors")       # an operator claiming to be a supervisor
    assert any(not r["ok"] for r in res)
    assert expected_for(perms, "operators", "POURequests") == (True, True, False, False)
    assert expected_for(perms, "flowservice", "POULedger") == (True, True, True, False)
    assert expected_for(perms, "operators", "POUEmployees") == (False, False, False, False)
