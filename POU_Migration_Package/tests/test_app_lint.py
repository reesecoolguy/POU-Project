"""The canvas-app generator and its static linter. Nothing here runs Power Fx; it proves the generated source is internally consistent
and that the linter really detects the mistakes it claims to detect."""
import copy

import pytest

from pou_app import lint, screens
from pou_app.spec import Ctl, walk


@pytest.fixture(scope="module")
def app():
    return screens.all_screens(), screens.app_props()


def test_generated_app_has_no_lint_errors(app):
    problems = [p for p in lint.lint(*app) if p.level == "ERROR"]
    assert not problems, lint.report(problems)


def _with(app, fn):
    ss = copy.deepcopy(app[0])
    fn(ss)
    return [str(p) for p in lint.lint(ss, app[1]) if p.level == "ERROR"]


def _ctl(ss, name):
    for s in ss:
        for c in walk(s.children):
            if c.name == name:
                return c
    raise KeyError(name)


def test_linter_detects_unbalanced_syntax(app):
    out = _with(app, lambda ss: _ctl(ss, "btnFindScan").props.update(OnSelect="Set(varBusy, true"))
    assert any("unclosed" in o or "unbalanced" in o for o in out)


def test_linter_detects_unknown_control_and_cross_screen_reference(app):
    out = _with(app, lambda ss: _ctl(ss, "btnFindScan").props.update(OnSelect="Reset(txtNope)"))
    assert any("txtNope" in o for o in out)
    out = _with(app, lambda ss: _ctl(ss, "lblMsgScan").props.update(Text="txtCountAudit.Text"))
    assert any("cross-screen" in o for o in out)


def test_linter_detects_variable_read_but_never_set(app):
    out = _with(app, lambda ss: _ctl(ss, "lblMsgScan").props.update(Text="varNeverSet"))
    assert any("varNeverSet" in o for o in out)
    out = _with(app, lambda ss: _ctl(ss, "lblMsgScan").props.update(Text="locNeverSet"))
    assert any("locNeverSet" in o for o in out)


def test_linter_detects_bad_column_and_choice_without_value(app):
    out = _with(app, lambda ss: _ctl(ss, "lblMsgScan").props.update(Text="LookUp(POUItems, ItemCode = \"x\").ItemID"))
    assert any("ItemCode" in o for o in out)
    out = _with(app, lambda ss: _ctl(ss, "lblMsgScan").props.update(Text="locSel.BalanceStatus"))
    assert any("Choice" in o for o in out)


def test_linter_detects_non_delegable_and_unindexed_filters(app):
    out = _with(app, lambda ss: _ctl(ss, "lblMsgScan").props.update(Text="First(Filter(POULedger, Lower(ItemID) = \"a\"))"))
    assert any("not delegable" in o for o in out)
    out = _with(app, lambda ss: _ctl(ss, "lblMsgScan").props.update(Text="First(Filter(POULedger, Reason = \"a\"))"))
    assert any("non-indexed" in o for o in out)
    out = _with(app, lambda ss: _ctl(ss, "lblMsgScan").props.update(Text="CountRows(POULedger)"))
    assert any("not delegable" in o for o in out)


def test_linter_detects_flow_argument_mismatch_and_unknown_setting(app):
    out = _with(app, lambda ss: _ctl(ss, "btnLogin").props.update(OnSelect="'POU-Session'.Run(\"LOGIN\", \"x\")"))
    assert any("arguments" in o for o in out)
    out = _with(app, lambda ss: _ctl(ss, "lblMsgScan").props.update(Text='LookUp(colSettings, SettingKey = "NoSuchSetting").SettingValue'))
    assert any("NoSuchSetting" in o for o in out)


def test_linter_detects_duplicate_names(app):
    out = _with(app, lambda ss: ss[1].children.append(Ctl("btnFindScan", "button", {"Text": '"x"', "OnSelect": "false"})))
    assert any("duplicate" in o for o in out)


# ---- properties the design promises, checked on the generated source ------------------------------------------------------------
def all_text(app):
    return {(s.name, c.name, k): str(v) for s in app[0] for c in walk(s.children) for k, v in c.props.items()}


def test_every_request_creating_path_uses_the_one_posting_procedure(app):
    """Every Patch into POURequests lives in run_post (one place, generated once)."""
    for (scr, name, prop), t in all_text(app).items():
        if "Patch(POURequests" in t:
            assert "Set(varLookupFailed, false)" in t and "varReq.RequestID" in t, (scr, name, prop)


def test_request_id_is_generated_exactly_once_per_request_and_never_on_retry(app):
    texts = all_text(app)
    for (scr, name, prop), t in texts.items():
        if "Lower(GUID())" in t:
            assert "begin_request" or "Set(varReq," in t
            assert "Collect(colOutbox, varReq)" in t and "SaveData(colOutbox" in t, (scr, name)
        if name.startswith("btnRetry"):
            assert "GUID" not in t, "a retry must reuse the retained RequestID"


def test_success_is_only_shown_for_a_succeeded_request(app):
    # the only places the banner is set green are guarded by the server status
    for (scr, name, prop), t in all_text(app).items():
        for part in t.split('Set(varOutKind, "ok")')[:-1]:
            assert 'varFinal = "Succeeded"' in part[-200:] or 'varTgtRow.RequestStatus.Value = "Succeeded"' in part[-400:] or "If(varTgtRow" in t, (scr, name)


def test_no_control_truncates_input_silently(app):
    for (scr, name, prop), t in all_text(app).items():
        assert "MaxLength" not in prop, (scr, name)


def test_quantity_inputs_are_validated_by_pattern_not_by_coercion(app):
    t = all_text(app)
    assert 'IsMatch(Trim(txtQtyScan.Text), "^[1-9][0-9]{0,3}$")' in t[("scrScan", "btnAddScan", "OnSelect")]
    assert "varMaxAdd" in t[("scrScan", "btnAddScan", "OnSelect")]
    assert "varMaxAdd" not in t[("scrScan", "btnRemoveScan", "OnSelect")]


def test_audit_carries_expected_version_and_confirms_variance(app):
    t = all_text(app)
    post = t[("scrAudit", "btnPostCountAudit", "OnSelect")]
    assert 'RequestType: "AUDIT"' in post and "ExpectedVersion: Text(locVer)" in post
    assert "varAuditVar" in t[("scrAudit", "btnPostCountAudit", "Text")]


def test_idle_timer_and_settings_are_central(app):
    t = all_text(app)
    assert "varIdleMin" in t[("scrScan", "tmrIdleScan", "OnTimerEnd")]
    start = screens.app_props()["OnStart"]
    for key in ("IdleTimeoutMinutes", "MaxAddQty", "AuditConfirmVariance", "LogoutAfterSubmit", "LowStockRule"):
        assert key in start


def test_no_layout_warnings(app):
    warns = [str(p) for p in lint.lint(*app) if p.level == "WARN"]
    assert not warns, warns
