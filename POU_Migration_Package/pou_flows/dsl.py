"""Tiny builder DSL for workflow definitions. Everything is plain dicts so the output is the exact JSON
that Power Automate stores for a cloud flow (properties.definition)."""
from __future__ import annotations

import json
from typing import Any

SCHEMA = "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#"
ALL = ["Succeeded", "Failed", "Skipped", "TimedOut"]
CONTAINERS = {"Scope", "If", "Foreach", "Until", "Switch"}
SP_CONN = "shared_sharepointonline"
MAIL_CONN = "shared_office365"
LIST_TYPE = lambda ln: f"SP.Data.{ln}ListItem"


class Ex(str):
    """Raw expression fragment (no leading @)."""


def lit(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def r(x) -> str:
    """Render a Python value as a WDL expression argument."""
    if isinstance(x, Ex):
        return str(x)
    if isinstance(x, str) and x.startswith("@") and not x.startswith("@@") and not x.startswith("@{"):
        return x[1:]          # already an '@expr' string produced by cat()/X()
    if x is None:
        return "null"
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, (int, float)):
        return str(x)
    return lit(x)


def cat(*parts) -> str:
    """'@concat(...)' - plain str parts are literals, Ex parts are expressions."""
    return "@concat(" + ", ".join(r(p) for p in parts) + ")"


def X(expr) -> str:
    """Expression string. Idempotent: an '@...' string produced by cat()/X() is returned unchanged (avoids '@@' = literal '@')."""
    if isinstance(expr, str) and not isinstance(expr, Ex) and expr.startswith("@"):
        return expr
    return "@" + str(expr)


def qv(x) -> Ex:
    """OData string value, escaped for use inside '...' within a URL: doubles quotes, then URL-encodes."""
    return Ex(f"uriComponent(replace(string({r(x)}), '''', ''''''))")


def v(name) -> Ex: return Ex(f"variables('{name}')")
def o(name) -> Ex: return Ex(f"outputs('{name}')")
def b(name) -> Ex: return Ex(f"body('{name}')")
def f(fn, *args) -> Ex: return Ex(f"{fn}({', '.join(r(a) for a in args)})")
def eq(a, c) -> Ex: return f("equals", a, c)
def and_(*a) -> Ex: return f("and", *a)
def or_(*a) -> Ex: return f("or", *a)
def not_(a) -> Ex: return f("not", a)
def if_(c, a, c2) -> Ex: return f("if", c, a, c2)
def coalesce(*a) -> Ex: return f("coalesce", *a)
def is_null(a) -> Ex: return f("equals", a, None)
def nz(a) -> Ex: return not_(f("empty", a))
def stat(name) -> Ex: return Ex(f"actions('{name}')?['status']")
def ok(name) -> Ex: return eq(stat(name), "Succeeded")


def first_nonempty(exprs: list) -> Ex:
    """Left-to-right first non-empty string among expressions (each yields '' when not applicable)."""
    if not exprs:
        return Ex("''")
    e = exprs[-1]
    for x in reversed(exprs[:-1]):
        e = Ex(f"if(empty({x}), {e}, {x})")
    return Ex(str(e))


def cond_true(expr) -> dict:
    """Designer-style condition object for any boolean expression."""
    return {"equals": [X(expr), True]}


def norm(x):
    """Replace Ex fragments by '@expr' strings, recursively (so action dicts are pure JSON)."""
    if isinstance(x, Ex):
        return "@" + str(x)
    if isinstance(x, dict):
        return {k: norm(v_) for k, v_ in x.items()}
    if isinstance(x, list):
        return [norm(v_) for v_ in x]
    return x


class Block:
    """Ordered actions with automatic runAfter chaining."""

    def __init__(self, flow: "Flow"):
        self.flow = flow
        self.actions: dict[str, dict] = {}
        self.last: str | None = None
        self.last_type: str | None = None

    def add(self, name: str, action: dict, after: dict | None = None, always: bool = False) -> str:
        self.flow.register(name)
        if after is not None:
            ra = after
        elif self.last is None:
            ra = {}
        elif always or self.last_type in CONTAINERS:
            # A step that follows a container (scope / condition / loop) runs whatever the container reports: a failure that was
            # handled INSIDE it must not silently skip the rest of the chain. Safety comes from variable guards, not from run-after.
            ra = {self.last: list(ALL)}
        else:
            ra = {self.last: ["Succeeded"]}
        action = norm(dict(action))
        action["runAfter"] = ra
        self.actions[name] = action
        self.last = name
        self.last_type = action["type"]
        return name

    # ---- primitives -------------------------------------------------------------------------
    def compose(self, name, value, **kw): return self.add(name, {"type": "Compose", "inputs": value}, **kw)

    def init_var(self, name, typ, value, **kw):
        return self.add(f"Init_{name}", {"type": "InitializeVariable", "inputs": {"variables": [{"name": name, "type": typ, "value": value}]}}, **kw)

    def set_var(self, var, value, name=None, **kw):
        return self.add(name or f"Set_{var}_{self.flow.next_id()}", {"type": "SetVariable", "inputs": {"name": var, "value": value}}, **kw)

    def inc_var(self, var, n=1, name=None, **kw):
        return self.add(name or f"Inc_{var}_{self.flow.next_id()}", {"type": "IncrementVariable", "inputs": {"name": var, "value": n}}, **kw)

    def set_many(self, name, assignments: dict, **kw):
        """Sequence of SetVariable actions inside a Scope (keeps conditions readable)."""
        inner = Block(self.flow)
        for var, val in assignments.items():
            inner.set_var(var, val, name=f"{name}_{var}")
        return self.add(name, {"type": "Scope", "actions": inner.actions}, **kw)

    def scope(self, name, build, **kw):
        inner = Block(self.flow)
        build(inner)
        return self.add(name, {"type": "Scope", "actions": inner.actions}, **kw)

    def cond(self, name, expr, then=None, otherwise=None, **kw):
        t = Block(self.flow)
        if then: then(t)
        a = {"type": "If", "expression": expr if isinstance(expr, dict) else cond_true(expr), "actions": t.actions}
        if otherwise:
            e = Block(self.flow)
            otherwise(e)
            a["else"] = {"actions": e.actions}
        else:
            a["else"] = {"actions": {}}
        return self.add(name, a, **kw)

    def when(self, name, expr, then, **kw):
        return self.cond(name, expr, then, **kw)

    def foreach(self, name, source, build, concurrency: int | None = 1, **kw):
        inner = Block(self.flow)
        build(inner)
        a = {"type": "Foreach", "foreach": source, "actions": inner.actions}
        if concurrency is not None:
            a["runtimeConfiguration"] = {"concurrency": {"repetitions": concurrency}}
        return self.add(name, a, **kw)

    def until(self, name, expr, build, count=10, timeout="PT1H", **kw):
        inner = Block(self.flow)
        build(inner)
        return self.add(name, {"type": "Until", "expression": X(expr), "limit": {"count": count, "timeout": timeout}, "actions": inner.actions}, **kw)

    def delay(self, name, seconds: int, **kw):
        return self.add(name, {"type": "Delay", "inputs": {"interval": {"count": seconds, "unit": "Second"}}}, **kw)

    def terminate(self, name, status, message="", **kw):
        inp = {"runStatus": status}
        if status == "Failed":
            inp["runError"] = {"code": "POU_CONFIG", "message": message}
        return self.add(name, {"type": "Terminate", "inputs": inp}, **kw)

    def select(self, name, source, select, **kw):
        return self.add(name, {"type": "Select", "inputs": {"from": source, "select": select}}, **kw)

    def filter_array(self, name, source, where, **kw):
        return self.add(name, {"type": "Query", "inputs": {"from": source, "where": where}}, **kw)

    def table(self, name, source, fmt, columns, **kw):
        return self.add(name, {"type": "Table", "inputs": {"from": source, "format": fmt, "columns": columns}}, **kw)

    def join(self, name, source, sep, **kw):
        return self.add(name, {"type": "Join", "inputs": {"from": source, "joinWith": sep}}, **kw)

    # ---- SharePoint (Send an HTTP request to SharePoint) -------------------------------------
    def sp(self, name, method, uri, body=None, headers=None, merge=False, etag=None, **kw):
        h = {"Accept": "application/json;odata=verbose"}
        if method != "GET":
            h["Content-Type"] = "application/json;odata=verbose"
        if merge:
            h["X-HTTP-Method"] = "MERGE"
            h["IF-MATCH"] = etag if etag is not None else "*"
        if headers:
            h.update(headers)
        params = {"dataset": X(o("Cfg_SiteUrl")), "parameters/method": "POST" if merge else method,
                  "parameters/uri": uri, "parameters/headers": h}
        if body is not None:
            params["parameters/body"] = body
        return self.add(name, {"type": "ApiConnection", "inputs": {
            "host": {"connectionName": SP_CONN, "operationId": "HttpRequest",
                     "apiId": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline"},
            "parameters": params, "authentication": "@parameters('$authentication')"}}, **kw)

    def sp_get(self, name, list_name, filter_parts=None, select=None, top=None, orderby=None, expand=None, **kw):
        q = []
        if filter_parts is not None:
            q.append(["$filter="] + list(filter_parts))
        if select: q.append([f"$select={select}"])
        if top:
            q.append(["$top=", top] if isinstance(top, str) else [f"$top={top}"])
        if orderby: q.append([f"$orderby={orderby}"])
        if expand: q.append([f"$expand={expand}"])
        parts = [f"/_api/web/lists/getbytitle('{list_name}')/items"]
        for i, seg in enumerate(q):
            parts.append("?" if i == 0 else "&")
            parts.extend(seg)
        return self.sp(name, "GET", cat(*parts), **kw)

    def sp_create(self, name, list_name, fields: dict, **kw):
        body = {"__metadata": {"type": LIST_TYPE(list_name)}, **fields}
        return self.sp(name, "POST", f"/_api/web/lists/getbytitle('{list_name}')/items", body, **kw)

    def sp_update(self, name, list_name, id_expr, fields: dict, etag=None, **kw):
        body = {"__metadata": {"type": LIST_TYPE(list_name)}, **fields}
        uri = cat(f"/_api/web/lists/getbytitle('{list_name}')/items(", id_expr, ")")
        return self.sp(name, "POST", uri, body, merge=True, etag=etag, **kw)

    def sp_delete(self, name, list_name, id_expr, **kw):
        uri = cat(f"/_api/web/lists/getbytitle('{list_name}')/items(", id_expr, ")")
        return self.sp(name, "POST", uri, None, headers={"X-HTTP-Method": "DELETE", "IF-MATCH": "*"}, **kw)

    def attempt(self, name, make, **kw):
        """A risky action whose failure is examined by the NEXT step (always=True) via ok(name) = actions(name)?['status'].
        Deliberately NOT wrapped in a scope: no dependence on how a container reports a handled failure, and one nesting level less."""
        return make(self, name)

    def mail(self, name, to, subject, body, attachments=None, **kw):
        params = {"emailMessage/To": to, "emailMessage/Subject": subject, "emailMessage/Body": body, "emailMessage/Importance": "Normal"}
        if attachments:
            params["emailMessage/Attachments"] = attachments
        return self.add(name, {"type": "ApiConnection", "inputs": {
            "host": {"connectionName": MAIL_CONN, "operationId": "SendEmailV2",
                     "apiId": "/providers/Microsoft.PowerApps/apis/shared_office365"},
            "parameters": params, "authentication": "@parameters('$authentication')"}}, **kw)

    def respond(self, name, body: dict, schema: dict, **kw):
        return self.add(name, {"type": "Response", "kind": "PowerApp", "inputs": {"statusCode": 200, "body": body, "schema": schema}}, **kw)


class Flow:
    def __init__(self, name: str, display: str, description: str, trigger: dict):
        self.name, self.display, self.description = name, display, description
        self.trigger = trigger
        self.names: set[str] = set()
        self._id = 0
        self.root = Block(self)
        self.connections = {SP_CONN}

    def register(self, name: str):
        if name in self.names:
            raise ValueError(f"duplicate action name {name} in {self.name}")
        if len(name) > 80:
            raise ValueError(f"action name too long: {name}")
        self.names.add(name)

    def next_id(self):
        self._id += 1
        return self._id

    def definition(self, site_url: str = "") -> dict:
        d = {
            "$schema": SCHEMA, "contentVersion": "1.0.0.0",
            "parameters": {
                "$connections": {"defaultValue": {}, "type": "Object"},
                "$authentication": {"defaultValue": {}, "type": "SecureObject"},
            },
            "triggers": self.trigger,
            "actions": self.root.actions,
        }
        return d

    def to_json(self, **kw) -> str:
        return json.dumps({"name": self.name, "properties": {"displayName": self.display, "definition": self.definition(**kw)}}, indent=2)


def recurrence(minutes: int | None = None, hours: int | None = None, time_zone: str = "Central Standard Time") -> dict:
    rec = {"frequency": "Minute", "interval": minutes} if minutes else {"frequency": "Hour", "interval": hours or 1}
    return {"Recurrence": {"type": "Recurrence", "recurrence": rec, "metadata": {"operationMetadataId": "00000000-0000-0000-0000-000000000000"}}}


def powerapps_trigger(inputs: list[tuple[str, str]]) -> dict:
    """Power Apps (V2) trigger. Input N is addressed as text, text_1, text_2 ... in triggerBody()."""
    props, req = {}, []
    for i, (title, desc) in enumerate(inputs):
        key = "text" if i == 0 else f"text_{i}"
        props[key] = {"title": title, "type": "string", "x-ms-dynamically-added": True, "description": desc, "x-ms-content-hint": "TEXT"}
        req.append(key)
    return {"manual": {"type": "Request", "kind": "Button", "inputs": {"schema": {"type": "object", "properties": props, "required": req}}}}


def trig_input(i: int) -> Ex:
    key = "text" if i == 0 else f"text_{i}"
    return Ex(f"triggerBody()?['{key}']")
