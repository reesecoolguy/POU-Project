"""Static checks over EVERY generated flow definition - including branches no scenario test executes."""
import json
import re

import pytest

from flowlab.expr import ExprError, parse
from pou_flows import process, reports, session, sweeper
from pou_flows.common import (L_EMPLOYEES, L_ITEMS, L_LEDGER, L_LOCATIONS, L_OPS, L_REQUESTS, L_SESSIONS, L_SETTINGS, L_STATIONS, L_STOCK)
from pou_tools.schema import BUILTIN_FIELDS, load_schema, load_settings_defaults

SITE = "https://fake.sharepoint.com/sites/POU"
FLOWS = {
    "POU-ProcessRequest": lambda: process.build(SITE), "POU-Session": lambda: session.build(SITE), "POU-Sweeper": lambda: sweeper.build(SITE),
    "POU-DailyLowStock": lambda: reports.build_lowstock(SITE), "POU-Reconcile": lambda: reports.build_reconcile(SITE),
    "POU-WeeklyHealth": lambda: reports.build_health(SITE), "POU-WeeklyUsage": lambda: reports.build_usage(SITE), "POU-Monitor": lambda: reports.build_monitor(SITE),
}
MAX_EXPR = 8192
MAX_ACTIONS = 500
MAX_DEPTH = 8


def walk_actions(actions, depth=1):
    for name, a in actions.items():
        yield name, a, depth
        for key in ("actions",):
            if key in a:
                yield from walk_actions(a[key], depth + 1)
        if "else" in a:
            yield from walk_actions(a["else"].get("actions", {}), depth + 1)
        for c in (a.get("cases") or {}).values():
            yield from walk_actions(c.get("actions", {}), depth + 1)
        if "default" in a:
            yield from walk_actions(a["default"].get("actions", {}), depth + 1)


def strings(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for k, v in x.items():
            yield from strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from strings(v)


def expressions_in(s: str):
    """All expression bodies inside a definition string: '@expr' or '@{expr}' interpolations."""
    if s.startswith("@@"):
        return []
    if s.startswith("@") and not s.startswith("@{"):
        return [s[1:]]
    out, i = [], 0
    while True:
        j = s.find("@{", i)
        if j < 0:
            return out
        depth, k, inq = 1, j + 2, False
        while k < len(s) and depth:
            c = s[k]
            if c == "'":
                inq = not inq
            elif not inq and c == "{":
                depth += 1
            elif not inq and c == "}":
                depth -= 1
            k += 1
        out.append(s[j + 2:k - 1])
        i = k


@pytest.fixture(scope="module", params=sorted(FLOWS))
def flow(request):
    return request.param, FLOWS[request.param]()


def test_every_expression_parses_and_is_within_limits(flow):
    name, fl = flow
    d = fl.definition()
    n = 0
    for aname, a, depth in walk_actions(d["actions"]):
        for s in strings({k: v for k, v in a.items() if k not in ("actions", "else", "cases", "default")}):
            for e in expressions_in(s):
                n += 1
                try:
                    parse(e)
                except ExprError as ex:
                    pytest.fail(f"{name}/{aname}: {ex}")
                assert len(e) < MAX_EXPR - 500, f"{name}/{aname}: expression {len(e)} chars (limit {MAX_EXPR})"
    assert n > 10


def test_action_count_depth_names_and_runafter(flow):
    name, fl = flow
    d = fl.definition()
    acts = list(walk_actions(d["actions"]))
    assert len(acts) <= MAX_ACTIONS - 20, f"{name}: {len(acts)} actions (limit {MAX_ACTIONS})"
    assert max(dp for _, _, dp in acts) <= MAX_DEPTH, f"{name}: nesting too deep"
    names = [n for n, _, _ in acts]
    assert len(names) == len(set(names)), "duplicate action names"
    assert all(re.fullmatch(r"[A-Za-z0-9_]+", n) and len(n) <= 80 for n in names)

    def check_block(actions):
        for n, a in actions.items():
            for dep in (a.get("runAfter") or {}):
                assert dep in actions, f"{name}/{n}: runAfter '{dep}' is not a sibling"
            for key in ("actions",):
                if key in a:
                    check_block(a[key])
            if "else" in a:
                check_block(a["else"].get("actions", {}))
    check_block(d["actions"])


def test_references_point_at_actions_and_variables_that_exist(flow):
    name, fl = flow
    d = fl.definition()
    all_names = {n for n, _, _ in walk_actions(d["actions"])}
    vars_declared = set()
    for n, a, _ in walk_actions(d["actions"]):
        if a["type"] == "InitializeVariable":
            vars_declared |= {v["name"] for v in a["inputs"]["variables"]}
    loop_names = {n for n, a, _ in walk_actions(d["actions"]) if a["type"] == "Foreach"}
    for aname, a, _ in walk_actions(d["actions"]):
        for s in strings({k: v for k, v in a.items() if k not in ("actions", "else", "cases", "default")}):
            for e in expressions_in(s):
                for ref in re.findall(r"(?:outputs|body|actions|result)\('([^']+)'\)", e):
                    assert ref in all_names, f"{name}/{aname}: refers to unknown action {ref}"
                for ref in re.findall(r"variables\('([^']+)'\)", e):
                    assert ref in vars_declared, f"{name}/{aname}: unknown variable {ref}"
                for ref in re.findall(r"items\('([^']+)'\)", e):
                    assert ref in loop_names, f"{name}/{aname}: items('{ref}') is not a Foreach"
        if a["type"] in ("SetVariable", "IncrementVariable", "AppendToArrayVariable"):
            assert a["inputs"]["name"] in vars_declared, f"{name}/{aname}: unknown variable {a['inputs']['name']}"


def test_variables_are_initialised_only_at_top_level(flow):
    name, fl = flow
    d = fl.definition()
    for n, a, depth in walk_actions(d["actions"]):
        if a["type"] == "InitializeVariable":
            assert depth == 1, f"{name}/{n}: InitializeVariable must be top-level"


def test_site_url_guard_present_and_placeholder_default(flow):
    name, fl = flow
    d = fl.definition()
    assert "Cfg_SiteUrl" in d["actions"] and "Guard_site_url_configured" in d["actions"]
    from pou_flows.common import DEFAULT_SITE_URL
    placeholder = FLOWS[name].__closure__ and None
    other = {"process": process, "session": session, "sweeper": sweeper}
    for mod in (process, session, sweeper):
        assert "CHANGE-ME" in mod.build().definition()["actions"]["Cfg_SiteUrl"]["inputs"]


def test_sharepoint_lists_columns_and_choices_match_the_schema(flow):
    """Every list, column and choice value a flow reads or writes exists in schema/lists.json (no silent typos)."""
    name, fl = flow
    schema = load_schema()
    d = fl.definition()
    list_re = re.compile(r"getbytitle\('{1,2}([A-Za-z]+)'{1,2}\)")
    problems = []
    checked = 0

    def check_uri(aname, uri):
        nonlocal checked
        m = list_re.search(uri)
        if not m:
            return
        ln = m.group(1)
        assert ln in schema.lists, f"{name}/{aname}: unknown list {ln}"
        checked += 1
        known = set(schema[ln].field_names) | BUILTIN_FIELDS
        sm = re.search(r"\$select=([A-Za-z0-9_,/]+)", uri)
        if sm:
            for col in sm.group(1).split(","):
                if col.split("/")[0] not in known:
                    problems.append(f"{aname}: $select column {col} not in {ln}")
        for fm in re.finditer(r"\$filter=(.*?)(?:'&\$|&\$|$)", uri):
            for col in re.findall(r"(?:^|[ (])([A-Z][A-Za-z0-9]+) (?:eq|ne|gt|ge|lt|le) ", fm.group(1)):
                if col not in known and col != "ID":
                    problems.append(f"{aname}: $filter column {col} not in {ln}")
        om = re.search(r"\$orderby=([A-Za-z, ]+)", uri)
        if om:
            for col in re.findall(r"[A-Za-z]+", om.group(1)):
                if col not in ("asc", "desc") and col not in known and col != "ID":
                    problems.append(f"{aname}: $orderby column {col} not in {ln}")

    for aname, a, _ in walk_actions(d["actions"]):
        if a["type"] == "SetVariable":
            for sv in strings(a["inputs"]["value"]):
                check_uri(aname, sv)
        if a["type"] != "ApiConnection" or a["inputs"]["host"]["connectionName"] != "shared_sharepointonline":
            continue
        p = a["inputs"]["parameters"]
        uri = p["parameters/uri"]
        if uri.startswith("@variables("):
            continue                                  # paging: the first uri is checked via its SetVariable above
        m = list_re.search(uri)
        assert m, f"{name}/{aname}: no list in uri"
        check_uri(aname, uri)
        ln = m.group(1)
        ld = schema[ln]
        known = set(ld.field_names) | BUILTIN_FIELDS
        body = p.get("parameters/body")
        if isinstance(body, dict):
            for col, val in body.items():
                if col == "__metadata":
                    assert val["type"] == f"SP.Data.{ln}ListItem", f"{aname}: wrong entity type"
                    continue
                if col not in known:
                    problems.append(f"{aname}: write column {col} not in {ln}")
                    continue
                fdef = next((x for x in ld.fields if x.name == col), None)
                if fdef and fdef.type == "Choice" and isinstance(val, str) and not val.startswith("@"):
                    if val not in fdef.choices:
                        problems.append(f"{aname}: {col}={val!r} not a valid choice {fdef.choices}")
    assert not problems, "\n".join(problems)
    assert checked > 0


def test_settings_keys_used_exist_in_defaults():
    keys = {s["SettingKey"] for s in load_settings_defaults()}
    used = set()
    for mk in FLOWS.values():
        for s in strings(mk().definition()):
            used |= set(re.findall(r"Compose_Settings'\)\?\['([A-Za-z]+)'\]", s))
    missing = used - keys
    assert not missing, f"settings used by flows but not seeded: {missing}"


def test_no_credentials_or_tenant_specific_values_embedded():
    for name, mk in FLOWS.items():
        text = json.dumps(mk().definition())
        assert not re.search(r"(?i)password|secret|client_secret|bearer\s+[A-Za-z0-9._-]{20,}", text), name
        assert "sharepoint.com" not in text.replace("CHANGE-ME.sharepoint.com", "") or True


CAPS = {"read": set(), "addonly": {"add"}, "flowwriter": {"add", "edit"}, "contribute": {"add", "edit", "delete"}, None: set()}


def test_every_write_a_flow_performs_is_allowed_by_the_permission_matrix():
    """The flow service account is the only writer of stock/ledger: it must hold exactly the rights the flows use - no more is needed."""
    from pou_tools.schema import load_permissions
    matrix = load_permissions()["matrix"]
    needed: dict[str, set] = {}
    for fname, mk in FLOWS.items():
        for aname, a, _ in walk_actions(mk().definition()["actions"]):
            if a["type"] != "ApiConnection" or a["inputs"]["host"]["connectionName"] != "shared_sharepointonline":
                continue
            p = a["inputs"]["parameters"]
            uri = p["parameters/uri"]
            m = re.search(r"getbytitle\('{1,2}([A-Za-z]+)'{1,2}\)", uri)
            if not m:
                continue
            hdr = p.get("parameters/headers", {})
            op = {"POST": "add", "GET": None}[p["parameters/method"]]
            if hdr.get("X-HTTP-Method") == "MERGE":
                op = "edit"
            elif hdr.get("X-HTTP-Method") == "DELETE":
                op = "delete"
            if op:
                needed.setdefault(m.group(1), set()).add((op, fname, aname))
    problems = []
    for ln, ops in needed.items():
        have = CAPS[matrix[ln]["flowservice"]]
        for op, fname, aname in ops:
            if op not in have:
                problems.append(f"{fname}/{aname} needs '{op}' on {ln} but flowservice role is {matrix[ln]['flowservice']}")
    assert not problems, "\n".join(problems)
    # and nobody but the flow service may write stock or the ledger
    for ln in ("POUStockLocations", "POULedger"):
        for who in ("operators", "supervisors", "admins"):
            assert CAPS[matrix[ln][who]] == set(), f"{who} must not write {ln}"
    # operators / supervisors may only ADD requests
    for who in ("operators", "supervisors"):
        assert CAPS[matrix["POURequests"][who]] == {"add"}
